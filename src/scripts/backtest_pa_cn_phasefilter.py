"""CN_COMMODITY + CN_BOND PA H2 BULL phase filter analysis.

Applies PAStructureDetector to h=opposing signals.
Compares EV: all h=opp vs BULL-phase-excluded h=opp (K=3 walk-forward).

Question: does excluding BULL phase improve OOS F3 EV for CN_COMMODITY/CN_BOND?
Baseline for comparison: CN_METAL BULL phase → all-negative (F1=-1.0R F2=-1.0R F3=-0.29R).

Usage:
  uv run python scripts/backtest_pa_cn_phasefilter.py
  uv run python scripts/backtest_pa_cn_phasefilter.py --pool CN_BOND
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
MAX_HOLD  = 40
MIN_GAP   = 5
STOP_MULT = 1.5

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")

POOLS: dict[str, list[str]] = {
    "CN_COMMODITY": [
        "kq_m_shfe_rb",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
    "CN_BOND": ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
}


def load_bars(sym: str, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, BARS_DIR)


def compute_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate(bars: pd.DataFrame, idx: int, atr: pd.Series) -> float | None:
    entry = float(bars["close"].iloc[idx])
    av    = float(atr.iloc[idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk = STOP_MULT * av
    stop, tp1, tp2 = entry - risk, entry + risk, entry + 2 * risk
    hit1 = False
    for off in range(1, MAX_HOLD + 1):
        i = idx + off
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
                return 0.5 + 0.5 * float(np.clip((cl - entry) / risk, -3, 3))
    f = min(idx + MAX_HOLD, len(bars) - 1)
    return float(np.clip((float(bars["close"].iloc[f]) - entry) / risk, -3, 3))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", choices=list(POOLS) + ["ALL"], default="ALL")
    args = parser.parse_args()

    pools_to_run = {args.pool: POOLS[args.pool]} if args.pool != "ALL" else POOLS

    det        = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=MIN_GAP)
    struct_det = PAStructureDetector()

    all_records: list[dict] = []

    for pool_name, symbols in pools_to_run.items():
        print(f"\nPool: {pool_name}")
        pool_records: list[dict] = []

        for sym in symbols:
            bars = load_bars(sym)
            if bars is None or len(bars) < 100:
                print(f"  [SKIP] {sym}: no daily data")
                continue
            h_bars = load_bars(sym, suffix="_60")
            atr    = compute_atr(bars)
            macd_df = compute_macd(bars["close"])
            sigs   = [s for s in det.scan(bars, h_bars) if s.higher_tf_relation == "opposing"]
            print(f"  {sym}: {len(sigs)} h=opp signals")

            for sig in sigs:
                r = simulate(bars, sig.bar_idx, atr)
                if r is None:
                    continue
                struct = struct_det.detect(bars, up_to_idx=sig.bar_idx)
                ts     = sig.timestamp
                period = (
                    "IS"   if ts <= CUTOFF_IS   else
                    "OOS1" if ts <= CUTOFF_OOS1 else
                    "OOS2" if ts <= CUTOFF_OOS2 else
                    "OOS3"
                )
                dif = float(macd_df["dif"].iloc[sig.bar_idx])
                rec = {
                    "pool": pool_name,
                    "sym": sym,
                    "ts": ts,
                    "period": period,
                    "r": r,
                    "phase": struct.phase,
                    "dif_pos": dif > 0,
                    "at_tr_bot": struct.at_tr_bottom,
                }
                pool_records.append(rec)
                all_records.append(rec)

        _print_pool_report(pool_name, pd.DataFrame(pool_records))

    if len(pools_to_run) > 1 and all_records:
        print("\n" + "=" * 90)
        print("COMBINED — CN_COMMODITY + CN_BOND")
        print("=" * 90)
        _print_pool_report("ALL", pd.DataFrame(all_records))


def _fold_str(sub: pd.DataFrame, width: int = 32) -> str:
    parts = []
    for p, lbl in [("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
        g = sub[sub["period"] == p]["r"].dropna()
        parts.append(f"{lbl}={g.mean():+.3f}R(n={len(g)})" if len(g) else f"{lbl}=—")
    return "  ".join(parts)


def _print_pool_report(name: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"  [{name}] no data")
        return
    oos = df[df["period"] != "IS"]
    print(f"\n{'='*90}")
    print(f"{name} — PA H2 BULL phase filter  (h=opposing, K=3, ATR stop {STOP_MULT}×)")
    print("=" * 90)

    def row(label: str, sub: pd.DataFrame) -> None:
        if sub.empty:
            print(f"  {label:<30}: n=  0")
            return
        oos_sub = sub[sub["period"] != "IS"]
        ev_oos  = oos_sub["r"].mean() if not oos_sub.empty else float("nan")
        print(f"  {label:<30}: n={len(oos_sub):4d}  EV={ev_oos:+.3f}R  {_fold_str(sub)}")

    row("All h=opp",          oos)
    row("h=opp BULL excl.",   oos[oos["phase"] != "BULL"])
    row("BULL phase only",    oos[oos["phase"] == "BULL"])
    row("TR phase",           oos[oos["phase"].isin(["TR", "TR_FORMING"])])
    row("TR + at_bot",        oos[oos["phase"].isin(["TR", "TR_FORMING"]) & oos["at_tr_bot"]])
    row("BEAR/UNCLEAR",       oos[oos["phase"].isin(["BEAR", "UNCLEAR"])])

    print(f"\n── Phase distribution (OOS h=opp) ──")
    for ph in ["BULL", "TR_FORMING", "TR", "BEAR", "UNCLEAR"]:
        sub = oos[oos["phase"] == ph]
        if sub.empty:
            continue
        ev = sub["r"].mean()
        print(f"  {ph:<14}: n={len(sub):3d}  EV={ev:+.3f}R  {_fold_str(sub)}")

    print(f"\n── Filter impact ──")
    n_all  = len(oos)
    n_bull = len(oos[oos["phase"] == "BULL"])
    n_filt = n_all - n_bull
    print(f"  BULL removed: {n_bull}/{n_all} = {n_bull/n_all:.0%} signals")
    ev_before = oos["r"].mean() if n_all else float("nan")
    ev_after  = oos[oos["phase"] != "BULL"]["r"].mean() if n_filt else float("nan")
    print(f"  EV before filter: {ev_before:+.3f}R → after: {ev_after:+.3f}R  (Δ={ev_after-ev_before:+.3f}R)")


if __name__ == "__main__":
    main()
