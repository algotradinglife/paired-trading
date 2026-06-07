"""SPY D+1h+15m experiment — alternate multi-TF topology.

Hypothesis: top divergences in the daily-only / daily+weekly setup performed
poorly. Maybe a tighter topology (daily primary + 60min higher context + 15min
lower context) captures real intraday reversals better.

This script reuses the same engine but reassigns timeframes:
  - primary    = D    (unchanged — signal source)
  - higher_tf  = 1h   (was: W)
  - lower_tf   = 15m  (was: 1h)

Compares per-rule and per-relation outcomes vs the production D+1h+W run.
Also surfaces top-direction signal analysis since that's the user's target.

Output:
  data/review/spy_d1h15m_signals.csv
  printout — aggregations
"""

from __future__ import annotations

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
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "review"
SYMBOL = "SPY"
FORWARD_WINDOWS = [5, 10, 20]


@dataclass
class Row:
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
    return detect_all_divergences(units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"], level_id=level_id)


def evaluate_forward(sig, bars):
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
    return Row(signal=sig, entry_close=entry, fwd_returns=fwd, signed_returns=signed, hits=hits)


def run_topology(daily, lower_bars, higher_bars, lower_id, higher_id):
    """Detect signals on daily, enrich with given (lower, higher) topology."""
    sigs = detect_signals(daily, level_id="D")
    # Restrict to overlap window
    window_start = max(
        lower_bars["timestamp"].iloc[0],
        higher_bars["timestamp"].iloc[0],
    )
    window_end = min(
        lower_bars["timestamp"].iloc[-1],
        higher_bars["timestamp"].iloc[-1],
    )
    in_window = [s for s in sigs
                 if window_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= window_end]
    enriched = enrich_with_higher_tf(in_window, daily, higher_bars,
                                     higher_tf_level_id=higher_id)
    enriched = enrich_with_lower_tf(enriched, daily, lower_bars,
                                    lower_tf_level_id=lower_id)
    rows = []
    for sig in enriched:
        r = evaluate_forward(sig, daily)
        if r is None:
            continue
        rows.append(r)
    return rows


def rows_to_df(rows: list[Row], topology_tag: str) -> pd.DataFrame:
    records = []
    for r in rows:
        ctx = r.signal.multi_tf_context or {}
        decision = apply_policy(r.signal)
        for h in FORWARD_WINDOWS:
            records.append({
                "topology": topology_tag,
                "date": r.signal.timestamp.strftime("%Y-%m-%d"),
                "direction": r.signal.direction,
                "subtype": r.signal.subtype,
                "level": r.signal.level,
                "confidence": r.signal.confidence,
                "rule_id": decision.rule_id or "—",
                "lower_side": ctx.get("lower_tf_side", "n/a"),
                "lower_cycle": ctx.get("lower_tf_cycle_state", "n/a"),
                "lower_relation": ctx.get("lower_relation", "n/a"),
                "higher_side": ctx.get("higher_tf_side", "n/a"),
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

    def _load(suffix: str) -> pd.DataFrame:
        df = _load_sym(SYMBOL, suffix, quant_root)
        if df is not None:
            return df
        return load_bars(DATA_DIR / f"{SYMBOL.lower()}_{suffix}.json")

    daily = _load("daily")
    sixty = _load("60")
    fifteen = _load("15")
    weekly_path = DATA_DIR / f"{SYMBOL.lower()}_weekly.json"
    weekly_quant = _load_sym(SYMBOL, "weekly", quant_root)
    weekly = weekly_quant if weekly_quant is not None else (load_bars(weekly_path) if weekly_path.exists() else None)

    print(f"Bars: daily={len(daily)}, 60min={len(sixty)}, 15min={len(fifteen)}, "
          f"weekly={'yes' if weekly is not None else 'no'}")

    # Run both topologies for direct comparison
    rows_a = run_topology(daily, sixty, weekly, lower_id="1h", higher_id="W") if weekly is not None else []
    df_a = rows_to_df(rows_a, topology_tag="D+1h+W")
    print(f"\nTopology A (D + 1h + W): {len(rows_a)} signals")

    rows_b = run_topology(daily, fifteen, sixty, lower_id="15m", higher_id="1h")
    df_b = rows_to_df(rows_b, topology_tag="D+15m+1h")
    print(f"Topology B (D + 15m + 1h): {len(rows_b)} signals")

    df_all = pd.concat([df_a, df_b], ignore_index=True)
    out_path = OUT_DIR / "spy_d1h15m_signals.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(out_path, index=False)
    print(f"  → {out_path}")

    for tag, df in [("A (D+1h+W)", df_a), ("B (D+15m+1h)", df_b)]:
        if df.empty:
            continue
        print(f"\n\n████ Topology {tag} ████")

        # Direction baseline
        fmt_band(df, ["direction"], f"Direction baseline ({tag})")

        # Per rule_id
        fmt_band(df, ["rule_id"], f"Per rule_id ({tag})")

        # Direction × relation (the key view for top-divergence improvement)
        fmt_band(df, ["direction", "lower_relation"], f"Direction × lower_relation ({tag})")
        fmt_band(df, ["direction", "higher_relation"], f"Direction × higher_relation ({tag})")

        # Top drill — the user's primary concern
        top_only = df[df["direction"] == "top"]
        if not top_only.empty:
            fmt_band(top_only, ["lower_relation", "higher_relation"],
                     f"TOP signal × lower × higher ({tag})")
            fmt_band(top_only, ["lower_relation"], f"TOP × lower_relation ({tag})")

    # Direct comparison: same daily signals, different contexts
    print("\n\n████ Per-signal context comparison (top signals only) ████")
    sig_dates_a = set(df_a[df_a["direction"] == "top"]["date"].unique())
    sig_dates_b = set(df_b[df_b["direction"] == "top"]["date"].unique())
    common = sorted(sig_dates_a & sig_dates_b)
    print(f"Top signals in BOTH topologies: {len(common)}")

    comp_rows = []
    for d in common:
        a_row = df_a[(df_a["direction"] == "top") & (df_a["date"] == d) & (df_a["horizon"] == 20)].head(1)
        b_row = df_b[(df_b["direction"] == "top") & (df_b["date"] == d) & (df_b["horizon"] == 20)].head(1)
        if a_row.empty or b_row.empty:
            continue
        a, b = a_row.iloc[0], b_row.iloc[0]
        comp_rows.append({
            "date": d,
            "A_lower_rel": a["lower_relation"], "A_higher_rel": a["higher_relation"], "A_rule": a["rule_id"],
            "B_lower_rel": b["lower_relation"], "B_higher_rel": b["higher_relation"], "B_rule": b["rule_id"],
            "h20_ret%": f"{a['signed_return']*100:+.2f}%",
            "h20_hit": "✓" if a["hit"] else "✗",
        })
    if comp_rows:
        pd.set_option("display.width", 200)
        print(pd.DataFrame(comp_rows).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main() or 0)
