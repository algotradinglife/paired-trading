"""Backtest divergence signals with multi-TF *context tags* attached.

This run does NOT modify signal confidence. It groups signals by the lower-TF
and (when available) higher-TF context attached at signal emission time, and
reports hit-rate / forward return per bucket so a downstream consumer can
decide its own weighting policy.

Pipeline (for each symbol, per daily signal):
  1. Detect daily divergence signals (gated).
  2. Restrict to the window where BOTH 60min and (if present) weekly exist.
  3. Enrich with engine.divergence.multi_tf_context:
       - enrich_with_higher_tf(... weekly ...)   if {symbol}_weekly.json exists
       - enrich_with_lower_tf(... 60min ...)
  4. Evaluate forward returns at h=5/10/20 on the daily series.
  5. Aggregate by combinations of direction, lower_relation, higher_relation,
     cycle states.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.divergence.multi_tf_context import enrich_with_higher_tf, enrich_with_lower_tf
from engine.divergence.signal import DivergenceSignal
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
# Symbols to include — any with at least daily+60min are evaluated; weekly is optional.
SYMBOLS = ["SPY", "QQQ", "NVDA", "GLD", "DIA", "IWM", "TLT", "XLK", "XLF", "GDX"]
FORWARD_WINDOWS = [5, 10, 20]


@dataclass
class CtxRow:
    symbol: str
    signal: DivergenceSignal
    entry_close: float
    fwd_returns: dict[int, float]
    signed_returns: dict[int, float]
    hits: dict[int, bool]


def load_bars(path: Path) -> pd.DataFrame:
    df, _ = bar_loader.load_snapshot_json(path)
    return df


def _load_sym(sym: str, suffix: str, quant_root: Path | None) -> pd.DataFrame | None:
    """Try BarStore, fall back to JSON in DATA_DIR. Returns None if neither available."""
    if quant_root is not None:
        level = bar_loader.FILENAME_SUFFIX_TO_BARSTORE_LEVEL.get(suffix)
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if level is not None and resolved is not None:
            quant_sym, mic = resolved
            try:
                return bar_loader.load_bars_quant(quant_sym, mic, level, quant_root)
            except Exception as e:
                print(f"quant load {sym}/{suffix}: {e} — falling back to JSON", file=sys.stderr)
    p = DATA_DIR / f"{sym.lower()}_{suffix}.json"
    return load_bars(p) if p.exists() else None


def detect_signals(bars: pd.DataFrame, level_id: str) -> list[DivergenceSignal]:
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
    return detect_all_divergences(units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"], level_id=level_id)


def evaluate_forward(sig: DivergenceSignal, bars: pd.DataFrame) -> CtxRow | None:
    idx = sig.candidate_bar_idx
    if idx + max(FORWARD_WINDOWS) >= len(bars):
        return None
    entry_close = float(bars["close"].iloc[idx])
    fwd, signed, hits = {}, {}, {}
    for h in FORWARD_WINDOWS:
        tgt = float(bars["close"].iloc[idx + h])
        ret = (tgt - entry_close) / entry_close
        s = -ret if sig.direction == "top" else ret
        fwd[h] = ret
        signed[h] = s
        hits[h] = s > 0
    return CtxRow(symbol="", signal=sig, entry_close=entry_close,
                  fwd_returns=fwd, signed_returns=signed, hits=hits)


def run_for_symbol(symbol: str, quant_root: Path | None = None) -> list[CtxRow]:
    daily = _load_sym(symbol, "daily", quant_root)
    sixty = _load_sym(symbol, "60", quant_root)
    if daily is None or sixty is None or daily.empty or sixty.empty:
        return []

    weekly_path = DATA_DIR / f"{symbol.lower()}_weekly.json"
    weekly_quant = _load_sym(symbol, "weekly", quant_root)
    weekly = weekly_quant if weekly_quant is not None else (
        load_bars(weekly_path) if weekly_path.exists() else None
    )
    if weekly is not None and weekly.empty:
        weekly = None

    # Window = intersection of available timeframes
    window_start = sixty["timestamp"].iloc[0]
    window_end = sixty["timestamp"].iloc[-1]
    if weekly is not None:
        window_start = max(window_start, weekly["timestamp"].iloc[0])
        window_end = min(window_end, weekly["timestamp"].iloc[-1])

    all_signals = detect_signals(daily, level_id="D")
    in_window = [
        s for s in all_signals
        if window_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= window_end
    ]

    enriched = in_window
    if weekly is not None:
        enriched = enrich_with_higher_tf(enriched, daily, weekly, higher_tf_level_id="W")
    enriched = enrich_with_lower_tf(enriched, daily, sixty, lower_tf_level_id="1h")

    rows: list[CtxRow] = []
    for sig in enriched:
        row = evaluate_forward(sig, daily)
        if row is None:
            continue
        row.symbol = symbol
        rows.append(row)
    return rows


def aggregate(rows: list[CtxRow]) -> pd.DataFrame:
    records = []
    for r in rows:
        ctx = r.signal.multi_tf_context or {}
        for h in FORWARD_WINDOWS:
            records.append({
                "symbol": r.symbol,
                "date": r.signal.timestamp.strftime("%Y-%m-%d"),
                "direction": r.signal.direction,
                "subtype": r.signal.subtype,
                "level": r.signal.level,
                "confidence": r.signal.confidence,
                "lower_side": ctx.get("lower_tf_side", "n/a"),
                "lower_cycle": ctx.get("lower_tf_cycle_state", "n/a"),
                "lower_relation": ctx.get("lower_relation", ctx.get("relation", "n/a")),
                "higher_side": ctx.get("higher_tf_side", "n/a"),
                "higher_cycle": ctx.get("higher_tf_cycle_state", "n/a"),
                "higher_relation": ctx.get("higher_relation", "n/a"),
                "horizon": h,
                "hit": r.hits[h],
                "signed_return": r.signed_returns[h],
            })
    return pd.DataFrame(records)


def fmt_band(df: pd.DataFrame, group_cols: list[str], title: str, h: int = 20) -> None:
    sub = df[df["horizon"] == h]
    g = sub.groupby(group_cols, dropna=False)
    out = pd.DataFrame({
        "n": g.size(),
        "hit_rate": g["hit"].mean(),
        "avg_ret_pct": g["signed_return"].mean() * 100,
        "median_ret_pct": g["signed_return"].median() * 100,
    }).reset_index()
    out["hit_rate"] = (out["hit_rate"] * 100).round(1).astype(str) + "%"
    out["avg_ret_pct"] = out["avg_ret_pct"].round(2).astype(str) + "%"
    out["median_ret_pct"] = out["median_ret_pct"].round(2).astype(str) + "%"
    print(f"\n=== {title} (horizon = {h}) ===")
    print(out.to_string(index=False))


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-csv", type=str, default=None,
                        help="Optional path to dump signal-level rows for external review")
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                        help="quant-data Parquet root (default: data/quant/)")
    args = parser.parse_args()
    quant_root = args.quant_data_root

    all_rows: list[CtxRow] = []
    for sym in SYMBOLS:
        rows = run_for_symbol(sym, quant_root=quant_root)
        sixty = _load_sym(sym, "60", quant_root)
        rng = ""
        if sixty is not None and not sixty.empty:
            rng = (sixty["timestamp"].iloc[0].strftime("%Y-%m-%d")
                   + " → " + sixty["timestamp"].iloc[-1].strftime("%Y-%m-%d"))
        n_ctx = sum(1 for r in rows if r.signal.multi_tf_context)
        print(f"  {sym}: {len(rows)} signals  ({n_ctx} with 60m context)  window={rng}")
        all_rows.extend(rows)

    if not all_rows:
        print("\nNo signals in overlap window.")
        return 0

    df = aggregate(all_rows)

    if args.export_csv:
        export_path = Path(args.export_csv)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(export_path, index=False)
        print(f"\nSignal-level rows exported → {export_path}")
    print(f"\nTotal: {len(all_rows)} signals × {len(FORWARD_WINDOWS)} horizons "
          f"= {len(df)} rows")

    has_weekly = (df["higher_relation"] != "n/a").any()

    # Baseline (no context)
    fmt_band(df, ["direction"], "Direction only (baseline)", h=20)

    # Lower-TF cuts (always available)
    fmt_band(df, ["direction", "lower_relation"], "Direction × lower_relation", h=20)
    fmt_band(df, ["direction", "lower_cycle"], "Direction × lower cycle_state", h=20)

    # Three-way lower drill
    fmt_band(df, ["direction", "lower_relation", "lower_cycle"],
             "Direction × lower_relation × lower cycle_state", h=20)

    # Higher-TF cuts (only when weekly is loaded)
    if has_weekly:
        fmt_band(df, ["direction", "higher_relation"],
                 "Direction × higher_relation (weekly trend)", h=20)
        fmt_band(df, ["direction", "higher_cycle"],
                 "Direction × higher cycle_state (weekly cycle)", h=20)
        fmt_band(df, ["direction", "lower_relation", "higher_relation"],
                 "Direction × lower_relation × higher_relation (three-TF)", h=20)
        fmt_band(df, ["direction", "lower_relation", "higher_relation"],
                 "Direction × lower_relation × higher_relation (three-TF)", h=10)

    # Subtype drills under bottom (dominant class)
    fmt_band(df[df["direction"] == "bottom"], ["subtype", "lower_cycle"],
             "Bottom: subtype × lower cycle_state", h=20)
    fmt_band(df[df["direction"] == "top"], ["lower_relation", "lower_cycle"],
             "Top: lower_relation × lower cycle_state", h=20)

    # Confidence band overlays
    def band(c):
        if c >= 0.80: return "confirmed"
        if c >= 0.65: return "candidate"
        if c >= 0.50: return "forming"
        if c >= 0.30: return "watching"
        return "dormant"
    df["conf_band"] = df["confidence"].apply(band)
    fmt_band(df, ["conf_band", "lower_cycle"], "Conf band × lower cycle_state", h=20)
    if has_weekly:
        fmt_band(df, ["conf_band", "higher_relation"], "Conf band × higher_relation", h=20)

    return 0


if __name__ == "__main__":
    sys.exit(main())
