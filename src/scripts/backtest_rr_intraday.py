"""
Intraday (15m MACD zero-cross) entry refinement for B-topology h=opposing setups.

After a daily exhaustion signal fires, instead of entering at the daily close:
1. Wait for the first 15m MACD(12,26,9) histogram zero-cross in the signal direction.
2. Enter at that 15m bar's close.
3. Stop = structural low/high of the prior STOP_LOOKBACK_BARS 15m bars.
4. TP1/TP2 = entry ± 1R/2R where R = intraday_risk_r (tight, structure-based).
5. Simulate remaining 15m bars with same phase logic as daily backtest.

Reports:
  - EV in 15m R units (tight stop → high R multiples)
  - Entry improvement vs daily close (% of daily ATR)
  - Risk reduction ratio (intraday_risk_r / daily_ATR)
  - Daily-normalized EV: EV_15m × mean(risk_reduction) for direct comparison
  - Miss rate: fraction of signals with no 15m entry within MAX_WAIT_BARS
  - Breakdown by lower_relation (key question: does timing help most for "leading"?)

Usage:
  uv run python scripts/backtest_rr_intraday.py --pool CN_COMMODITY --stop-mult 1.0
  uv run python scripts/backtest_rr_intraday.py --pool CFFEX --stop-mult 1.0
  uv run python scripts/backtest_rr_intraday.py --pool US --stop-mult 0.75
  uv run python scripts/backtest_rr_intraday.py --pool CN_COMMODITY --all-signals
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
from scripts.backtest_rr_pool import (
    POOLS,
    POOL_INSTRUMENT_CLASS,
    TradeResult as DailyTradeResult,
    compute_atr,
    detect_signals,
    enrich_with_higher_tf,
    enrich_with_lower_tf,
    load_bars,
    apply_policy,
    DATA_DIR,
    _load_sym,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_PERIOD = 9

STOP_LOOKBACK_BARS = 8    # 15m bars for structure stop (2h for 30min/bar markets)
MAX_WAIT_BARS = 120       # max 15m bars after daily close to find entry (~3 CN days)
MAX_HOLD_BARS_15M = 200   # max 15m bars for trade exit (~5 days)
DAILY_ATR_PERIOD = 14


# ---------------------------------------------------------------------------
# MACD on intraday bars
# ---------------------------------------------------------------------------

def compute_macd_histogram(closes: pd.Series) -> pd.Series:
    ema_fast = closes.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = closes.ewm(span=MACD_SLOW, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=MACD_SIGNAL_PERIOD, adjust=False).mean()
    return macd - sig


# ---------------------------------------------------------------------------
# Intraday entry search
# ---------------------------------------------------------------------------

@dataclass
class IntradayEntry:
    entry_ts: pd.Timestamp
    bar_idx: int        # index into fifteen DataFrame
    entry_price: float
    stop_price: float
    risk_r: float       # entry_price - stop_price (for bottom; > 0)
    wait_bars: int      # 15m bars waited after daily signal


def find_15m_entry(
    fifteen: pd.DataFrame,
    hist: pd.Series,
    signal_ts: pd.Timestamp,
    direction: str,
    daily_entry: float,
    max_wait_bars: int = MAX_WAIT_BARS,
    stop_lookback: int = STOP_LOOKBACK_BARS,
) -> IntradayEntry | None:
    """Find first 15m MACD histogram zero-cross after signal_ts."""
    # Start from first 15m bar AFTER the daily close timestamp
    after_mask = fifteen["timestamp"] > signal_ts
    after_idx = fifteen.index[after_mask]
    if len(after_idx) == 0:
        return None

    search_start = after_idx[0]
    search_end = min(search_start + max_wait_bars, len(fifteen))

    for i in range(search_start, search_end):
        if i == 0:
            continue
        prev_h = float(hist.iloc[i - 1])
        curr_h = float(hist.iloc[i])

        if direction == "bottom":
            cross = prev_h <= 0 and curr_h > 0
        else:  # top
            cross = prev_h >= 0 and curr_h < 0

        if not cross:
            continue

        entry_price = float(fifteen["close"].iloc[i])

        # Structure stop: extreme of prior stop_lookback bars
        lb_start = max(0, i - stop_lookback)
        if direction == "bottom":
            stop_price = float(fifteen["low"].iloc[lb_start:i].min())
        else:
            stop_price = float(fifteen["high"].iloc[lb_start:i].max())

        # Reject stops on the wrong side (stop must be behind entry)
        if direction == "bottom" and stop_price >= entry_price:
            continue
        if direction == "top" and stop_price <= entry_price:
            continue
        risk_r = entry_price - stop_price if direction == "bottom" else stop_price - entry_price
        if risk_r <= 0:
            continue

        return IntradayEntry(
            entry_ts=fifteen["timestamp"].iloc[i],
            bar_idx=i,
            entry_price=entry_price,
            stop_price=stop_price,
            risk_r=risk_r,
            wait_bars=i - search_start,
        )

    return None


# ---------------------------------------------------------------------------
# Intraday trade simulation
# ---------------------------------------------------------------------------

@dataclass
class IntradayTradeResult:
    # Identity (matches daily trade)
    symbol: str
    date: str            # daily signal date
    direction: str
    higher_relation: str
    lower_relation: str
    confidence_band: str
    subtype: str
    # Intraday entry details
    intraday_entry: float
    intraday_stop: float
    intraday_risk_r: float
    wait_bars: int       # 15m bars waited
    entry_ts: str        # intraday entry timestamp
    # Daily context (for comparison)
    daily_entry: float
    daily_atr: float
    stop_mult: float
    entry_improvement: float  # (daily_entry - intraday_entry) / daily_atr; > 0 = better
    risk_reduction: float     # intraday_risk_r / daily_atr; < 1 = tighter stop
    # Outcome
    outcome: str
    realized_r_15m: float    # in intraday risk_r units
    realized_r_daily_equiv: float  # realized_r_15m × risk_reduction; comparable to daily EV
    bars_to_tp1_15m: int | None
    bars_to_exit_15m: int
    # Reference: daily outcome (from parallel daily backtest)
    daily_outcome: str = ""
    daily_realized_r: float = 0.0


def simulate_15m_trade(
    fifteen: pd.DataFrame,
    entry: IntradayEntry,
    direction: str,
    max_hold_bars: int = MAX_HOLD_BARS_15M,
) -> tuple[str, float, int | None, int]:
    """Simulate trade on 15m bars using symmetric 1R/2R targets. Returns (outcome, realized_r, bars_tp1, bars_exit)."""
    e = entry.entry_price
    r = entry.risk_r

    if direction == "bottom":
        stop_level = entry.stop_price
        tp1_level = e + r
        tp2_level = e + 2 * r
        def adverse_hit(lo, hi): return lo <= stop_level
        def tp1_hit(lo, hi): return hi >= tp1_level
        def tp2_hit(lo, hi): return hi >= tp2_level
        def mark_pnl(cl): return (cl - e) / r
    else:
        stop_level = entry.stop_price
        tp1_level = e - r
        tp2_level = e - 2 * r
        def adverse_hit(lo, hi): return hi >= stop_level
        def tp1_hit(lo, hi): return lo <= tp1_level
        def tp2_hit(lo, hi): return lo <= tp2_level
        def mark_pnl(cl): return (e - cl) / r

    reached_tp1 = False
    bars_to_tp1: int | None = None

    for offset in range(1, max_hold_bars + 1):
        idx = entry.bar_idx + offset
        if idx >= len(fifteen):
            break
        lo = float(fifteen["low"].iloc[idx])
        hi = float(fifteen["high"].iloc[idx])
        cl = float(fifteen["close"].iloc[idx])

        if not reached_tp1:
            if adverse_hit(lo, hi):
                return "full_stop", -1.0, None, offset
            if tp1_hit(lo, hi):
                reached_tp1 = True
                bars_to_tp1 = offset
                if tp2_hit(lo, hi):
                    return "tp1_tp2", 1.5, bars_to_tp1, offset
        else:
            if adverse_hit(lo, hi):
                return "tp1_stop", 0.0, bars_to_tp1, offset
            if tp2_hit(lo, hi):
                return "tp1_tp2", 1.5, bars_to_tp1, offset
            if offset == max_hold_bars:
                mark = mark_pnl(cl)
                realized = 0.5 * 1.0 + 0.5 * float(np.clip(mark, -3.0, 3.0))
                return "tp1_max", realized, bars_to_tp1, offset

    idx_final = min(entry.bar_idx + max_hold_bars, len(fifteen) - 1)
    cl_final = float(fifteen["close"].iloc[idx_final])
    mark = mark_pnl(cl_final)
    realized = float(np.clip(mark, -3.0, 3.0))
    return "max_hold", realized, None, max_hold_bars


# ---------------------------------------------------------------------------
# Per-symbol pipeline
# ---------------------------------------------------------------------------

def run_symbol(
    stem: str,
    stop_mult: float,
    instrument_class: str = "cn_futures",
    h_opposing_only: bool = True,
    quant_root: Path | None = None,
) -> tuple[list[IntradayTradeResult], list[str], str]:
    """Returns (results, misses, status).
    misses: list of signal dates that fired but no 15m entry found.
    """
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
        return [], [], f"missing: {missing}"
    if daily.empty or sixty.empty or fifteen.empty:
        return [], [], "empty bars"

    atr_series = compute_atr(daily, period=DAILY_ATR_PERIOD)
    hist_15m = compute_macd_histogram(fifteen["close"])

    sigs = detect_signals(daily, instrument_class=instrument_class)
    win_start = max(sixty["timestamp"].iloc[0], fifteen["timestamp"].iloc[0])
    win_end = min(sixty["timestamp"].iloc[-1], fifteen["timestamp"].iloc[-1])
    in_window = [s for s in sigs
                 if win_start <= daily["timestamp"].iloc[s.candidate_bar_idx] <= win_end]

    enriched = enrich_with_higher_tf(in_window, daily, sixty, higher_tf_level_id="1h")
    enriched = enrich_with_lower_tf(enriched, daily, fifteen, lower_tf_level_id="15m")

    # Also run daily simulation to attach daily outcomes for comparison
    from scripts.backtest_rr_pool import simulate_trade as daily_sim
    daily_atr_series = atr_series  # same series

    results: list[IntradayTradeResult] = []
    misses: list[str] = []

    for sig in enriched:
        idx = sig.candidate_bar_idx
        ctx = sig.multi_tf_context or {}
        h_rel = ctx.get("higher_relation", "n/a")

        if h_opposing_only and h_rel != "opposing":
            continue

        daily_entry = float(daily["close"].iloc[idx])
        daily_atr = float(atr_series.iloc[idx])
        if daily_atr <= 0 or not np.isfinite(daily_atr):
            continue

        signal_ts = daily["timestamp"].iloc[idx]
        date_str = signal_ts.strftime("%Y-%m-%d")

        # Find intraday entry
        ie = find_15m_entry(
            fifteen, hist_15m, signal_ts, sig.direction,
            daily_entry=daily_entry,
        )

        # Get daily outcome for reference
        daily_sim_result = daily_sim(daily, idx, sig.direction, stop_mult, daily_atr_series)
        d_outcome = d_realized = ""
        if daily_sim_result:
            d_outcome, d_realized, _, _ = daily_sim_result
        else:
            d_outcome, d_realized = "n/a", float("nan")

        # Compute confidence band (same logic as daily backtest)
        conf_raw = getattr(sig, "confidence", 0.0) or 0.0

        if ie is None:
            misses.append(date_str)
            # Record as "no_entry" with NaN EV
            results.append(IntradayTradeResult(
                symbol=stem,
                date=date_str,
                direction=sig.direction,
                higher_relation=h_rel,
                lower_relation=ctx.get("lower_relation", "n/a"),
                confidence_band="",
                subtype=getattr(sig, "subtype", ""),
                intraday_entry=float("nan"),
                intraday_stop=float("nan"),
                intraday_risk_r=float("nan"),
                wait_bars=-1,
                entry_ts="",
                daily_entry=daily_entry,
                daily_atr=daily_atr,
                stop_mult=stop_mult,
                entry_improvement=float("nan"),
                risk_reduction=float("nan"),
                outcome="no_entry",
                realized_r_15m=float("nan"),
                realized_r_daily_equiv=float("nan"),
                bars_to_tp1_15m=None,
                bars_to_exit_15m=-1,
                daily_outcome=d_outcome,
                daily_realized_r=float(d_realized) if np.isfinite(float(d_realized)) else float("nan"),
            ))
            continue

        # Simulate on 15m
        outcome, realized_r_15m, bars_tp1, bars_exit = simulate_15m_trade(
            fifteen, ie, sig.direction
        )

        entry_improvement = (daily_entry - ie.entry_price) / daily_atr if sig.direction == "bottom" \
                             else (ie.entry_price - daily_entry) / daily_atr
        daily_risk_r = stop_mult * daily_atr
        risk_reduction = ie.risk_r / daily_risk_r
        realized_r_daily_equiv = realized_r_15m * risk_reduction

        results.append(IntradayTradeResult(
            symbol=stem,
            date=date_str,
            direction=sig.direction,
            higher_relation=h_rel,
            lower_relation=ctx.get("lower_relation", "n/a"),
            confidence_band="",
            subtype=getattr(sig, "subtype", ""),
            intraday_entry=ie.entry_price,
            intraday_stop=ie.stop_price,
            intraday_risk_r=ie.risk_r,
            wait_bars=ie.wait_bars,
            entry_ts=ie.entry_ts.isoformat() if hasattr(ie.entry_ts, "isoformat") else str(ie.entry_ts),
            daily_entry=daily_entry,
            daily_atr=daily_atr,
            stop_mult=stop_mult,
            entry_improvement=entry_improvement,
            risk_reduction=risk_reduction,
            outcome=outcome,
            realized_r_15m=realized_r_15m,
            realized_r_daily_equiv=realized_r_daily_equiv,
            bars_to_tp1_15m=bars_tp1,
            bars_to_exit_15m=bars_exit,
            daily_outcome=d_outcome,
            daily_realized_r=float(d_realized) if np.isfinite(float(d_realized)) else float("nan"),
        ))

    return results, misses, "ok"


# ---------------------------------------------------------------------------
# Confidence band assignment (mirrors daily backtest)
# ---------------------------------------------------------------------------

def assign_confidence_bands(results: list[IntradayTradeResult]) -> None:
    confs = [r.intraday_risk_r for r in results  # proxy: risk_r correlates with confidence
             if r.outcome != "no_entry" and np.isfinite(r.intraday_risk_r)]
    if not confs:
        return
    # Use daily confidence from the daily_realized_r reference; rough proxy
    # Actually assign based on the fraction of daily_atr as risk_reduction —
    # this is not meaningful for confidence_band which should come from sig.confidence.
    # Leave blank; the daily breakdown is the reference.


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt(ev: float, n: int = 0) -> str:
    if not np.isfinite(ev):
        return "  n/a "
    sign = "+" if ev >= 0 else ""
    return f"{sign}{ev:.3f}R"


def print_summary_table(label: str, rows: list[IntradayTradeResult], key_fn) -> None:
    from itertools import groupby
    groups: dict[str, list[IntradayTradeResult]] = {}
    for r in rows:
        k = key_fn(r)
        groups.setdefault(k, []).append(r)

    header = f"{'group':<32s}  {'n':>4s}  {'EV(15mR)':>9s}  {'EV(daily≡)':>11s}  " \
             f"{'risk_red':>8s}  {'TP1%':>5s}  {'stop%':>5s}  {'miss%':>5s}"
    print(f"\n=== {label} ===")
    print(header)
    print("-" * len(header))
    for k in sorted(groups):
        g = groups[k]
        n_all = len(g)
        n_ok = [x for x in g if x.outcome != "no_entry"]
        n_miss = n_all - len(n_ok)
        miss_pct = n_miss / n_all if n_all else float("nan")

        if not n_ok:
            print(f"  {k:<30s}  {n_all:>4d}  {'':>9s}  {'':>11s}  {'':>8s}  {'':>5s}  {'':>5s}  {miss_pct:>4.0%}")
            continue

        ev_15m = np.mean([x.realized_r_15m for x in n_ok])
        ev_daily = np.mean([x.realized_r_daily_equiv for x in n_ok])
        rr = np.mean([x.risk_reduction for x in n_ok])
        tp1_pct = np.mean([x.outcome in ("tp1_tp2", "tp1_stop", "tp1_max") for x in n_ok])
        stop_pct = np.mean([x.outcome == "full_stop" for x in n_ok])

        print(f"  {k:<30s}  {n_all:>4d}  {_fmt(ev_15m):>9s}  {_fmt(ev_daily):>11s}  "
              f"{rr:>7.2f}×  {tp1_pct:>4.0%}  {stop_pct:>4.0%}  {miss_pct:>4.0%}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Intraday 15m entry refinement for B-topology h=opposing")
    p.add_argument("--pool", default="CN_COMMODITY",
                   choices=list(POOLS.keys()),
                   help="Symbol pool to analyse")
    p.add_argument("--stop-mult", type=float, default=1.0,
                   help="Daily ATR stop multiplier (used only for daily baseline comparison)")
    p.add_argument("--instrument-class", dest="instrument_class", default=None)
    p.add_argument("--all-signals", action="store_true",
                   help="Include all signals, not just h=opposing")
    p.add_argument("-o", "--output", default=None,
                   help="Optional CSV output path")
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    args = p.parse_args()
    quant_root = args.quant_data_root

    pool_label = args.pool
    symbols = POOLS[pool_label]
    h_opposing_only = not args.all_signals

    if args.instrument_class:
        instrument_class = args.instrument_class
    elif pool_label in POOL_INSTRUMENT_CLASS:
        instrument_class = POOL_INSTRUMENT_CLASS[pool_label]
    else:
        instrument_class = "cn_futures"

    filter_label = "h=opposing only" if h_opposing_only else "ALL signals"
    print(f"Pool: {pool_label} ({len(symbols)} symbols)  stop_mult={args.stop_mult}  "
          f"instrument_class={instrument_class}  filter={filter_label}")
    print(f"15m MACD({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL_PERIOD})  "
          f"stop_lookback={STOP_LOOKBACK_BARS}  max_wait={MAX_WAIT_BARS}  "
          f"max_hold_15m={MAX_HOLD_BARS_15M}\n")

    all_results: list[IntradayTradeResult] = []
    all_misses_count = 0
    all_signals_count = 0

    for sym in symbols:
        res, misses, status = run_symbol(
            sym, args.stop_mult, instrument_class=instrument_class,
            h_opposing_only=h_opposing_only, quant_root=quant_root,
        )
        n_all = len(res)
        n_miss = len(misses)
        n_ok = n_all - n_miss
        all_signals_count += n_all
        all_misses_count += n_miss
        if n_all > 0:
            ev_15m = np.mean([r.realized_r_15m for r in res if r.outcome != "no_entry"]) \
                     if n_ok else float("nan")
            ev_d = np.mean([r.realized_r_daily_equiv for r in res if r.outcome != "no_entry"]) \
                   if n_ok else float("nan")
            miss_pct = n_miss / n_all
            status_str = f"[{status}]" if status != "ok" else ""
            print(f"  {sym:<28s}: {n_ok:>3d}/{n_all} trades  "
                  f"EV_15m={_fmt(ev_15m)}  EV_daily≡={_fmt(ev_d)}  "
                  f"miss={miss_pct:.0%}  {status_str}")
        else:
            print(f"  {sym:<28s}: 0 trades  [{status}]")
        all_results.extend(res)

    if not all_results:
        print("\nNo results. Check data and pool configuration.")
        return 1

    ok_results = [r for r in all_results if r.outcome != "no_entry"]
    miss_rate = all_misses_count / all_signals_count if all_signals_count else 0.0

    print(f"\n{'='*72}")
    print(f"OVERALL SUMMARY  n_signals={all_signals_count}  n_entered={len(ok_results)}  "
          f"miss_rate={miss_rate:.1%}")
    print(f"{'='*72}\n")

    if ok_results:
        ev_15m = np.mean([r.realized_r_15m for r in ok_results])
        ev_daily = np.mean([r.realized_r_daily_equiv for r in ok_results])
        mean_rr = np.mean([r.risk_reduction for r in ok_results])
        mean_imp = np.mean([r.entry_improvement for r in ok_results])
        tp1_pct = np.mean([r.outcome in ("tp1_tp2", "tp1_stop", "tp1_max") for r in ok_results])
        stop_pct = np.mean([r.outcome == "full_stop" for r in ok_results])

        print(f"  EV (15m R units)      : {_fmt(ev_15m)}")
        print(f"  EV (daily-equiv R)    : {_fmt(ev_daily)}  "
              f"(compare to daily-entry EV for this filter)")
        print(f"  Mean risk reduction   : {mean_rr:.2f}×  (15m stop / daily ATR)")
        print(f"  Mean entry improvement: {mean_imp:+.3f}× daily ATR  "
              f"(+ve = entered at better price)")
        print(f"  TP1 hit rate          : {tp1_pct:.1%}")
        print(f"  Full stop rate        : {stop_pct:.1%}")
        print()

        # Compute daily reference EV for the same signals
        daily_ref = [r.daily_realized_r for r in ok_results if np.isfinite(r.daily_realized_r)]
        if daily_ref:
            print(f"  Daily-entry EV (same signals, stop={args.stop_mult}×ATR): "
                  f"{_fmt(np.mean(daily_ref))}")
        print()

        # Breakdowns
        print_summary_table(
            "By direction",
            all_results,
            lambda r: r.direction,
        )
        print_summary_table(
            "By lower_relation",
            all_results,
            lambda r: r.lower_relation,
        )
        print_summary_table(
            "By direction × lower_relation",
            all_results,
            lambda r: f"{r.direction} / l={r.lower_relation}",
        )

        # Entry improvement by lower_relation (the key diagnostic)
        print("\n=== Entry timing: wait_bars and entry_improvement by lower_relation ===")
        print(f"  {'lower_rel':<12s}  {'n_ok':>4s}  {'mean_wait':>10s}  {'mean_entry_imp':>14s}  {'mean_risk_red':>13s}")
        print(f"  {'-'*60}")
        for lr in sorted({r.lower_relation for r in ok_results}):
            sub = [r for r in ok_results if r.lower_relation == lr]
            if not sub:
                continue
            mw = np.mean([r.wait_bars for r in sub])
            mi = np.mean([r.entry_improvement for r in sub])
            mr = np.mean([r.risk_reduction for r in sub])
            print(f"  {lr:<12s}  {len(sub):>4d}  {mw:>9.1f}b  {mi:>+13.3f}× ATR  {mr:>12.3f}×")

    # Save CSV
    out_path = args.output
    if out_path is None:
        pool_lower = pool_label.lower()
        out_path = str(DATA_DIR.parent / "review" / f"rr_intraday_{pool_lower}.csv")

    df = pd.DataFrame([vars(r) for r in all_results])
    df.to_csv(out_path, index=False)
    print(f"\nPer-trade CSV → {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
