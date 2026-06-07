"""15min intraday confirmation for daily PA TR-phase signals.

After a daily PABottomDetector h=opposing signal fires in TR/TR_FORMING phase,
wait for a 15min PABottomDetector h=opposing signal within a confirmation window
before entering. Compare EV vs entering at daily close (baseline).

Question: does the 15min confirmation filter improve TR-phase signal quality?
Metrics: coverage (% confirmed), EV improvement, entry timing.

Uses CN_METAL as baseline (validated h=opp pool).

Usage:
  uv run python scripts/backtest_pa_15min_confirm.py
  uv run python scripts/backtest_pa_15min_confirm.py --pool CN_COMMODITY
  uv run python scripts/backtest_pa_15min_confirm.py --window-days 3
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from data import bar_loader
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
MAX_HOLD  = 40   # daily bars
MIN_GAP   = 5
STOP_MULT = 1.5

CONFIRM_DAYS_DEFAULT = 5   # max trading days to wait for 15min confirmation
BARS_PER_DAY_15 = 16       # approx 15min bars in one CN futures trading day

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")

POOLS: dict[str, list[str]] = {
    "CN_METAL": ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
}


def load_bars(sym: str, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, BARS_DIR)


def compute_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_from_entry(
    bars: pd.DataFrame, entry_idx: int, entry_price: float, risk: float
) -> float | None:
    """Simulate trade given an explicit entry price and risk (stop distance)."""
    if risk <= 0 or not np.isfinite(risk):
        return None
    stop = entry_price - risk
    tp1  = entry_price + risk
    tp2  = entry_price + 2 * risk
    hit1 = False
    for off in range(1, MAX_HOLD + 1):
        i = entry_idx + off
        if i >= len(bars):
            break
        lo = float(bars["low"].iloc[i])
        hi = float(bars["high"].iloc[i])
        cl = float(bars["close"].iloc[i])
        if not hit1:
            if lo <= stop:
                return -1.0
            if hi >= tp1:
                hit1 = True
                if hi >= tp2:
                    return 1.5
        else:
            if lo <= stop:
                return 0.0
            if hi >= tp2:
                return 1.5
            if off == MAX_HOLD:
                return 0.5 + 0.5 * float(np.clip((cl - entry_price) / risk, -3, 3))
    f = min(entry_idx + MAX_HOLD, len(bars) - 1)
    return float(np.clip((float(bars["close"].iloc[f]) - entry_price) / risk, -3, 3))


def find_15min_confirm(
    sig_ts: pd.Timestamp,
    m15_sigs: list[PASignal],
    m15_bars: pd.DataFrame,
    window_days: int,
) -> PASignal | None:
    """Find first 15min h=opp signal within window_days after daily signal."""
    deadline = sig_ts + pd.Timedelta(days=window_days)
    for s in m15_sigs:
        if s.timestamp <= sig_ts:
            continue
        if s.timestamp > deadline:
            break
        if s.higher_tf_relation == "opposing":
            return s
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", choices=list(POOLS), default="CN_METAL")
    parser.add_argument("--window-days", type=int, default=CONFIRM_DAYS_DEFAULT)
    args = parser.parse_args()

    symbols = POOLS[args.pool]

    daily_det = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=MIN_GAP)
    m15_det   = PABottomDetector(min_h_legs=2, min_quality=0.2, ema_threshold=0.0, min_gap=3)
    struct_det = PAStructureDetector()

    records: list[dict] = []

    for sym in symbols:
        bars   = load_bars(sym)
        if bars is None or len(bars) < 100:
            print(f"  [SKIP] {sym}: no daily data")
            continue
        h_bars  = load_bars(sym, suffix="_60")
        m15_bars = load_bars(sym, suffix="_15")
        if m15_bars is None or len(m15_bars) < 50:
            print(f"  [SKIP] {sym}: no 15min data")
            continue

        atr = compute_atr(bars)

        # Daily signals: TR/TR_FORMING phase, h=opp
        daily_sigs = [
            s for s in daily_det.scan(bars, h_bars)
            if s.higher_tf_relation == "opposing"
        ]

        # 15min signals: h=opp vs 60min (sorted by timestamp for binary search)
        m15_sigs_all: list[PASignal] = m15_det.scan(m15_bars, h_bars)
        m15_sigs_opp = [s for s in m15_sigs_all if s.higher_tf_relation == "opposing"]

        n_tr = 0
        print(f"  {sym}: {len(daily_sigs)} daily h=opp", end="")

        for sig in daily_sigs:
            struct = struct_det.detect(bars, up_to_idx=sig.bar_idx)
            is_tr  = struct.phase in ("TR", "TR_FORMING")

            ts     = sig.timestamp
            period = (
                "IS"   if ts <= CUTOFF_IS   else
                "OOS1" if ts <= CUTOFF_OOS1 else
                "OOS2" if ts <= CUTOFF_OOS2 else
                "OOS3"
            )

            # Baseline: enter at daily close using ATR stop
            av      = float(atr.iloc[sig.bar_idx])
            r_base  = None
            if av > 0 and np.isfinite(av):
                entry_d = float(bars["close"].iloc[sig.bar_idx])
                r_base  = simulate_from_entry(bars, sig.bar_idx, entry_d, STOP_MULT * av)

            if r_base is None:
                continue

            if is_tr:
                n_tr += 1

            # 15min confirmation: find first 15min h=opp signal in window
            m15_sig = find_15min_confirm(sig.timestamp, m15_sigs_opp, m15_bars, args.window_days)
            confirmed = m15_sig is not None

            r_confirm = None
            confirm_entry_price = None
            confirm_delay_bars  = None
            if confirmed:
                m15_close = float(m15_bars["close"].iloc[m15_sig.bar_idx])
                # Risk based on daily ATR (same R-unit for comparison)
                r_confirm = simulate_from_entry(
                    bars,
                    sig.bar_idx,       # continue monitoring on daily bars from signal bar
                    m15_close,
                    STOP_MULT * av,
                )
                confirm_entry_price = m15_close
                # Time delay in 15min bars
                confirm_delay_bars = m15_sig.bar_idx - (
                    m15_bars[m15_bars["timestamp"] <= sig.timestamp].index[-1]
                    if (m15_bars["timestamp"] <= sig.timestamp).any()
                    else 0
                )

            records.append({
                "sym":       sym,
                "ts":        ts,
                "period":    period,
                "phase":     struct.phase,
                "is_tr":     is_tr,
                "r_base":    r_base,
                "confirmed": confirmed,
                "r_confirm": r_confirm,
                "confirm_price": confirm_entry_price,
                "confirm_delay_bars": confirm_delay_bars,
                "entry_price": float(bars["close"].iloc[sig.bar_idx]),
                "at_tr_bot": struct.at_tr_bottom,
            })

        print(f"  TR={n_tr}  15m-sigs={len(m15_sigs_opp)}")

    df = pd.DataFrame(records)
    if df.empty:
        print("No signals found.")
        return

    oos = df[df["period"] != "IS"]
    oos_tr = oos[oos["is_tr"]]

    print(f"\n{'='*90}")
    print(f"{args.pool} — 15min Intraday Confirmation  (window={args.window_days}d, K=3)")
    print("=" * 90)

    def fold_str(sub: pd.DataFrame, col: str) -> str:
        parts = []
        for p, lbl in [("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
            g = sub[sub["period"] == p][col].dropna()
            parts.append(f"{lbl}={g.mean():+.3f}R(n={len(g)})" if len(g) else f"{lbl}=—")
        return "  ".join(parts)

    def row(label: str, sub: pd.DataFrame, col: str = "r_base") -> None:
        if sub.empty:
            print(f"  {label:<38}: n=  0")
            return
        valid = sub[col].dropna()
        ev = valid.mean() if not valid.empty else float("nan")
        print(f"  {label:<38}: n={len(valid):4d}  EV={ev:+.3f}R  {fold_str(sub, col)}")

    print("\n── Baseline (all h=opp, enter at daily close) ──")
    row("All h=opp",             oos)
    row("TR/TR_FORMING phase",   oos_tr)
    row("BULL phase",            oos[oos["phase"] == "BULL"])

    print("\n── Coverage: 15min confirmation rate ──")
    if not oos_tr.empty:
        n_conf = oos_tr["confirmed"].sum()
        n_tot  = len(oos_tr)
        print(f"  TR-phase confirmed: {n_conf}/{n_tot} = {n_conf/n_tot:.0%}  (window={args.window_days}d)")
        delay = oos_tr[oos_tr["confirmed"]]["confirm_delay_bars"].dropna()
        if not delay.empty:
            print(f"  Delay (15min bars): median={delay.median():.0f}  p90={delay.quantile(0.9):.0f}")
    # For all h=opp
    n_conf_all = oos["confirmed"].sum()
    print(f"  All h=opp confirmed: {n_conf_all}/{len(oos)} = {n_conf_all/len(oos):.0%}")

    print("\n── Confirmed vs unconfirmed TR signals ──")
    tr_conf   = oos_tr[oos_tr["confirmed"]]
    tr_unconf = oos_tr[~oos_tr["confirmed"]]
    row("TR confirmed (enter 15m)", tr_conf, "r_confirm")
    row("TR confirmed (baseline)",  tr_conf, "r_base")
    row("TR unconfirmed (baseline)", tr_unconf, "r_base")

    print("\n── Entry price improvement (confirmed TR) ──")
    if not tr_conf.empty:
        entry_d  = tr_conf["entry_price"]
        entry_15 = tr_conf["confirm_price"]
        better   = (entry_15 < entry_d).mean()
        improve  = ((entry_d - entry_15) / entry_d * 100).mean()
        print(f"  15min entry < daily close: {better:.0%} of confirmed signals")
        print(f"  Avg entry improvement: {improve:+.2f}% (lower = better for long)")

    print("\n── Phase breakdown (OOS h=opp) ──")
    for ph in ["BULL", "TR_FORMING", "TR", "BEAR", "UNCLEAR"]:
        sub = oos[oos["phase"] == ph]
        if sub.empty:
            continue
        print(f"  {ph:<14}: n={len(sub):3d}  EV_base={sub['r_base'].mean():+.3f}R  "
              f"conf={sub['confirmed'].mean():.0%}")

    print(f"\n── Per-symbol (TR-phase OOS) ──")
    for sym, grp in oos_tr.groupby("sym"):
        ev_b = grp["r_base"].mean()
        conf = grp["confirmed"].mean()
        ev_c = grp[grp["confirmed"]]["r_confirm"].mean() if grp["confirmed"].any() else float("nan")
        print(f"  {sym}: n={len(grp)}  EV_base={ev_b:+.3f}R  conf={conf:.0%}  EV_confirm={ev_c:+.3f}R")


if __name__ == "__main__":
    main()
