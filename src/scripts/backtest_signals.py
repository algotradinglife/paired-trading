"""Backtest divergence signals: forward-return + hit-rate evaluation.

Project scope reminder: this validates the *analysis layer*. It scores whether
each emitted signal points in the correct direction over multiple forward
windows. It does NOT simulate trades or compute P&L net of costs — that work
belongs to the downstream trading project.

Method:
  For each detected signal:
    - direction = top → predicts price decline
    - direction = bottom → predicts price rise
    - For each forward horizon (5, 10, 20 bars):
        * forward_return = (close[t+N] - close[t]) / close[t]
        * signed_return  = forward_return aligned to prediction
        * hit            = signed_return > 0
        * mfe / mae      = max favorable / adverse excursion within window

  Then aggregate by:
    - subtype (standard / weakness / hidden)
    - confidence band (mid 0.50-0.65, candidate 0.65-0.80, confirmed 0.80+)
    - direction (top / bottom)
    - horizon

Signals too close to the end of data (insufficient forward bars) are skipped.

Usage:
  uv run python scripts/backtest_signals.py [snapshot] [min_conf]
  uv run python scripts/backtest_signals.py --all   # run all snapshots aggregated
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.divergence.signal import DivergenceSignal
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Confidence bands per doc/10 §2
CONF_BANDS = [
    ("watching", 0.30, 0.50),
    ("forming", 0.50, 0.65),
    ("candidate", 0.65, 0.80),
    ("confirmed", 0.80, 1.01),
]

FORWARD_WINDOWS = [5, 10, 20]


@dataclass
class EvalRow:
    snapshot: str
    level_id: str
    signal: DivergenceSignal
    entry_idx: int
    entry_close: float
    fwd_returns: dict[int, float]       # horizon → forward return (raw, signed by price)
    signed_returns: dict[int, float]    # horizon → return aligned to prediction direction
    hits: dict[int, bool]
    mfes: dict[int, float]              # max favorable excursion (in direction of prediction)
    maes: dict[int, float]              # max adverse excursion (opposite of prediction)


def conf_band(conf: float) -> str:
    for name, lo, hi in CONF_BANDS:
        if lo <= conf < hi:
            return name
    return "dormant"


def load_snapshot(path: Path) -> pd.DataFrame:
    df, _ = bar_loader.load_snapshot_json(path)
    return df


def evaluate_signal(
    sig: DivergenceSignal,
    bars: pd.DataFrame,
    *,
    horizons: list[int],
) -> EvalRow | None:
    """Compute forward returns + MFE/MAE for one signal. Returns None if signal
    has insufficient forward bars."""
    entry_idx = sig.candidate_bar_idx
    max_h = max(horizons)
    if entry_idx + max_h >= len(bars):
        return None

    entry_close = float(bars["close"].iloc[entry_idx])

    fwd_returns: dict[int, float] = {}
    signed_returns: dict[int, float] = {}
    hits: dict[int, bool] = {}
    mfes: dict[int, float] = {}
    maes: dict[int, float] = {}

    for h in horizons:
        target_close = float(bars["close"].iloc[entry_idx + h])
        fwd_ret = (target_close - entry_close) / entry_close
        # Direction-aligned signed return:
        #   top signal: profit if price goes down → signed = -fwd_ret
        #   bottom signal: profit if price goes up → signed = +fwd_ret
        signed = -fwd_ret if sig.direction == "top" else fwd_ret

        window = bars.iloc[entry_idx + 1 : entry_idx + 1 + h]
        max_high = float(window["high"].max())
        min_low = float(window["low"].min())
        max_up_ret = (max_high - entry_close) / entry_close      # ≥ 0
        max_down_ret = (entry_close - min_low) / entry_close      # ≥ 0

        if sig.direction == "top":
            mfe = max_down_ret      # max favorable = max price drop
            mae = max_up_ret        # max adverse = max price rise
        else:
            mfe = max_up_ret
            mae = max_down_ret

        fwd_returns[h] = fwd_ret
        signed_returns[h] = signed
        hits[h] = signed > 0
        mfes[h] = mfe
        maes[h] = mae

    return EvalRow(
        snapshot="",
        level_id=sig.level_id,
        signal=sig,
        entry_idx=entry_idx,
        entry_close=entry_close,
        fwd_returns=fwd_returns,
        signed_returns=signed_returns,
        hits=hits,
        mfes=mfes,
        maes=maes,
    )


def run_pipeline_and_eval(
    snapshot_path: Path,
    *,
    min_conf: float,
    horizons: list[int],
    bars: pd.DataFrame | None = None,
) -> list[EvalRow]:
    if bars is None:
        bars = load_snapshot(snapshot_path)
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )
    signals = detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id=snapshot_path.stem,
    )
    signals = [s for s in signals if s.confidence >= min_conf]

    rows: list[EvalRow] = []
    for sig in signals:
        row = evaluate_signal(sig, bars, horizons=horizons)
        if row is None:
            continue
        row.snapshot = snapshot_path.stem
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(rows: list[EvalRow], horizons: list[int]) -> pd.DataFrame:
    """Build a long-form DataFrame for aggregation."""
    records = []
    for r in rows:
        for h in horizons:
            records.append({
                "snapshot": r.snapshot,
                "level": r.signal.level,
                "subtype": r.signal.subtype,
                "direction": r.signal.direction,
                "conf_band": conf_band(r.signal.confidence),
                "confidence": r.signal.confidence,
                "horizon": h,
                "fwd_return": r.fwd_returns[h],
                "signed_return": r.signed_returns[h],
                "hit": r.hits[h],
                "mfe": r.mfes[h],
                "mae": r.maes[h],
            })
    return pd.DataFrame(records)


def summary_by_group(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = df.groupby(group_cols, dropna=False)
    summary = pd.DataFrame({
        "n": grouped.size(),
        "hit_rate": grouped["hit"].mean(),
        "avg_signed_ret_pct": grouped["signed_return"].mean() * 100,
        "median_signed_ret_pct": grouped["signed_return"].median() * 100,
        "avg_mfe_pct": grouped["mfe"].mean() * 100,
        "avg_mae_pct": grouped["mae"].mean() * 100,
        "mfe_mae_ratio": grouped["mfe"].mean() / grouped["mae"].mean(),
    }).reset_index()
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x:+.2f}%"


def print_table(title: str, df: pd.DataFrame, group_cols: list[str]) -> None:
    print(f"\n=== {title} ===")
    if df.empty:
        print("  (no data)")
        return
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    # Format display
    show = df.copy()
    show["hit_rate"] = (show["hit_rate"] * 100).round(1).astype(str) + "%"
    show["avg_signed_ret_pct"] = show["avg_signed_ret_pct"].round(2).astype(str) + "%"
    show["median_signed_ret_pct"] = show["median_signed_ret_pct"].round(2).astype(str) + "%"
    show["avg_mfe_pct"] = show["avg_mfe_pct"].round(2).astype(str) + "%"
    show["avg_mae_pct"] = show["avg_mae_pct"].round(2).astype(str) + "%"
    show["mfe_mae_ratio"] = show["mfe_mae_ratio"].round(2)
    show["n"] = show["n"].astype(int)
    print(show.to_string(index=False))


def main(args: list[str]) -> int:
    # Pre-extract --quant-data-root (backward-compat: callers like backtest_no_gate pass plain list)
    quant_root: Path = bar_loader.DEFAULT_QUANT_ROOT
    clean: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--quant-data-root" and i + 1 < len(args):
            quant_root = Path(args[i + 1])
            i += 2
        elif args[i].startswith("--quant-data-root="):
            quant_root = Path(args[i].split("=", 1)[1])
            i += 1
        else:
            clean.append(args[i])
            i += 1
    args = clean

    if not args or args[0] == "--all":
        snapshot_names = ["spy_60min.json", "spy_daily.json", "spy_weekly.json"]
    elif args[0] == "--daily":
        # Compare all *_daily.json snapshots in data/raw
        snapshot_names = sorted(p.name for p in (DATA_DIR / "raw").glob("*_daily.json"))
    else:
        snapshot_names = [args[0]]

    min_conf = float(args[1]) if len(args) > 1 else 0.5

    all_rows: list[EvalRow] = []
    for sn in snapshot_names:
        preloaded: pd.DataFrame | None = None
        if quant_root is not None:
            parsed = bar_loader.parse_snapshot_name(sn)
            if parsed is not None:
                sym, mic, level = parsed
                try:
                    preloaded = bar_loader.load_bars_quant(sym, mic, level, quant_root)
                except Exception as e:
                    print(f"quant load {sn}: {e} — falling back to JSON", file=sys.stderr)
        path = DATA_DIR / "raw" / sn
        if preloaded is None and not path.exists():
            print(f"Skip {sn} — missing snapshot", file=sys.stderr)
            continue
        rows = run_pipeline_and_eval(path, min_conf=min_conf, horizons=FORWARD_WINDOWS, bars=preloaded)
        print(f"{sn}: {len(rows)} evaluable signals (≥{min_conf})")
        all_rows.extend(rows)

    if not all_rows:
        print("No evaluable signals.")
        return 0

    df = aggregate(all_rows, FORWARD_WINDOWS)
    print(f"\nTotal evaluable signal-horizons: {len(df)}")
    print(f"Total signal events: {len(all_rows)}")

    # Per-snapshot × horizon
    s1 = summary_by_group(df, ["snapshot", "horizon"])
    print_table("Per snapshot × horizon", s1, ["snapshot", "horizon"])

    # Per subtype × horizon (pooled across snapshots)
    s2 = summary_by_group(df, ["subtype", "horizon"])
    print_table("Per subtype × horizon (pooled)", s2, ["subtype", "horizon"])

    # Per direction × horizon
    s3 = summary_by_group(df, ["direction", "horizon"])
    print_table("Per direction × horizon (pooled)", s3, ["direction", "horizon"])

    # Per confidence band × horizon
    s4 = summary_by_group(df, ["conf_band", "horizon"])
    print_table("Per confidence band × horizon (pooled)", s4, ["conf_band", "horizon"])

    # Per subtype × conf_band at horizon=10
    df10 = df[df["horizon"] == 10]
    if not df10.empty:
        s5 = summary_by_group(df10, ["subtype", "conf_band"])
        print_table("Subtype × confidence band at horizon=10", s5, ["subtype", "conf_band"])

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
