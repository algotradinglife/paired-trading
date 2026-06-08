"""PA TOP multi-dimensional walk-forward grid validation.

Walk-forward K=3 validation of ``PATopDetector`` to identify which
``phase × h_rel × context × top_divergence`` cells produce positive
EV.  Output feeds the calibration of ``PATopDetector.policy_weight()``,
which is currently a no-emit 0.0 placeholder.

Pools:
  - us_60min            : 10 ETFs (matches backtest_pa_swing us_60min),
                          h_bars = daily
  - cn_metal_daily      : 5 SHFE/INE metals (rb/cu/au/ag/sc),
                          h_bars = 60min (cross-TF DIF anchor)
  - cn_bond_daily       : 3 CFFEX bond futures (tf/t/ts),
                          h_bars = 60min
  - cn_commodity_daily  : CN_COMMODITY pool minus cn_metal_daily and rb
                          (i.e. m/i/j/jm/p/y/ta/ma/cf/sr), h_bars = 60min

Top-divergence helper (in-script — does NOT add APIs to pa_detector):
  An in-script top-side divergence flag computed from the MACD
  histogram on the entry bar: ``hist[idx] < hist[idx-N]`` AND
  ``hist[idx] < 0 OR hist[idx-N] > 0`` — i.e. histogram is weaker now
  than N bars ago, consistent with momentum exhaustion at a top.
  N defaults to 5 bars.

Walk-forward folds (K=3, mirrors backtest_pa_us_k3.py):
  IS  : <= 2022-12-31
  OOS1: 2023-01-01 - 2023-12-31
  OOS2: 2024-01-01 - 2024-12-31
  OOS3: > 2025-01-01

Output:
  - /Users/huhan/code/trading/macd-momentum/data/review/pa_top_wf_grid.csv
      Per (pool × phase × h_rel × context × top_div) cell breakdown
      with n, EV and per-fold EV / n.

Usage:
  uv run python scripts/backtest_pa_top_grid.py
  uv run python scripts/backtest_pa_top_grid.py --pool us_60min
  uv run python scripts/backtest_pa_top_grid.py --min-cell-n 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.pa_context_classifier import classify_context
from engine.divergence.pa_detector import PATopDetector
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
REVIEW_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "review"

# Simulation parameters mirror BOTTOM simulate_trade in backtest_pa_swing.py
# but flip direction (short).
ATR_PERIOD = 14
MIN_GAP    = 10

# Frame defaults (counter_trend = C4 baseline).
FRAME_DEFAULTS: dict[str, dict] = {
    "counter_trend": dict(
        stop_mult=1.5,
        max_hold=40,
        phase_allow=None,        # No phase gate; report all rows.
    ),
    "trend_follow": dict(
        stop_mult=2.5,
        max_hold=80,
        # Reject BULL phase entries — trend-following puts should not
        # fade an uptrend. Allow BEAR / TR / TR_FORMING (and UNCLEAR
        # for completeness, since the structure detector occasionally
        # leaves bars unclassified mid-window).
        phase_allow={"BEAR", "TR", "TR_FORMING", "UNCLEAR"},
    ),
}

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")

# Top divergence: hist[idx] weaker than hist[idx-DIV_LOOKBACK]
DIV_LOOKBACK = 5

POOLS: dict[str, dict] = {
    "us_60min": dict(
        symbols=["spy", "qqq", "dia", "iwm", "gld", "gdx", "tlt",
                 "xlf", "xlk", "nvda"],
        suffix="_60",
        h_suffix="_daily",
        h_lookback=20,
        run_context=False,   # context classifier is daily-only
    ),
    "cn_metal_daily": dict(
        symbols=["kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au",
                 "kq_m_shfe_ag", "kq_m_ine_sc"],
        suffix="_daily",
        h_suffix="_60",
        h_lookback=8,
        run_context=True,
    ),
    "cn_bond_daily": dict(
        symbols=["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
        suffix="_daily",
        h_suffix="_60",
        h_lookback=8,
        run_context=True,
    ),
    "cn_commodity_daily": dict(
        symbols=[
            "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
            "kq_m_dce_p", "kq_m_dce_y",
            "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        ],
        suffix="_daily",
        h_suffix="_60",
        h_lookback=8,
        run_context=True,
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str) -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_short(
    bars: pd.DataFrame,
    entry_idx: int,
    atr_series: pd.Series,
    stop_mult: float = 1.5,
    max_hold: int = 40,
) -> float | None:
    """Short-side mirror of simulate_trade in backtest_pa_swing.py.

    Stop = entry + risk; TP1 = entry - risk; TP2 = entry - 2 * risk.
    Hit TP1 first (trail to BE), TP2 = +1.5R; stopped = -1.0R;
    max-hold marked at +/- mark in R units.
    """
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
                return 0.0   # trailed to BE on TP1
            if lo <= tp2:
                return 1.5
            if offset == max_hold:
                # Convert remaining drift into R units (short: profit = entry - cl)
                return 0.5 + 0.5 * float(np.clip((entry - cl) / risk, -3, 3))
    idx_fin = min(entry_idx + max_hold, len(bars) - 1)
    return float(np.clip((entry - float(bars["close"].iloc[idx_fin])) / risk, -3, 3))


def top_divergence_flag(hist: pd.Series, idx: int, lookback: int = DIV_LOOKBACK) -> bool:
    """In-script top-side divergence flag.

    Definition: histogram value at idx is weaker (lower) than at
    idx-lookback, indicating momentum is fading even as price prints
    a higher swing high.  Skip if either point is NaN.
    """
    if idx - lookback < 0:
        return False
    cur = float(hist.iloc[idx])
    prev = float(hist.iloc[idx - lookback])
    if not (np.isfinite(cur) and np.isfinite(prev)):
        return False
    # Weakening: histogram falling.  Don't double-fire on already-weak runs:
    # require at least the previous point to be > 0 (it was a bullish push)
    # OR the current to be < 0 (sustained weakness).
    return cur < prev and (prev > 0 or cur < 0)


def fold_label(ts: pd.Timestamp) -> str:
    if ts <= CUTOFF_IS:
        return "IS"
    if ts <= CUTOFF_OOS1:
        return "OOS1"
    if ts <= CUTOFF_OOS2:
        return "OOS2"
    return "OOS3"


# ---------------------------------------------------------------------------
# Per-pool scan
# ---------------------------------------------------------------------------

def scan_pool(
    pool: str,
    cfg: dict,
    bars_dir: Path,
    *,
    stop_mult: float,
    max_hold: int,
    phase_allow: set[str] | None,
) -> pd.DataFrame:
    records: list[dict] = []
    struct_det = PAStructureDetector()

    for sym in cfg["symbols"]:
        bars = load_bars(sym, bars_dir, cfg["suffix"])
        if bars is None or len(bars) < 100:
            print(f"  [{pool}] [SKIP] {sym}: no data")
            continue

        h_bars = (
            load_bars(sym, bars_dir, cfg["h_suffix"])
            if cfg.get("h_suffix") else None
        )

        atr     = compute_atr(bars)
        macd_df = compute_macd(bars["close"])
        hist    = macd_df["hist"]

        if cfg.get("run_context"):
            ema20 = bars["close"].ewm(span=20, adjust=False).mean()
            ema60 = bars["close"].ewm(span=60, adjust=False).mean()
        else:
            ema20 = ema60 = None

        det = PATopDetector(
            min_l_legs=2,
            min_quality=0.3,
            ema_threshold=0.0,
            min_gap=MIN_GAP,
            h_lookback=cfg.get("h_lookback", 8),
        )
        sigs = det.scan(bars, h_bars=h_bars)

        n_total = len(sigs)
        n_opp   = sum(1 for s in sigs if s.higher_tf_relation == "opposing")
        print(f"  [{pool}] {sym}: signals={n_total}  h=opp={n_opp}")

        for sig in sigs:
            struct = struct_det.detect(bars, up_to_idx=sig.bar_idx)
            phase = struct.phase

            # Frame-level phase gate: trend_follow drops BULL entries.
            if phase_allow is not None and phase not in phase_allow:
                continue

            r = simulate_short(
                bars, sig.bar_idx, atr,
                stop_mult=stop_mult, max_hold=max_hold,
            )
            if r is None:
                continue

            if cfg.get("run_context"):
                ctx = classify_context(bars, sig.bar_idx, macd_df, ema20, ema60)
            else:
                ctx = None

            div = top_divergence_flag(hist, sig.bar_idx)

            ts = sig.timestamp
            records.append({
                "pool":              pool,
                "symbol":            sym,
                "bar_idx":           sig.bar_idx,
                "timestamp":         ts,
                "fold":              fold_label(ts),
                "r":                 r,
                "phase":             phase,
                "h_rel":             sig.higher_tf_relation or "none",
                "context":           ctx if ctx is not None else "none",
                "top_div":           bool(div),
                "confidence":        sig.confidence,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Grid aggregation
# ---------------------------------------------------------------------------

GRID_KEYS = ["pool", "phase", "h_rel", "context", "top_div"]


def aggregate_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Cell rollup with per-fold EV/n.

    OOS counts use OOS1+OOS2+OOS3; IS is reported but not part of
    promotion logic.
    """
    rows: list[dict] = []
    for keys, sub in df.groupby(GRID_KEYS, dropna=False):
        oos = sub[sub["fold"] != "IS"]
        is_  = sub[sub["fold"] == "IS"]
        n_total = len(sub)
        n_oos   = len(oos)
        ev_oos  = oos["r"].mean() if n_oos else np.nan
        hit_oos = (oos["r"] > 0).mean() if n_oos else np.nan
        ev_is   = is_["r"].mean() if len(is_) else np.nan
        n_is    = len(is_)

        fold_evs = {}
        fold_ns  = {}
        signs    = []
        for f in ["OOS1", "OOS2", "OOS3"]:
            g = sub[sub["fold"] == f]
            fold_ns[f] = len(g)
            if len(g):
                fold_evs[f] = g["r"].mean()
                signs.append(np.sign(g["r"].mean()))
            else:
                fold_evs[f] = np.nan

        signs_valid = [s for s in signs if not np.isnan(s)]
        if signs_valid:
            stable_sign = all(s == signs_valid[0] for s in signs_valid)
        else:
            stable_sign = False

        rows.append({
            **dict(zip(GRID_KEYS, keys)),
            "n_total":     n_total,
            "n_is":        n_is,
            "n_oos":       n_oos,
            "ev_is":       round(ev_is, 4) if not np.isnan(ev_is) else np.nan,
            "ev_oos":      round(ev_oos, 4) if not np.isnan(ev_oos) else np.nan,
            "hit_oos":     round(hit_oos, 3) if not np.isnan(hit_oos) else np.nan,
            "ev_f1":       round(fold_evs["OOS1"], 4) if not np.isnan(fold_evs["OOS1"]) else np.nan,
            "n_f1":        fold_ns["OOS1"],
            "ev_f2":       round(fold_evs["OOS2"], 4) if not np.isnan(fold_evs["OOS2"]) else np.nan,
            "n_f2":        fold_ns["OOS2"],
            "ev_f3":       round(fold_evs["OOS3"], 4) if not np.isnan(fold_evs["OOS3"]) else np.nan,
            "n_f3":        fold_ns["OOS3"],
            "stable_sign": stable_sign,
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["pool", "ev_oos"], ascending=[True, False])
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool",        default="all",
                        choices=["all", *POOLS.keys()])
    parser.add_argument("--bars-dir",    type=Path, default=DEFAULT_BARS_DIR)
    parser.add_argument("--min-cell-n",  type=int, default=20,
                        help="Minimum OOS n for a cell to be promoted "
                             "in the summary table.")
    parser.add_argument("--frame",       default="counter_trend",
                        choices=list(FRAME_DEFAULTS.keys()),
                        help="Simulation frame. counter_trend = C4 baseline "
                             "(1.5xATR / 40-bar / no phase gate). trend_follow "
                             "= 2.5xATR / 80-bar / phase∈{BEAR,TR,TR_FORMING}.")
    parser.add_argument("--out-csv",     type=Path, default=None,
                        help="Output grid CSV. Default depends on --frame.")
    args = parser.parse_args()

    frame_cfg = FRAME_DEFAULTS[args.frame]
    stop_mult: float = frame_cfg["stop_mult"]
    max_hold: int = frame_cfg["max_hold"]
    phase_allow: set[str] | None = frame_cfg["phase_allow"]

    if args.out_csv is None:
        if args.frame == "counter_trend":
            args.out_csv = REVIEW_DIR_DEFAULT / "pa_top_wf_grid.csv"
        else:
            args.out_csv = (
                REVIEW_DIR_DEFAULT / f"pa_top_wf_grid_{args.frame}.csv"
            )

    selected = list(POOLS) if args.pool == "all" else [args.pool]

    print(f"PA TOP grid backtest — frame={args.frame}  pools: {selected}")
    print(f"K=3 folds: IS<={CUTOFF_IS.date()}  OOS1<={CUTOFF_OOS1.date()}  "
          f"OOS2<={CUTOFF_OOS2.date()}  OOS3>")
    print(f"stop={stop_mult}xATR  max_hold={max_hold}  min_gap={MIN_GAP}  "
          f"min_quality=0.3  div_lookback={DIV_LOOKBACK}  "
          f"phase_allow={'<all>' if phase_allow is None else sorted(phase_allow)}")
    print("=" * 80)

    all_signals: list[pd.DataFrame] = []
    for pool in selected:
        cfg = POOLS[pool]
        print(f"\n-- {pool} ({len(cfg['symbols'])} symbols) --")
        df = scan_pool(
            pool, cfg, args.bars_dir,
            stop_mult=stop_mult, max_hold=max_hold,
            phase_allow=phase_allow,
        )
        if df.empty:
            print(f"  [{pool}] no signals")
            continue
        all_signals.append(df)
        print(f"  [{pool}] total fires = {len(df)}")

    if not all_signals:
        print("No signals across any pool.")
        return

    raw = pd.concat(all_signals, ignore_index=True)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)

    grid = aggregate_grid(raw)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    grid.to_csv(args.out_csv, index=False)
    print(f"\nGrid written to {args.out_csv}  (rows={len(grid)})")

    # --- Surface promote / fail / inconclusive cells ---
    if grid.empty:
        return

    promoted = grid[
        (grid["n_oos"] >= args.min_cell_n)
        & (grid["stable_sign"])
        & (grid["ev_oos"] > 0)
    ].copy()
    failed   = grid[
        (grid["n_oos"] >= args.min_cell_n)
        & ((~grid["stable_sign"]) | (grid["ev_oos"] <= 0))
    ].copy()
    inconc   = grid[grid["n_oos"] < args.min_cell_n].copy()

    def show(label: str, sub: pd.DataFrame, n: int = 20) -> None:
        print(f"\n== {label} (n_oos>={args.min_cell_n}{', stable +ev' if 'pass' in label.lower() else ''}) ==")
        if sub.empty:
            print("  (none)")
            return
        for _, r in sub.head(n).iterrows():
            print(
                f"  pool={r['pool']:>20s}  phase={r['phase']:>10s}  "
                f"h_rel={r['h_rel']:>10s}  ctx={r['context']:>4s}  "
                f"div={str(r['top_div']):>5s}  "
                f"n_oos={int(r['n_oos']):>3d}  "
                f"EV_oos={r['ev_oos']:+.3f}R  hit={r['hit_oos']:.0%}  "
                f"F1={r['ev_f1']:+.3f}(n={int(r['n_f1'])})  "
                f"F2={r['ev_f2']:+.3f}(n={int(r['n_f2'])})  "
                f"F3={r['ev_f3']:+.3f}(n={int(r['n_f3'])})"
            )

    show("PROMOTE CANDIDATES (stable sign + EV_oos > 0)", promoted)
    show("FAILED (large n, unstable sign or EV_oos <= 0)", failed.sort_values("ev_oos"))
    print(f"\nInconclusive cells (n_oos<{args.min_cell_n}): {len(inconc)} rows (full data in CSV)")

    # Pool-level summary
    print("\n== Per-pool top-5 promote candidates ==")
    for pool in selected:
        p_sub = promoted[promoted["pool"] == pool].head(5)
        if p_sub.empty:
            print(f"  {pool}: (none passed)")
            continue
        print(f"  {pool}:")
        for _, r in p_sub.iterrows():
            print(
                f"    phase={r['phase']:>10s} h_rel={r['h_rel']:>10s} "
                f"ctx={r['context']:>4s} div={str(r['top_div']):>5s} "
                f"n_oos={int(r['n_oos']):>3d}  EV={r['ev_oos']:+.3f}R"
            )


if __name__ == "__main__":
    main()
