"""Swing feature analysis: extract price-structure / candle / volume features
around each signal bar and compare winners vs losers.

Goal: identify feature combinations that distinguish high-quality setups.

Features computed around signal date (using daily bars):
  candle:   wick_lo_ratio, wick_hi_ratio, body_pct, is_doji
  volume:   vol_ratio (signal / 20-bar MA), vol_trend (slope of last 5 bars)
  structure:
    atr_norm_range20   — 20-bar H-L range / ATR (compression)
    dist_from_lo20     — pct distance from signal close to 20-bar low
    dist_from_hi20     — pct distance from signal close to 20-bar high
    ema20_slope        — (EMA20[0] - EMA20[-5]) / EMA20[-5]  (trend direction)
    bars_below_ema20   — # bars out of last 10 where close < EMA20 (for bottoms)
    consol_ratio       — range(last 10) / range(last 20) (1=no compression, <1=tight)
  existing MACD:
    higher_relation, confidence_band, subtype

Output:
  data/review/swing_features.csv   — one row per signal, all features + outcome
  data/review/swing_feature_agg.csv — win rate by feature quintile
"""
from __future__ import annotations

import json
import glob
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

SRC_DIR    = Path(__file__).resolve().parents[1]
RAW_DIR    = SRC_DIR / "data" / "raw"
REVIEW_DIR = SRC_DIR / "data" / "review"

LOOKBACK = 30   # bars before signal to compute features
MIN_BARS = 25   # minimum bars needed to compute all features


# ---------------------------------------------------------------------------
# Bar loading
# ---------------------------------------------------------------------------
def _load_bars(symbol: str) -> pd.DataFrame | None:
    path = RAW_DIR / f"{symbol}_daily.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
        bars = d.get("bars", [])
        if not bars:
            return None
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.date
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------
def _ema(series: np.ndarray, period: int) -> np.ndarray:
    if len(series) == 0:
        return series.astype(float)
    k = 2 / (period + 1)
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1 - k)
    return out


def compute_features(bars: pd.DataFrame, sig_idx: int) -> dict | None:
    """Compute features for the bar at sig_idx. Returns None if not enough history."""
    if sig_idx < LOOKBACK:
        return None

    window = bars.iloc[sig_idx - LOOKBACK : sig_idx + 1].copy()
    bar    = bars.iloc[sig_idx]

    o, h, l, c = float(bar.open), float(bar.high), float(bar.low), float(bar.close)
    bar_range = h - l
    if bar_range <= 0:
        return None

    # --- Candle features ---
    body      = abs(c - o)
    body_pct  = body / bar_range
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    wick_hi_ratio = upper_wick / bar_range
    wick_lo_ratio = lower_wick / bar_range
    is_doji   = int(body_pct < 0.1)

    # --- Volume ---
    vols = window["volume"].values.astype(float)
    vol_ma20 = vols[:-1].mean() if len(vols) > 1 else float("nan")
    vol_ratio = float(vols[-1]) / vol_ma20 if vol_ma20 > 0 else float("nan")
    # slope of volume over last 5 bars (linear regression sign)
    if len(vols) >= 5:
        y = vols[-5:]
        x = np.arange(5)
        vol_trend = float(np.polyfit(x, y, 1)[0]) / (vol_ma20 + 1e-9)
    else:
        vol_trend = float("nan")

    # --- ATR (14-bar) ---
    highs  = window["high"].values.astype(float)
    lows   = window["low"].values.astype(float)
    closes = window["close"].values.astype(float)
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i - 1]),
               abs(lows[i]  - closes[i - 1]))
           for i in range(1, len(highs))]
    atr = float(np.mean(trs[-14:])) if len(trs) >= 14 else float(np.mean(trs)) if trs else float("nan")

    # --- Structure (20-bar slice, not full 30-bar window) ---
    w20   = window.iloc[-20:]
    hi20  = float(w20["high"].max())
    lo20  = float(w20["low"].min())
    range20 = hi20 - lo20
    atr_norm_range20 = range20 / atr if atr > 0 else float("nan")

    dist_from_lo20 = (c - lo20) / (range20 + 1e-9)   # 0=at low, 1=at high
    dist_from_hi20 = (hi20 - c) / (range20 + 1e-9)

    # Consolidation: range of last 10 vs last 20 bars
    hi10  = float(window.iloc[-10:]["high"].max())
    lo10  = float(window.iloc[-10:]["low"].min())
    range10 = hi10 - lo10
    consol_ratio = range10 / (range20 + 1e-9)   # <0.5 = tight consolidation

    # EMA20 slope
    ema20 = _ema(closes, 20)
    ema20_slope = (ema20[-1] - ema20[-6]) / (ema20[-6] + 1e-9) if len(ema20) >= 6 else float("nan")

    # Bars below EMA20 in last 10 (useful for bottoms)
    bars_below_ema20 = int((closes[-10:] < ema20[-10:]).sum()) if len(closes) >= 10 else 0

    # Prior swing: did price make lower low before signal? (for bottoms)
    # Check if the signal bar low is the lowest in last 20 bars
    is_20bar_low = int(l <= lo20 + atr * 0.05)   # within 5% ATR of 20-bar low

    return {
        "wick_lo_ratio":      round(wick_lo_ratio, 4),
        "wick_hi_ratio":      round(wick_hi_ratio, 4),
        "body_pct":           round(body_pct, 4),
        "is_doji":            is_doji,
        "vol_ratio":          round(vol_ratio, 3) if not np.isnan(vol_ratio) else None,
        "vol_trend":          round(vol_trend, 4) if not np.isnan(vol_trend) else None,
        "atr_norm_range20":   round(atr_norm_range20, 2) if not np.isnan(atr_norm_range20) else None,
        "dist_from_lo20":     round(dist_from_lo20, 4),
        "dist_from_hi20":     round(dist_from_hi20, 4),
        "consol_ratio":       round(consol_ratio, 4),
        "ema20_slope":        round(ema20_slope, 6) if not np.isnan(ema20_slope) else None,
        "bars_below_ema20":   bars_below_ema20,
        "is_20bar_low":       is_20bar_low,
        "atr":                round(atr, 4),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    # Load signals
    frames = []
    for f in glob.glob(str(REVIEW_DIR / "rr_b_*.csv")):
        df = pd.read_csv(f)
        df["pool"] = Path(f).stem.replace("rr_b_", "")
        frames.append(df)
    signals = pd.concat(frames, ignore_index=True)
    signals["date"] = pd.to_datetime(signals["date"]).dt.date
    signals["win"]  = signals["outcome"].isin(["tp1_tp2", "tp1_stop", "tp1_max"])

    print(f"Loaded {len(signals)} signals across {signals['pool'].nunique()} pools")

    # Load bar data per symbol
    bar_cache: dict[str, pd.DataFrame | None] = {}

    rows: list[dict] = []
    skipped = 0

    for _, sig in signals.iterrows():
        sym = str(sig["symbol"])
        if sym not in bar_cache:
            bar_cache[sym] = _load_bars(sym)
        bars = bar_cache[sym]
        if bars is None:
            skipped += 1
            continue

        sig_date = sig["date"]
        # Find signal bar index
        idx_candidates = bars.index[bars["date"] == sig_date].tolist()
        if not idx_candidates:
            # Try nearest date within 3 days
            bar_dates = bars["date"].values
            for delta in [1, -1, 2, -2, 3, -3]:
                from datetime import timedelta
                target = sig_date + timedelta(days=delta)
                cands = bars.index[bars["date"] == target].tolist()
                if cands:
                    idx_candidates = cands
                    break
        if not idx_candidates:
            skipped += 1
            continue

        sig_idx = idx_candidates[0]
        feats = compute_features(bars, sig_idx)
        if feats is None:
            skipped += 1
            continue

        row = {
            "symbol":           sym,
            "date":             sig_date,
            "pool":             sig["pool"],
            "direction":        sig["direction"],
            "subtype":          sig["subtype"],
            "confidence":       sig["confidence"],
            "confidence_band":  sig["confidence_band"],
            "higher_relation":  sig["higher_relation"],
            "lower_relation":   sig.get("lower_relation"),
            "outcome":          sig["outcome"],
            "realized_r":       sig["realized_r"],
            "win":              sig["win"],
            **feats,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"Features computed: {len(df)} / {len(signals)} signals ({skipped} skipped)")
    print(f"Win rate overall: {df['win'].mean():.1%}")

    out = REVIEW_DIR / "swing_features.csv"
    df.to_csv(out, index=False)
    print(f"Saved: {out}")

    # --- Aggregation: win rate by feature quintile ---
    feature_cols = [
        "wick_lo_ratio", "wick_hi_ratio", "body_pct", "vol_ratio",
        "atr_norm_range20", "dist_from_lo20", "dist_from_hi20",
        "consol_ratio", "ema20_slope", "bars_below_ema20",
    ]

    agg_rows = []
    for feat in feature_cols:
        col = df[feat].dropna()
        if len(col) < 20:
            continue
        try:
            df["_q"] = pd.qcut(df[feat], q=5, labels=False, duplicates="drop")
        except Exception:
            continue
        for direction in ["bottom", "top"]:
            sub = df[df["direction"] == direction]
            q_agg = sub.groupby("_q")["win"].agg(n="count", win_rate="mean").reset_index()
            q_agg["feature"]   = feat
            q_agg["direction"] = direction
            agg_rows.append(q_agg)
        df.drop(columns=["_q"], inplace=True)

    if agg_rows:
        agg = pd.concat(agg_rows, ignore_index=True)
        agg_out = REVIEW_DIR / "swing_feature_agg.csv"
        agg.to_csv(agg_out, index=False)
        print(f"Saved aggregation: {agg_out}")

    # --- Quick summary: top discriminating features ---
    print("\n=== Win rate spread by feature quintile (bottom signals) ===")
    bot = df[df["direction"] == "bottom"]
    for feat in feature_cols:
        if df[feat].isna().all():
            continue
        try:
            bot["_q"] = pd.qcut(bot[feat], q=5, labels=False, duplicates="drop")
            q = bot.groupby("_q")["win"].mean()
            spread = q.max() - q.min()
            best_q = q.idxmax()
            print(f"  {feat:25s}  spread={spread:.3f}  best_q={best_q}  "
                  f"range=[{q.min():.2f},{q.max():.2f}]")
            bot.drop(columns=["_q"], inplace=True)
        except Exception:
            pass

    print("\n=== Win rate spread by feature quintile (top signals) ===")
    top = df[df["direction"] == "top"]
    for feat in feature_cols:
        if df[feat].isna().all():
            continue
        try:
            top["_q"] = pd.qcut(top[feat], q=5, labels=False, duplicates="drop")
            q = top.groupby("_q")["win"].mean()
            spread = q.max() - q.min()
            best_q = q.idxmax()
            print(f"  {feat:25s}  spread={spread:.3f}  best_q={best_q}  "
                  f"range=[{q.min():.2f},{q.max():.2f}]")
            top.drop(columns=["_q"], inplace=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
