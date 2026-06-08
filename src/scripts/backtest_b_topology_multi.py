"""B-topology (D + 15min + 1h) multi-symbol validation.

Runs the alternate topology across all 10 symbols to validate the
'top + higher_60m_opposing' bucket discovered in the SPY-only run
(n=4, 75% hit). Goal: see if this pattern survives expansion or
collapses as more data arrives.

Output:
  data/review/b_topology_signals_all.csv  (per-signal × per-horizon)
  printout — key aggregations focused on the candidate bucket
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.multi_tf_context import (
    enrich_with_higher_tf,
    enrich_with_lower_tf,
)
from engine.divergence.signal import DivergenceSignal
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


OUT_DIR = _default_review_dir()
SYMBOLS = ["SPY", "QQQ", "NVDA", "GLD", "DIA", "IWM", "TLT", "XLK", "XLF", "GDX"]
FORWARD_WINDOWS = [5, 10, 20]


@dataclass
class Row:
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


def detect_signals(bars: pd.DataFrame, level_id: str):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
    return detect_all_divergences(units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"], level_id="D")


def evaluate_forward(symbol, sig, bars):
    idx = sig.candidate_bar_idx
    if idx + max(FORWARD_WINDOWS) >= len(bars):
        return None
    entry = float(bars["close"].iloc[idx])
    fwd, signed, hits = {}, {}, {}
    for h in FORWARD_WINDOWS:
        tgt = float(bars["close"].iloc[idx + h])
        ret = (tgt - entry) / entry
        s = -ret if sig.direction == "top" else ret
        fwd[h] = ret
        signed[h] = s
        hits[h] = s > 0
    return Row(symbol=symbol, signal=sig, entry_close=entry,
               fwd_returns=fwd, signed_returns=signed, hits=hits)


def run_b_topology_for_symbol(sym: str, quant_root: Path | None = None) -> list[Row]:
    daily = _load_sym(sym, "daily", quant_root)
    sixty = _load_sym(sym, "60", quant_root)
    fifteen = _load_sym(sym, "15", quant_root)
    if daily is None or sixty is None or fifteen is None:
        return []

    sigs = detect_signals(daily, level_id="D")
    window_start = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    window_end = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    in_window = [s for s in sigs
                 if window_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= window_end]

    # B topology: higher = 1h (was W), lower = 15m (was 1h)
    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    enriched = enrich_with_lower_tf(enriched, daily, fifteen, lower_tf_level_id="15m")

    rows = []
    for sig in enriched:
        r = evaluate_forward(sym, sig, daily)
        if r is not None:
            rows.append(r)
    return rows


def rows_to_df(rows: list[Row]) -> pd.DataFrame:
    records = []
    for r in rows:
        ctx = r.signal.multi_tf_context or {}
        decision = apply_policy(r.signal)
        for h in FORWARD_WINDOWS:
            records.append({
                "symbol": r.symbol,
                "date": r.signal.timestamp.strftime("%Y-%m-%d"),
                "direction": r.signal.direction,
                "subtype": r.signal.subtype,
                "level": r.signal.level,
                "confidence": r.signal.confidence,
                "rule_id": decision.rule_id or "—",
                "lower_side": ctx.get("lower_tf_side", "n/a"),     # 15m here
                "lower_cycle": ctx.get("lower_tf_cycle_state", "n/a"),
                "lower_relation": ctx.get("lower_relation", "n/a"),
                "higher_side": ctx.get("higher_tf_side", "n/a"),   # 1h here
                "higher_cycle": ctx.get("higher_tf_cycle_state", "n/a"),
                "higher_relation": ctx.get("higher_relation", "n/a"),
                "horizon": h,
                "hit": r.hits[h],
                "signed_return": r.signed_returns[h],
            })
    return pd.DataFrame(records)


def fmt_band(df, group_cols, title, h=20):
    sub = df[df["horizon"] == h]
    if sub.empty:
        print(f"\n=== {title} (h={h}) === (empty)")
        return
    g = sub.groupby(group_cols, dropna=False)
    out = pd.DataFrame({
        "n": g.size(),
        "hit_rate": g["hit"].mean(),
        "avg_ret%": g["signed_return"].mean() * 100,
        "median%": g["signed_return"].median() * 100,
    }).reset_index()
    out["hit_rate"] = (out["hit_rate"] * 100).round(1).astype(str) + "%"
    out["avg_ret%"] = out["avg_ret%"].round(2).astype(str) + "%"
    out["median%"] = out["median%"].round(2).astype(str) + "%"
    print(f"\n=== {title} (h={h}) ===")
    print(out.to_string(index=False))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                        help="quant-data Parquet root (default: data/quant/)")
    args = parser.parse_args()
    quant_root = args.quant_data_root

    all_rows = []
    for sym in SYMBOLS:
        rows = run_b_topology_for_symbol(sym, quant_root=quant_root)
        n_top = sum(1 for r in rows if r.signal.direction == "top")
        n_bottom = sum(1 for r in rows if r.signal.direction == "bottom")
        print(f"  {sym}: {len(rows)} signals ({n_bottom} bottom, {n_top} top)")
        all_rows.extend(rows)

    df = rows_to_df(all_rows)
    out_path = OUT_DIR / "b_topology_signals_all.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nTotal: {len(all_rows)} signals → {out_path}")

    if df.empty:
        return

    # Direction baseline
    fmt_band(df, ["direction"], "Direction baseline (B topology)")

    # Per rule
    fmt_band(df, ["rule_id"], "Per rule_id")

    # The headline question: top × higher_relation (1h state at signal time)
    fmt_band(df[df["direction"] == "top"], ["higher_relation"],
             "TOP × higher_relation (1h state) — KEY VALIDATION")

    # And the three-way drill for top
    fmt_band(df[df["direction"] == "top"], ["lower_relation", "higher_relation"],
             "TOP × lower(15m) × higher(1h)")

    # Same drill for bottom (sanity check)
    fmt_band(df[df["direction"] == "bottom"], ["higher_relation"],
             "BOTTOM × higher_relation (1h state)")

    fmt_band(df[df["direction"] == "bottom"], ["lower_relation", "higher_relation"],
             "BOTTOM × lower(15m) × higher(1h)")

    # Spotlight: the candidate bucket "top + higher=opposing"
    print("\n\n████ Spotlight: top + higher_relation=opposing (1h opposing daily direction) ████")
    spotlight = df[(df["direction"] == "top") & (df["higher_relation"] == "opposing") & (df["horizon"] == 20)]
    print(f"n={len(spotlight)}")
    if len(spotlight) > 0:
        print(f"  hit_rate: {spotlight['hit'].mean()*100:.1f}%")
        print(f"  mean ret: {spotlight['signed_return'].mean()*100:+.2f}%")
        print(f"  median:   {spotlight['signed_return'].median()*100:+.2f}%")
        print(f"  symbol distribution:")
        for sym, n in spotlight.groupby("symbol").size().items():
            sym_hit = spotlight[spotlight["symbol"] == sym]["hit"].mean() * 100
            sym_ret = spotlight[spotlight["symbol"] == sym]["signed_return"].mean() * 100
            print(f"    {sym}: n={n}  hit={sym_hit:.0f}%  ret={sym_ret:+.2f}%")
        print(f"\n  per-signal rows:")
        for _, r in spotlight.sort_values(["symbol", "date"]).iterrows():
            mark = "✓" if r["hit"] else "✗"
            print(f"    {r['symbol']:5s} {r['date']} subtype={r['subtype']:10s} lower_rel={r['lower_relation']:10s} ret={r['signed_return']*100:+6.2f}% {mark}")


if __name__ == "__main__":
    sys.exit(main() or 0)
