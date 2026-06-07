"""K=3 walk-forward EV backtest for Context A windows.

Context A: DIF>0, established uptrend, price 3-10% below 20-bar high and
below EMA20, above EMA60×0.98, no recent acceleration bar.

Entry: daily close of the first bar in each Context A run (min_gap=10).
Trade: ATR-based stop, 1R:1R target, 40-bar timeout.

Fold boundaries:
  IS  : ≤ 2022-12-31
  F1  : 2023-01-01 – 2023-12-31
  F2  : 2024-01-01 – 2024-12-31
  F3  : 2025-01-01 – present

Usage:
  uv run python scripts/backtest_context_a_ev.py
  uv run python scripts/backtest_context_a_ev.py --pool CN_METAL
  uv run python scripts/backtest_context_a_ev.py --stop-mult 2.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.b1_bottom_detector import _compute_htf_dif, _htf_relation_at
from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd as compute_macd

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD   = 40
MIN_GAP    = 10

US_SYMBOLS       = ["spy", "qqq", "iwm", "gld", "tlt", "nvda", "dia", "gdx", "xlf", "xlk"]
CN_METAL_SYMBOLS = ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"]

POOLS: dict[str, tuple[list[str], str]] = {
    "US":       (US_SYMBOLS,        "us_equity"),
    "CN_METAL": (CN_METAL_SYMBOLS,  "cn_metal_futures"),
}

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    candidates = list(bars_dir.glob(f"**/{sym}{suffix}.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    raw = payload.get("bars", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Trade simulation — identical to B1 backtest
# ---------------------------------------------------------------------------

def simulate_trade(
    bars: pd.DataFrame,
    entry_idx: int,
    stop_mult: float,
    atr_series: pd.Series,
) -> float | None:
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk   = stop_mult * av
    stop   = entry - risk
    tp1    = entry + risk
    tp2    = entry + 2 * risk
    hit_tp1 = False
    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if lo <= stop:
                return -1.0
            if hi >= tp1:
                hit_tp1 = True
                if hi >= tp2:
                    return 1.5
        else:
            if lo <= stop:
                return 0.0
            if hi >= tp2:
                return 1.5
            if offset == MAX_HOLD:
                mark = (cl - entry) / risk
                return 0.5 + 0.5 * float(np.clip(mark, -3.0, 3.0))
    idx_fin = min(entry_idx + MAX_HOLD, len(bars) - 1)
    mark = (float(bars["close"].iloc[idx_fin]) - entry) / risk
    return float(np.clip(mark, -3.0, 3.0))


# ---------------------------------------------------------------------------
# Context A scanner — first bar of each A run (min_gap)
# ---------------------------------------------------------------------------

def scan_context_a(
    bars: pd.DataFrame,
    h_bars: pd.DataFrame | None,
    stop_mult: float,
    atr_series: pd.Series,
) -> list[dict]:
    macd_df = compute_macd(bars["close"])
    ema20   = bars["close"].ewm(span=20, adjust=False).mean()
    ema60   = bars["close"].ewm(span=60, adjust=False).mean()

    h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

    records: list[dict] = []
    last_sig_idx = -999

    for i in range(65, len(bars)):
        if i - last_sig_idx < MIN_GAP:
            continue
        ctx = classify_context(bars, i, macd_df, ema20, ema60)
        if ctx != "A":
            continue

        r = simulate_trade(bars, i, stop_mult, atr_series)
        if r is None:
            continue

        ts    = bars["timestamp"].iloc[i]
        h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None
        period = (
            "IS"   if ts <= CUTOFF_IS   else
            "OOS1" if ts <= CUTOFF_OOS1 else
            "OOS2" if ts <= CUTOFF_OOS2 else
            "OOS3"
        )
        dif_val  = float(macd_df["dif"].iloc[i])
        hist_val = float(macd_df["hist"].iloc[i])
        records.append({
            "bar_idx":   i,
            "timestamp": ts,
            "period":    period,
            "r":         r,
            "h_rel":     h_rel,
            "dif":       round(dif_val,  6),
            "hist":      round(hist_val, 6),
        })
        last_sig_idx = i

    return records


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _period_str(subset: pd.DataFrame) -> str:
    parts = []
    for p, label in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
        g = subset[subset["period"] == p]
        if len(g):
            parts.append(f"{label}={g['r'].mean():+.3f}R(n={len(g)})")
        else:
            parts.append(f"{label}=—")
    return "  ".join(parts)


def report_pool(pool: str, df: pd.DataFrame) -> None:
    width = 26
    print(f"\n{'='*80}")
    print(f"Pool: {pool}  —  Context A  K=3 Walk-Forward")
    print(f"stop={df.attrs.get('stop_mult', '?')}×ATR  max_hold={MAX_HOLD}  min_gap={MIN_GAP}")
    print("=" * 80)

    def row(label: str, sub: pd.DataFrame) -> None:
        if sub.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n  = len(sub)
        ev = sub["r"].mean()
        hit = (sub["r"] > 0).mean()
        print(f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}  {_period_str(sub)}")

    print()
    row("All signals",        df)
    row("h=opposing",         df[df["h_rel"] == "opposing"])
    row("h=supporting",       df[df["h_rel"] == "supporting"])
    row("h=neutral/unknown",  df[df["h_rel"].isin(["neutral"]) | df["h_rel"].isna()])

    print()
    print("  Per-symbol (h=opposing):")
    for sym, grp in df.groupby("symbol"):
        opp = grp[grp["h_rel"] == "opposing"]
        all_str = f"n={len(grp)} EV={grp['r'].mean():+.3f}R"
        opp_str = f"  h=opp n={len(opp)} EV={opp['r'].mean():+.3f}R" if len(opp) else "  h=opp —"
        print(f"    {sym}: {all_str}{opp_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool",      choices=list(POOLS) + ["ALL"], default="ALL")
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--bars-dir",  type=Path,  default=DEFAULT_BARS_DIR)
    args = parser.parse_args()

    pools_to_run = list(POOLS) if args.pool == "ALL" else [args.pool]

    for pool in pools_to_run:
        symbols, _ = POOLS[pool]
        print(f"\nRunning pool: {pool}")
        all_records: list[dict] = []

        for sym in symbols:
            bars = load_bars(sym, args.bars_dir)
            if bars is None or len(bars) < 100:
                print(f"  {sym}: no data")
                continue
            h_bars = load_bars(sym, args.bars_dir, suffix="_60")
            atr    = compute_atr(bars)
            recs   = scan_context_a(bars, h_bars, args.stop_mult, atr)
            for r in recs:
                r["symbol"] = sym
            n_opp = sum(1 for r in recs if r.get("h_rel") == "opposing")
            print(f"  {sym}: signals={len(recs)}  h=opp={n_opp}")
            all_records.extend(recs)

        if not all_records:
            print(f"  No signals for {pool}")
            continue

        df = pd.DataFrame(all_records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.attrs["stop_mult"] = args.stop_mult
        report_pool(pool, df)

        out = Path(f"/tmp/context_a_ev_{pool.lower()}.csv")
        df.to_csv(out, index=False)
        print(f"\n  Saved to {out}")


if __name__ == "__main__":
    main()
