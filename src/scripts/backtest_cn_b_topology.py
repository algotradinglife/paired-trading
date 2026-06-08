"""CN futures B-topology (D + 15min + 1h) backtest — 19 品种 pooled.

Uses TqSdk-sourced daily / 60min / 15min data + instrument_class="cn_futures"
so direction_gate is pass-through (CN tops are empirically +0.65% mean per
prior 2026-05-24 study; US gate over-penalizes).

Validates whether F2 / F4 / B1 rules (which need multi_tf_context to fire)
generate meaningful signals on CN futures now that we have intraday data.

Inputs: data/raw/kq_m_<exch>_<product>_{daily,60,15}.json (from fetch_tqsdk).

Output:
  data/review/cn_b_topology_signals_all.csv  — per-signal × per-horizon rows
  printout — direction baseline, per-rule, per-relation aggregations
"""

from __future__ import annotations

import json
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
FORWARD_WINDOWS = [5, 10, 20]

# 19 CN futures — filename stems match fetch_tqsdk.py sanitization of
# KQ.m@<EXCH>.<PROD> symbols
CN_FUTURES = [
    # CFFEX index futures
    "kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im",
    # SHFE metals + steel
    "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
    # DCE agri + coke
    "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
    "kq_m_dce_p", "kq_m_dce_y",
    # CZCE
    "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    # INE
    "kq_m_ine_sc",
]


@dataclass
class Row:
    symbol: str
    signal: DivergenceSignal
    entry_close: float
    fwd_returns: dict[int, float]
    signed_returns: dict[int, float]
    hits: dict[int, bool]


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def load_bars_via_quant(stem: str, level: str, quant_root: Path) -> pd.DataFrame:
    """Load a kq_m_<exch>_<sym> bar series from the Parquet quant store.

    level is the BarStore level: 'D', '60min', or '15min'.
    """
    mapping = bar_loader._kq_m_to_quant(stem)
    if mapping is None:
        raise ValueError(f"Cannot map {stem!r} to a quant-data symbol")
    sym, mic = mapping
    return bar_loader.load_bars_quant(sym, mic, level, quant_root)


def detect_signals(bars: pd.DataFrame, level_id: str, instrument_class: str):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id=level_id, instrument_class=instrument_class,
    )


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


def run_for_symbol(stem: str, source: str = "json", quant_root: Path | None = None) -> tuple[list[Row], str]:
    if source == "quant":
        try:
            daily = load_bars_via_quant(stem, "D", quant_root)
            sixty = load_bars_via_quant(stem, "60min", quant_root)
            fifteen = load_bars_via_quant(stem, "15min", quant_root)
        except Exception as e:
            return [], f"quant load error: {e}"
    else:
        daily_p = DATA_DIR / f"{stem}_daily.json"
        sixty_p = DATA_DIR / f"{stem}_60.json"
        fifteen_p = DATA_DIR / f"{stem}_15.json"
        missing = [p.name for p in (daily_p, sixty_p, fifteen_p) if not p.exists()]
        if missing:
            return [], f"missing files: {missing}"
        daily = load_bars(daily_p)
        sixty = load_bars(sixty_p)
        fifteen = load_bars(fifteen_p)
    if daily.empty or sixty.empty or fifteen.empty:
        return [], "empty bars"

    sigs = detect_signals(daily, level_id="D", instrument_class="cn_futures")
    # Restrict to window where both 60min and 15min cover the signal date
    win_start = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    win_end = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    in_window = [s for s in sigs
                 if win_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= win_end]

    # B-topology: higher=1h, lower=15m
    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    enriched = enrich_with_lower_tf(enriched, daily, fifteen, lower_tf_level_id="15m")

    rows = []
    for sig in enriched:
        r = evaluate_forward(stem, sig, daily)
        if r is not None:
            rows.append(r)
    return rows, "ok"


def rows_to_df(rows: list[Row]) -> pd.DataFrame:
    records = []
    for r in rows:
        ctx = r.signal.multi_tf_context or {}
        decision = apply_policy(r.signal, instrument_class="cn_futures")
        for h in FORWARD_WINDOWS:
            records.append({
                "symbol": r.symbol,
                "date": r.signal.timestamp.strftime("%Y-%m-%d"),
                "direction": r.signal.direction,
                "subtype": r.signal.subtype,
                "level": r.signal.level,
                "confidence": r.signal.confidence,
                "rule_id": decision.rule_id or "—",
                "rule_weight": decision.weight,
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
                        help="quant-data Parquet root (used when --source=quant)")
    parser.add_argument("--source", choices=["json", "quant"], default="json",
                        help="bar source: legacy JSON (data/raw/) or quant Parquet store (default: json)")
    parser.add_argument("--out", type=Path, default=None,
                        help="output CSV path (default: <review_dir>/cn_b_topology_signals_all.csv; "
                             "review_dir honors $DERIVED_ROOT/paired-trading/src-data-review "
                             "or falls back to src/data/review/)")
    args = parser.parse_args()

    all_rows = []
    for stem in CN_FUTURES:
        rows, status = run_for_symbol(stem, source=args.source, quant_root=args.quant_data_root)
        n_top = sum(1 for r in rows if r.signal.direction == "top")
        n_bot = sum(1 for r in rows if r.signal.direction == "bottom")
        n_ctx = sum(1 for r in rows if r.signal.multi_tf_context)
        print(f"  {stem:25s}: {len(rows):3d} signals ({n_bot} bot + {n_top} top, {n_ctx} w/ ctx)  [{status}]")
        all_rows.extend(rows)

    if not all_rows:
        print("\nNo signals collected. Phase 1 fetch may be incomplete.")
        return 1

    df = rows_to_df(all_rows)
    out_path = args.out if args.out is not None else OUT_DIR / "cn_b_topology_signals_all.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nTotal: {len(all_rows)} signals × {len(FORWARD_WINDOWS)} horizons = {len(df)} rows → {out_path}")

    # Direction baseline
    fmt_band(df, ["direction"], "Direction baseline (CN, B topology)")

    # Per rule
    fmt_band(df, ["rule_id"], "Per rule_id (cn_futures policy)")

    # Direction × lower_relation
    fmt_band(df, ["direction", "lower_relation"], "Direction × lower_relation (15m)")

    # Direction × higher_relation
    fmt_band(df, ["direction", "higher_relation"], "Direction × higher_relation (1h)")

    # 3-way drill
    fmt_band(df, ["direction", "lower_relation", "higher_relation"],
             "Direction × lower × higher")

    # Per-symbol direction split
    print("\n=== Per-symbol direction summary (h=20) ===")
    h20 = df[df["horizon"] == 20]
    for sym in CN_FUTURES:
        sub = h20[h20["symbol"] == sym]
        if sub.empty:
            continue
        b = sub[sub["direction"] == "bottom"]
        t = sub[sub["direction"] == "top"]
        bh = f"{b['hit'].mean()*100:.0f}% (+{b['signed_return'].mean()*100:.2f}%) n={len(b)}" if len(b) else "—"
        th = f"{t['hit'].mean()*100:.0f}% ({t['signed_return'].mean()*100:+.2f}%) n={len(t)}" if len(t) else "—"
        print(f"  {sym:25s}  bottom: {bh:30s}  top: {th}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
