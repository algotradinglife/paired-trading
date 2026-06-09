"""A_top sell-the-rally put-lane K=3 discovery backtest.

Fires on classify_context_top(...) == "A_top" (a DIF<0 counter-trend rally in a
downtrend), forward-sims a SHORT, and stratifies by daily phase x h_rel x pool
across a K=3 walk-forward. See docs/superpowers/specs/2026-06-10-pa-top-path-b-design.md.

Usage:
  uv run python scripts/backtest_pa_atop.py --pool US_EQUITY
  uv run python scripts/backtest_pa_atop.py --pool CN_METAL --cutoff3 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.pa_context_classifier import classify_context_top
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD = 40
MIN_GAP = 10

POOLS: dict[str, list[str]] = {
    "US_EQUITY": ["spy", "qqq", "iwm", "dia", "gld", "gdx", "xlf", "xlk",
                  "nvda", "xlb", "xle", "xlre", "xlu"],
    "CN_METAL": ["kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au",
                 "kq_m_shfe_ag", "kq_m_ine_sc"],
}


def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_short(bars: pd.DataFrame, entry_idx: int, atr_series: pd.Series,
                   stop_mult: float = 1.5, max_hold: int = MAX_HOLD) -> float | None:
    """Short mirror of simulate_trade. Stop=entry+risk; TP1=entry-risk; TP2=entry-2risk.
    Downmove -> +R; stopped -> -1.0. (Verbatim port of backtest_pa_top_grid.simulate_short.)"""
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk = stop_mult * av
    stop = entry + risk
    tp1, tp2 = entry - risk, entry - 2 * risk
    hit_tp1 = False
    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if hi >= stop:
                return -1.0
            if lo <= tp1:
                hit_tp1 = True
                if lo <= tp2:
                    return 1.5
        else:
            if hi >= stop:
                return 0.0
            if lo <= tp2:
                return 1.5
            if offset == max_hold:
                return 0.5 + 0.5 * float(np.clip((entry - cl) / risk, -3, 3))
    idx_fin = min(entry_idx + max_hold, len(bars) - 1)
    return float(np.clip((entry - float(bars["close"].iloc[idx_fin])) / risk, -3, 3))


def htf_relation_top(ts: pd.Timestamp, h_ts: np.ndarray, h_dif: np.ndarray) -> str | None:
    """TOP/short convention: supporting = HTF DIF<0 (bearish, confirms short);
    opposing = HTF DIF>0 (bullish, counter); neutral = 0; None if no HTF bar."""
    ts_np = np.datetime64(ts.to_datetime64())
    mask = h_ts <= ts_np
    if not mask.any():
        return None
    v = float(h_dif[int(np.flatnonzero(mask)[-1])])
    if not np.isfinite(v):
        return None
    if v < 0:
        return "supporting"
    if v > 0:
        return "opposing"
    return "neutral"


def fold_period(ts, c1, c2, c3) -> str:
    if c3 is None:
        return "IS" if ts <= c1 else ("OOS1" if ts <= c2 else "OOS2")
    return ("IS" if ts <= c1 else "OOS1" if ts <= c2 else
            "OOS2" if ts <= c3 else "OOS3")


def scan_symbol(sym, bars, h_bars, atr, macd_df, ema20, ema60, c1, c2, c3, pool):
    """Yield trade records for A_top fires on this symbol."""
    struct_det = PAStructureDetector()
    if h_bars is not None:
        hm = compute_macd(h_bars["close"], hist_scale=1.0)
        h_dif = hm["dif"].values.astype(float)
        h_ts = pd.to_datetime(h_bars["timestamp"]).values
    else:
        h_dif = h_ts = None
    last_idx = -999
    out = []
    for i in range(len(bars)):
        if classify_context_top(bars, i, macd_df, ema20, ema60) != "A_top":
            continue
        if i - last_idx < MIN_GAP:
            continue
        r = simulate_short(bars, i, atr, stop_mult=1.5, max_hold=MAX_HOLD)
        if r is None:
            continue
        last_idx = i
        ts = pd.Timestamp(bars["timestamp"].iloc[i])
        phase = struct_det.detect(bars, up_to_idx=i).phase
        h_rel = (htf_relation_top(ts, h_ts, h_dif) if h_dif is not None else None)
        out.append({"pool": pool, "symbol": sym, "bar_idx": i, "timestamp": ts,
                    "period": fold_period(ts, c1, c2, c3), "r": r,
                    "phase": phase, "h_rel": h_rel})
    return out


def _report(label, sub, k3, width=34):
    if sub.empty:
        print(f"  {label:{width}s}: n=  0")
        return
    parts = []
    for p, lbl in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
        g = sub[sub["period"] == p]
        if len(g):
            parts.append(f"{lbl}={g['r'].mean():+.3f}(n={len(g)})")
    print(f"  {label:{width}s}: n={len(sub):4d}  EV={sub['r'].mean():+.3f}R  "
          f"hit={(sub['r']>0).mean():.0%}  " + "  ".join(parts))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pool", default="US_EQUITY", choices=list(POOLS))
    p.add_argument("--cutoff1", default="2022-12-31")
    p.add_argument("--cutoff2", default="2023-12-31")
    p.add_argument("--cutoff3", default="2024-12-31")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--htf-suffix", default="_weekly",
                   help="suffix for higher-TF bars used for h_rel. If absent for a "
                        "pool, h_bars=None -> h_rel=None and the phase breakdown still works.")
    args = p.parse_args()
    c1 = pd.Timestamp(args.cutoff1, tz="UTC")
    c2 = pd.Timestamp(args.cutoff2, tz="UTC")
    c3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None

    records = []
    for sym in POOLS[args.pool]:
        bars = load_bars(sym, args.bars_dir)
        if bars is None or len(bars) < 80:
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix=args.htf_suffix)
        atr = compute_atr(bars)
        macd_df = compute_macd(bars["close"])
        ema20 = bars["close"].ewm(span=20, adjust=False).mean()
        ema60 = bars["close"].ewm(span=60, adjust=False).mean()
        records.extend(scan_symbol(sym, bars, h_bars, atr, macd_df, ema20, ema60,
                                   c1, c2, c3, args.pool))

    if not records:
        print("No A_top signals found.")
        return
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    k3 = c3 is not None

    print(f"\nA_top put-lane K=3 — pool={args.pool}  n={len(df)}")
    print(f"Periods: IS<={args.cutoff1}  F1->{args.cutoff2}  F2->{args.cutoff3}  F3>")
    print("=" * 92)
    print("\n--- By phase (sanity: BULL must be NEGATIVE) ---")
    for ph in ["BULL", "TR", "TR_FORMING", "BEAR", "UNCLEAR"]:
        _report(f"phase={ph}", df[df["phase"] == ph], k3)
    print("\n--- By phase x h_rel ---")
    for ph in ["BEAR", "TR", "TR_FORMING"]:
        for hr in ["supporting", "opposing", "neutral"]:
            _report(f"{ph} + h={hr}", df[(df["phase"] == ph) & (df["h_rel"] == hr)], k3)
    out = Path(f"/tmp/pa_atop_{args.pool.lower()}.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved {len(df)} signals → {out}")


if __name__ == "__main__":
    main()
