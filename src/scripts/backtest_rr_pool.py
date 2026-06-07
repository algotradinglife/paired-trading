"""B-topology backtest with ATR-based stop loss, scaled take-profit, RR and EV.

For each exhaustion signal on the daily TF (B-topology: higher=1h, lower=15m):
  - Entry: close of signal bar
  - Stop:  entry ± STOP_ATR_MULT × ATR(14)  (minus for bottom, plus for top)
  - TP1:   entry + 1R (50% exit)
  - TP2:   entry + 2R (remaining 50% exit)
  - Max hold: MAX_HOLD bars — any open position marked at bar close

Trade simulation uses OHLC bar-by-bar (no look-ahead past bar close).
Within a bar: adverse move (stop direction) is checked before favourable move
(conservative fill assumption).

Outcome types:
  full_stop  — stop hit before TP1       → realized R = -1.0
  tp1_stop   — TP1 hit, then stopped     → realized R =  0.0
  tp1_tp2    — TP1 + TP2 both hit        → realized R = +1.5
  tp1_max    — TP1 hit, max-hold on rest → realized R = 0.5 + 0.5 × (mark / R)
  max_hold   — max-hold from entry       → realized R = (mark / R), capped ±3

EV = mean realized_R across signals.

Usage:
  uv run python scripts/backtest_rr_pool.py --pool CZCE
  uv run python scripts/backtest_rr_pool.py --pool CN_COMMODITY
  uv run python scripts/backtest_rr_pool.py --pool CFFEX
  uv run python scripts/backtest_rr_pool.py --symbols kq_m_czce_ma kq_m_czce_ta
  uv run python scripts/backtest_rr_pool.py --pool CZCE --stop-mult 1.0 1.5 2.0
  uv run python scripts/backtest_rr_pool.py --pool CZCE -o data/review/rr_czce.csv
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.multi_tf_context import enrich_with_higher_tf, enrich_with_lower_tf
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "review"

ATR_PERIOD = 14
MAX_HOLD = 20          # bars; open positions marked at close on bar MAX_HOLD
DEFAULT_STOP_MULTS = [1.5]

POOLS: dict[str, list[str]] = {
    # --- legacy pools (kept for backward compat) ---
    "CZCE": [
        "kq_m_czce_ma", "kq_m_czce_ta", "kq_m_czce_sr", "kq_m_czce_sa",
    ],
    "CFFEX": [
        "kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im",
    ],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_czce_sa",
        "kq_m_ine_sc",
    ],
    "US": [
        "spy", "qqq", "iwm", "dia", "gld", "gdx", "xlf", "xlk", "tlt", "nvda",
    ],
    # --- reclassified pools (scheme B, 2026-05-30) ---
    # CN_INDEX: CFFEX equity index futures
    "CN_INDEX": [
        "kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im",
    ],
    # CN_METAL: SHFE base/precious metals + INE crude oil
    "CN_METAL": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_ine_sc",
    ],
    # CN_AGRI: DCE agri/industrial + CZCE chemicals/soft commodities
    "CN_AGRI": [
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_czce_sa",
    ],
    # US_EQUITY: broad market + sector ETFs (equity-only)
    "US_EQUITY": [
        "spy", "qqq", "iwm", "dia", "xlf", "xlk", "nvda",
    ],
    # US_MACRO: gold/miners + bonds (macro/alternative)
    "US_MACRO": [
        "gld", "gdx", "tlt",
    ],
    # CN_BOND: CFFEX treasury bond futures (TF=5Y, T=10Y, TS=2Y)
    "CN_BOND": [
        "kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts",
    ],
}

POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CZCE": "czce",
    "CFFEX": "cn_index_futures",  # legacy alias for CN_INDEX
    "CN_INDEX": "cn_index_futures",
    "CN_METAL": "cn_metal_futures",
    "CN_AGRI": "czce",      # CZCE1 rule applied; covers both DCE and CZCE symbols
    "US_EQUITY": "us_equity",
    "US_MACRO": "us_equity",
    "CN_BOND": "cn_futures",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(path: Path) -> pd.DataFrame:
    """Load from JSON — kept unchanged as it is imported by backtest_rr_intraday."""
    df, _ = bar_loader.load_snapshot_json(path)
    return df


def _load_sym(sym: str, barstore_level: str, quant_root: Path | None) -> pd.DataFrame | None:
    """Try BarStore; return None if unsupported or unavailable (caller should fall back to JSON)."""
    if quant_root is None:
        return None
    resolved = bar_loader.infer_symbol_and_mic(sym)
    if resolved is None:
        return None
    quant_sym, mic = resolved
    try:
        return bar_loader.load_bars_quant(quant_sym, mic, barstore_level, quant_root)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_c = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_c).abs(),
                    (low - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Signal detection (same B-topology as backtest_cn_b_topology.py)
# ---------------------------------------------------------------------------

def detect_signals(bars: pd.DataFrame, instrument_class: str = "cn_futures"):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"],
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"],
    )
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class=instrument_class,
    )


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

@dataclass
class TradeResult:
    symbol: str
    date: str
    direction: str
    subtype: str
    sig_level: str        # e.g. intra_cycle, intra_cycle_hist, intra_cycle_slope, intra_cycle_dea
    confidence: float
    rule_id: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    atr: float
    stop_mult: float
    risk_r: float
    outcome: str          # full_stop / tp1_stop / tp1_tp2 / tp1_max / max_hold
    realized_r: float
    bars_to_tp1: int | None
    bars_to_exit: int
    higher_relation: str
    lower_relation: str
    confidence_band: str  # low / mid / high tercile (computed globally)


STRUCT_STOP_BUFFER = 0.001   # 0.1% beyond bar extreme


def simulate_trade(
    bars: pd.DataFrame,
    entry_idx: int,
    direction: str,
    stop_mult: float,
    atr_series: pd.Series,
    struct_stop_price: float | None = None,
) -> tuple[str, float, int | None, int] | None:
    """Simulate one trade. Returns (outcome, realized_r, bars_to_tp1, bars_to_exit) or None.

    If struct_stop_price is given, it overrides the ATR-based stop; risk_r is
    computed from |entry - struct_stop_price| and TP targets scale accordingly.
    """
    if entry_idx + 1 >= len(bars):
        return None

    entry = float(bars["close"].iloc[entry_idx])
    atr_val = float(atr_series.iloc[entry_idx])
    if atr_val <= 0 or not np.isfinite(atr_val):
        return None

    if struct_stop_price is not None:
        stop_level = struct_stop_price
        risk_r = abs(entry - stop_level)
        if risk_r <= 0:
            return None
    else:
        risk_r = stop_mult * atr_val

    if direction == "bottom":
        if struct_stop_price is None:
            stop_level = entry - risk_r
        tp1_level = entry + risk_r          # +1R
        tp2_level = entry + 2 * risk_r     # +2R
        def adverse_hit(lo, hi):  return lo <= stop_level
        def tp1_hit(lo, hi):      return hi >= tp1_level
        def tp2_hit(lo, hi):      return hi >= tp2_level
        def mark_pnl(close_price): return close_price - entry
    else:  # top
        if struct_stop_price is None:
            stop_level = entry + risk_r
        tp1_level = entry - risk_r
        tp2_level = entry - 2 * risk_r
        def adverse_hit(lo, hi):  return hi >= stop_level
        def tp1_hit(lo, hi):      return lo <= tp1_level
        def tp2_hit(lo, hi):      return lo <= tp2_level
        def mark_pnl(close_price): return entry - close_price

    reached_tp1 = False
    bars_to_tp1: int | None = None

    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])

        if not reached_tp1:
            # Phase 1: full position — check adverse before favourable
            if adverse_hit(lo, hi):
                return "full_stop", -1.0, None, offset
            if tp1_hit(lo, hi):
                reached_tp1 = True
                bars_to_tp1 = offset
                # check tp2 in same bar (full run through)
                if tp2_hit(lo, hi):
                    return "tp1_tp2", 1.5, bars_to_tp1, offset
                # continue to phase 2
        else:
            # Phase 2: 50% remaining — check adverse before favourable
            if adverse_hit(lo, hi):
                return "tp1_stop", 0.0, bars_to_tp1, offset
            if tp2_hit(lo, hi):
                return "tp1_tp2", 1.5, bars_to_tp1, offset
            if offset == MAX_HOLD:
                # mark remaining 50% at close
                mark = mark_pnl(cl) / risk_r
                realized = 0.5 * 1.0 + 0.5 * float(np.clip(mark, -3.0, 3.0))
                return "tp1_max", realized, bars_to_tp1, offset

    # Never reached TP1, max hold
    idx_final = min(entry_idx + MAX_HOLD, len(bars) - 1)
    cl_final = float(bars["close"].iloc[idx_final])
    mark = mark_pnl(cl_final) / risk_r
    realized = float(np.clip(mark, -3.0, 3.0))
    bars_final = idx_final - entry_idx
    return "max_hold", realized, None, bars_final


# ---------------------------------------------------------------------------
# Per-symbol pipeline
# ---------------------------------------------------------------------------

def run_symbol(
    stem: str,
    stop_mult: float,
    instrument_class: str = "cn_futures",
    use_struct_stop: bool = False,
    quant_root: Path | None = None,
) -> tuple[list[TradeResult], str]:
    def _load_tf(suffix: str, barstore_level: str) -> pd.DataFrame | None:
        df = _load_sym(stem, barstore_level, quant_root)
        if df is not None:
            return df
        p = DATA_DIR / f"{stem}_{suffix}.json"
        return load_bars(p) if p.exists() else None

    daily = _load_tf("daily", "D")
    sixty = _load_tf("60", "60min")
    fifteen = _load_tf("15", "15min")
    if daily is None or sixty is None or fifteen is None:
        missing = [s for s, d in [("daily", daily), ("60", sixty), ("15", fifteen)] if d is None]
        return [], f"missing: {missing}"
    if daily.empty or sixty.empty or fifteen.empty:
        return [], "empty bars"

    atr_series = compute_atr(daily)

    sigs = detect_signals(daily, instrument_class=instrument_class)
    win_start = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    win_end = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    in_window = [s for s in sigs
                 if win_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= win_end]

    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    enriched = enrich_with_lower_tf(enriched, daily, fifteen, lower_tf_level_id="15m")

    results: list[TradeResult] = []
    for sig in enriched:
        idx = sig.candidate_bar_idx
        entry = float(daily["close"].iloc[idx])
        atr_val = float(atr_series.iloc[idx])

        struct_stop: float | None = None
        if use_struct_stop:
            bar_lo = float(daily["low"].iloc[idx])
            bar_hi = float(daily["high"].iloc[idx])
            if sig.direction == "bottom":
                struct_stop = bar_lo * (1 - STRUCT_STOP_BUFFER)
            else:
                struct_stop = bar_hi * (1 + STRUCT_STOP_BUFFER)

        sim = simulate_trade(daily, idx, sig.direction, stop_mult, atr_series,
                             struct_stop_price=struct_stop)
        if sim is None:
            continue
        outcome, realized_r, bars_tp1, bars_exit = sim

        if use_struct_stop and struct_stop is not None:
            risk_r = abs(entry - struct_stop)
        else:
            risk_r = stop_mult * atr_val
        stop_level = (entry - risk_r) if sig.direction == "bottom" else (entry + risk_r)
        tp1_level = (entry + risk_r) if sig.direction == "bottom" else (entry - risk_r)
        tp2_level = (entry + 2*risk_r) if sig.direction == "bottom" else (entry - 2*risk_r)

        ctx = sig.multi_tf_context or {}
        decision = apply_policy(sig, instrument_class=instrument_class)
        if decision.weight == 0.0:
            continue

        results.append(TradeResult(
            symbol=stem,
            date=sig.timestamp.strftime("%Y-%m-%d"),
            direction=sig.direction,
            subtype=sig.subtype,
            sig_level=sig.level,
            confidence=sig.confidence,
            rule_id=decision.rule_id or "—",
            entry=entry,
            stop=stop_level,
            tp1=tp1_level,
            tp2=tp2_level,
            atr=atr_val,
            stop_mult=stop_mult,
            risk_r=risk_r,
            outcome=outcome,
            realized_r=realized_r,
            bars_to_tp1=bars_tp1,
            bars_to_exit=bars_exit,
            higher_relation=ctx.get("higher_relation", "n/a"),
            lower_relation=ctx.get("lower_relation", "n/a"),
            confidence_band="",   # filled later
        ))
    return results, "ok"


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def assign_confidence_bands(results: list[TradeResult]) -> None:
    vals = [r.confidence for r in results]
    if not vals:
        return
    lo_thr = np.percentile(vals, 33.33)
    hi_thr = np.percentile(vals, 66.67)
    for r in results:
        if r.confidence <= lo_thr:
            r.confidence_band = "low"
        elif r.confidence <= hi_thr:
            r.confidence_band = "mid"
        else:
            r.confidence_band = "high"


def print_ev_table(results: list[TradeResult], title: str, group_key) -> None:
    if not results:
        print(f"\n=== {title} === (no data)")
        return
    groups: dict[str, list[TradeResult]] = {}
    for r in results:
        k = group_key(r)
        groups.setdefault(k, []).append(r)

    print(f"\n=== {title} ===")
    hdr = f"{'group':<28} {'n':>4}  {'EV(R)':>7}  {'hit%TP1':>7}  {'hit%TP2':>7}  "
    hdr += f"{'full_stop%':>10}  {'outcome_breakdown'}"
    print(hdr)
    print("-" * 95)

    for k in sorted(groups):
        grp = groups[k]
        n = len(grp)
        ev = float(np.mean([r.realized_r for r in grp]))
        tp1_rate = sum(1 for r in grp if r.outcome in ("tp1_stop", "tp1_tp2", "tp1_max")) / n
        tp2_rate = sum(1 for r in grp if r.outcome == "tp1_tp2") / n
        stop_rate = sum(1 for r in grp if r.outcome == "full_stop") / n
        outcomes = ["full_stop", "tp1_stop", "tp1_tp2", "tp1_max", "max_hold"]
        breakdown = "  ".join(
            f"{o}:{sum(1 for r in grp if r.outcome==o)}"
            for o in outcomes
            if any(r.outcome == o for r in grp)
        )
        ev_flag = " ✓" if ev > 0 else ""
        print(f"{k:<28} {n:>4}  {ev:>+7.3f}  {tp1_rate:>6.1%}  {tp2_rate:>6.1%}  "
              f"{stop_rate:>9.1%}  {breakdown}{ev_flag}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="B-topology RR backtest with ATR stop loss")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--pool", choices=sorted(POOLS))
    grp.add_argument("--symbols", nargs="+")
    p.add_argument("--stop-mult", type=float, nargs="+", default=DEFAULT_STOP_MULTS,
                   dest="stop_mults",
                   help="ATR stop multipliers to test (default: 1.5)")
    p.add_argument("--instrument-class", dest="instrument_class", default=None,
                   help="Override instrument class (default: pool-based auto-detect)")
    p.add_argument("--struct-stop", action="store_true", dest="struct_stop",
                   help="Use bar low/high (±0.1%%) as stop instead of ATR×mult")
    p.add_argument("-o", "--output", type=Path, help="CSV output path for per-trade records")
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    args = p.parse_args()
    quant_root = args.quant_data_root

    symbols = POOLS[args.pool] if args.pool else args.symbols
    pool_label = args.pool or "custom"

    # Resolve instrument_class: explicit flag > pool mapping > fallback
    if args.instrument_class:
        instrument_class = args.instrument_class
    elif args.pool and args.pool in POOL_INSTRUMENT_CLASS:
        instrument_class = POOL_INSTRUMENT_CLASS[args.pool]
    else:
        instrument_class = "cn_futures"

    stop_label = "struct(bar_low/high±0.1%)" if args.struct_stop else f"ATR×{args.stop_mults}"
    print(f"Pool: {pool_label} ({len(symbols)} symbols)  instrument_class={instrument_class}  "
          f"ATR_period={ATR_PERIOD}  MAX_HOLD={MAX_HOLD}")
    print(f"Stop: {stop_label}  TP1=+1R(50%), TP2=+2R(50%)\n")

    all_results: list[TradeResult] = []
    for mult in args.stop_mults:
        print(f"─── stop_mult={mult} ───")
        for sym in symbols:
            res, status = run_symbol(sym, mult, instrument_class=instrument_class,
                                     use_struct_stop=args.struct_stop, quant_root=quant_root)
            n_bot = sum(1 for r in res if r.direction == "bottom")
            n_top = sum(1 for r in res if r.direction == "top")
            ev_all = float(np.mean([r.realized_r for r in res])) if res else float("nan")
            print(f"  {sym:25s}: {len(res):3d} trades ({n_bot} bot / {n_top} top)  "
                  f"EV={ev_all:+.3f}R  [{status}]")
            all_results.extend(res)
        print()

    if not all_results:
        print("No trades found. Check that daily+60m+15m data files exist.")
        return 1

    # Assign confidence bands globally (same percentile thresholds for all)
    assign_confidence_bands(all_results)

    # Aggregate output (first stop_mult only if multiple)
    primary = [r for r in all_results if r.stop_mult == args.stop_mults[0]]

    print(f"\n{'='*70}")
    print(f"PRIMARY ANALYSIS  stop_mult={args.stop_mults[0]}  "
          f"n={len(primary)} trades")
    print(f"{'='*70}")

    n_bot = sum(1 for r in primary if r.direction == "bottom")
    n_top = sum(1 for r in primary if r.direction == "top")
    ev_all = float(np.mean([r.realized_r for r in primary]))
    ev_bot = float(np.mean([r.realized_r for r in primary if r.direction == "bottom"])) if n_bot else float("nan")
    ev_top = float(np.mean([r.realized_r for r in primary if r.direction == "top"])) if n_top else float("nan")
    print(f"\nOverall EV: {ev_all:+.3f}R  (bottom n={n_bot} EV={ev_bot:+.3f}R  |  "
          f"top n={n_top} EV={ev_top:+.3f}R)")

    print_ev_table(primary, "By direction × stop_mult", lambda r: f"{r.direction}")
    print_ev_table(primary, "By sig_level",
                   lambda r: f"{r.direction} / {r.sig_level}")
    print_ev_table(primary, "By direction × lower_relation (15m)",
                   lambda r: f"{r.direction} / l={r.lower_relation}")
    print_ev_table(primary, "By direction × higher_relation (1h)",
                   lambda r: f"{r.direction} / h={r.higher_relation}")
    print_ev_table(primary, "By direction × confidence_band",
                   lambda r: f"{r.direction} / conf={r.confidence_band}")
    print_ev_table(primary, "By direction × rule_id",
                   lambda r: f"{r.direction} / {r.rule_id}")
    print_ev_table(primary, "By symbol",
                   lambda r: r.symbol)

    if len(args.stop_mults) > 1:
        print_ev_table(all_results, "Stop multiplier sensitivity (all directions)",
                       lambda r: f"mult={r.stop_mult}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        records = [vars(r) for r in all_results]
        pd.DataFrame(records).to_csv(args.output, index=False)
        print(f"\nPer-trade CSV → {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
