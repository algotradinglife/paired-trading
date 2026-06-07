"""scan_portfolio_b.py — Daily bottom×h=opposing signal scanner across all 6 Scheme B pools.

Detects MACD divergence bottom signals on the daily timeframe, enriches each
with 1h context (h=opposing = 1h trend bearish while daily predicts a bounce),
and surfaces recent candidates ranked by quality.

OOS-validated EV (walk-forward K=3, 2026-06-01, h=opposing bottoms+tops):
  Portfolio: +0.258R (fold1) / +0.126R (fold2) — PASS  [6-pool, n=1077]
  CN_BOND bottom×h=opposing: +0.978R (fold1, 100% hit) / +0.786R (fold2) — STRONG PASS
  CN_METAL heap tops: +0.942R / +1.340R after CNM1 gate (top×inter_segment disabled)

  Prior result (2026-05-31, bottoms only, n=111): fold1=+0.870R / fold2=+0.862R

Usage:
  uv run python scripts/scan_portfolio_b.py
  uv run python scripts/scan_portfolio_b.py --window-days 14
  uv run python scripts/scan_portfolio_b.py --pool CN_METAL CN_AGRI
  uv run python scripts/scan_portfolio_b.py -o data/review/scan_today.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.bpull_detector import BPullDetector
from engine.divergence.vflush_detector import VFlushDetector
from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.multi_tf_context import enrich_with_higher_tf, enrich_with_lower_tf
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


# ── Pool definitions (symbols from walk-forward backtest CSVs) ─────────────────
POOLS: dict[str, dict] = {
    "CN_INDEX": {
        "symbols": ["kq_m_cffex_ic", "kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_im"],
        "instrument_class": "cn_index_futures",
        "ev_fold1": 0.583, "ev_fold2": None,   # fold2 n=2, unreliable
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
    "CN_AGRI": {
        "symbols": [
            "kq_m_czce_cf", "kq_m_czce_ma", "kq_m_czce_sa", "kq_m_czce_sr", "kq_m_czce_ta",
            "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm", "kq_m_dce_m", "kq_m_dce_p", "kq_m_dce_y",
        ],
        "instrument_class": "czce",
        "ev_fold1": 0.250, "ev_fold2": 1.021,
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
    "CN_METAL": {
        "symbols": ["kq_m_ine_sc", "kq_m_shfe_ag", "kq_m_shfe_au", "kq_m_shfe_cu", "kq_m_shfe_rb"],
        "instrument_class": "cn_metal_futures",
        "ev_fold1": 0.673, "ev_fold2": 0.782,
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
    "US_EQUITY": {
        "symbols": ["dia", "iwm", "nvda", "qqq", "spy", "xlf", "xlk"],
        "instrument_class": "us_equity",
        "ev_fold1": 1.250, "ev_fold2": 0.375,
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
    "US_MACRO": {
        "symbols": ["gdx", "gld", "tlt"],
        "instrument_class": "us_equity",
        "ev_fold1": 0.900, "ev_fold2": 1.424,
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
    "CN_BOND": {
        "symbols": ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
        "instrument_class": "cn_futures",
        "ev_fold1": 0.978, "ev_fold2": 0.786,   # walk-forward OOS 2026-06-01 bottom×h=opposing
        "daily_suffix": "_daily.json",
        "h1_suffix":    "_60.json",
    },
}

# 6-pool Scheme B: default scan set (portfolio EV validated for these pools)
SCHEME_B_POOLS = ["CN_INDEX", "CN_AGRI", "CN_METAL", "US_EQUITY", "US_MACRO", "CN_BOND"]

# Portfolio-level EV from walk-forward OOS (2026-06-01, 6-pool Scheme B, n=1077 h=opposing)
PORTFOLIO_EV_FOLD1 = 0.258
PORTFOLIO_EV_FOLD2 = 0.126


@dataclass
class Candidate:
    pool: str
    symbol: str
    signal_date: date
    direction: str
    subtype: str
    confidence: float
    higher_relation: str   # opposing / supporting / neutral / unknown
    lower_relation: str    # leading / lagging / pivoting / unknown
    ev_fold1: float | None
    ev_fold2: float | None
    entry_close: float | None = None
    atr_est: float | None = None
    # DD line (顶底趋势线) — the two bottoms of the divergence pair
    ref_low_price: float | None = None    # first bottom price (DD anchor 1, price extreme)
    ref_low_date: date | None = None      # first bottom date
    cand_low_price: float | None = None   # second bottom price (DD anchor 2, price extreme)
    dd_slope_per_bar: float | None = None # price change per bar along the DD line
    dd_level_today: float | None = None   # DD line projected to today's bar
    # Invalidation level: if underlying closes below this, setup fails
    invalidation_level: float | None = None
    # Independent swing lows from OHLC (for main/acceleration trend line drawing)
    swing_lows: list[tuple[date, float]] = field(default_factory=list)


def find_swing_lows(
    bars: pd.DataFrame,
    lookback: int = 90,
    wing: int = 2,
    n_results: int = 3,
) -> list[tuple[date, float]]:
    """Return the last n_results local lows in the past `lookback` bars.

    A local low is a bar whose `low` is ≤ all bars within `wing` bars on each side.
    """
    start = max(0, len(bars) - lookback)
    lows_arr = bars["low"].values
    results: list[tuple[date, float]] = []
    for i in range(start + wing, len(bars) - wing):
        lo = lows_arr[i]
        if all(lo <= lows_arr[i - k] for k in range(1, wing + 1)) and \
           all(lo <= lows_arr[i + k] for k in range(1, wing + 1)):
            results.append((bars["timestamp"].iloc[i].date(), float(lo)))
    return results[-n_results:] if len(results) >= n_results else results


def load_bars(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return bar_loader.load_bars_json(path)


def _load_quant(sym: str, barstore_level: str, quant_root: Path) -> pd.DataFrame | None:
    """Load one level from BarStore; None if symbol not supported or data missing."""
    resolved = bar_loader.infer_symbol_and_mic(sym)
    if resolved is None:
        return None
    quant_sym, mic = resolved
    try:
        return bar_loader.load_bars_quant(quant_sym, mic, barstore_level, quant_root)
    except Exception:
        return None


def detect_signals(bars: pd.DataFrame, instrument_class: str):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"]
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class=instrument_class,
    )


def atr14(bars: pd.DataFrame) -> float | None:
    if len(bars) < 15:
        return None
    h = bars["high"].values[-15:]
    lo = bars["low"].values[-15:]
    c_prev = bars["close"].values[-15:]
    trs = [max(h[i] - lo[i], abs(h[i] - c_prev[i-1]), abs(lo[i] - c_prev[i-1]))
           for i in range(1, 15)]
    return sum(trs) / len(trs)


def scan_pool(pool_name: str, cfg: dict, cutoff: date, window_days: int,
              quant_root: Path | None = None) -> tuple[list[Candidate], int]:
    instrument_class = cfg["instrument_class"]
    candidates: list[Candidate] = []
    loaded = 0

    for sym in cfg["symbols"]:
        # Load daily bars (BarStore preferred, JSON fallback)
        d_bars: pd.DataFrame | None = None
        if quant_root is not None:
            d_bars = _load_quant(sym, "D", quant_root)
        if d_bars is None:
            d_path = DATA_DIR / f"{sym}{cfg['daily_suffix']}"
            d_bars = load_bars(d_path)
        if d_bars is None:
            continue
        loaded += 1

        signals = detect_signals(d_bars, instrument_class)
        recent = [s for s in signals
                  if d_bars["timestamp"].iloc[s.candidate_bar_idx].date() >= cutoff
                  and s.direction == "bottom"]

        # Load h_bars before BPull scan (BPull is independent of MACD early exit)
        h_bars: pd.DataFrame | None = None
        if quant_root is not None:
            h_bars = _load_quant(sym, "60min", quant_root)
        if h_bars is None:
            h_path = DATA_DIR / f"{sym}{cfg['h1_suffix']}"
            h_bars = load_bars(h_path)

        # ── BPull scan — cn_metal_futures only (K=3 STRONG PASS) ──────────────
        # Must run before MACD early-exit: BPull fires independently of MACD signals.
        # rb (kq_m_shfe_rb) is excluded inside BPullDetector.policy_weight().
        bpull_cands: list[Candidate] = []
        if instrument_class == "cn_metal_futures":
            bpull_det = BPullDetector()
            for bsig in bpull_det.scan(d_bars, h_bars):
                if bsig.timestamp.date() < cutoff:
                    continue
                weight = BPullDetector.policy_weight(bsig, instrument_class, symbol=sym)
                if weight == 0.0:
                    continue
                sig_date = bsig.timestamp.date()
                entry = float(bsig.features.get("close", d_bars["close"].iloc[bsig.bar_idx]))
                bpull_cands.append(Candidate(
                    pool=pool_name,
                    symbol=sym,
                    signal_date=sig_date,
                    direction="bottom",
                    subtype="bpull",
                    confidence=weight,  # policy_weight (0.75)
                    higher_relation=bsig.higher_tf_relation or "unknown",
                    lower_relation="unknown",
                    ev_fold1=cfg["ev_fold1"],
                    ev_fold2=cfg["ev_fold2"],
                    entry_close=entry,
                    atr_est=atr14(d_bars),
                    ref_low_price=None,
                    ref_low_date=None,
                    cand_low_price=None,
                    dd_slope_per_bar=None,
                    dd_level_today=None,
                    invalidation_level=None,
                    swing_lows=find_swing_lows(d_bars),
                ))

        # ── VFlush scan — cn_metal_futures only (K=3 STRONG PASS, cu+sc only) ──────
        # Exhaustion-based V-shape flush bottoms; complements PA H2 (90% non-overlap).
        # ag+au excluded (OOS negative across K=3 folds); mirrors BPull rb exclusion.
        vflush_cands: list[Candidate] = []
        if instrument_class == "cn_metal_futures":
            vflush_det = VFlushDetector()
            for vsig in vflush_det.scan(d_bars, h_bars):
                if vsig.timestamp.date() < cutoff:
                    continue
                weight = VFlushDetector.policy_weight(vsig, instrument_class, symbol=sym)
                if weight == 0.0:
                    continue
                sig_date = vsig.timestamp.date()
                entry = float(vsig.features.get("close", d_bars["close"].iloc[vsig.bar_idx]))
                vflush_cands.append(Candidate(
                    pool=pool_name,
                    symbol=sym,
                    signal_date=sig_date,
                    direction="bottom",
                    subtype="vflush",
                    confidence=weight,  # policy_weight (0.65)
                    higher_relation=vsig.higher_tf_relation or "unknown",
                    lower_relation="unknown",
                    ev_fold1=cfg["ev_fold1"],
                    ev_fold2=cfg["ev_fold2"],
                    entry_close=entry,
                    atr_est=atr14(d_bars),
                    ref_low_price=None,
                    ref_low_date=None,
                    cand_low_price=None,
                    dd_slope_per_bar=None,
                    dd_level_today=None,
                    invalidation_level=None,
                    swing_lows=find_swing_lows(d_bars),
                ))

        if not recent and not bpull_cands and not vflush_cands:
            continue

        # Enrich MACD signals with HTF context (h_bars already loaded above)
        if h_bars is not None:
            recent = enrich_with_higher_tf(
                recent, d_bars, h_bars, higher_tf_level_id="60m",
            )
        m_bars: pd.DataFrame | None = None
        if quant_root is not None:
            m_bars = _load_quant(sym, "15min", quant_root)
        if m_bars is None:
            m_path = DATA_DIR / f"{sym}_15.json"
            m_bars = load_bars(m_path)
        if m_bars is not None:
            recent = enrich_with_lower_tf(
                recent, d_bars, m_bars, lower_tf_level_id="15m",
            )

        slows = find_swing_lows(d_bars)
        last_bar_idx = len(d_bars) - 1

        for sig in recent:
            if apply_policy(sig, instrument_class=instrument_class).weight == 0.0:
                continue
            ctx = sig.multi_tf_context or {}
            higher_rel = ctx.get("higher_relation", "unknown")
            lower_rel  = ctx.get("lower_relation", "unknown")
            sig_date = d_bars["timestamp"].iloc[sig.candidate_bar_idx].date()
            entry = float(d_bars["close"].iloc[sig.candidate_bar_idx])

            # DD line: anchored on price extremes (lows), not closes
            ref_price  = float(sig.price_side.reference_value)
            cand_low   = float(sig.price_side.candidate_value)
            ref_date   = d_bars["timestamp"].iloc[sig.reference_bar_idx].date()
            bars_span  = sig.candidate_bar_idx - sig.reference_bar_idx
            dd_slope   = (cand_low - ref_price) / bars_span if bars_span > 0 else None
            dd_today   = (ref_price + dd_slope * (last_bar_idx - sig.reference_bar_idx)
                          if dd_slope is not None else None)

            inval = (sig.context_features or {}).get("invalidation_level")

            candidates.append(Candidate(
                pool=pool_name,
                symbol=sym,
                signal_date=sig_date,
                direction=sig.direction,
                subtype=sig.subtype,
                confidence=sig.confidence,
                higher_relation=higher_rel,
                lower_relation=lower_rel,
                ev_fold1=cfg["ev_fold1"],
                ev_fold2=cfg["ev_fold2"],
                entry_close=entry,
                atr_est=atr14(d_bars),
                ref_low_price=ref_price,
                ref_low_date=ref_date,
                cand_low_price=cand_low,
                dd_slope_per_bar=dd_slope,
                dd_level_today=dd_today,
                invalidation_level=inval,
                swing_lows=slows,
            ))

        candidates.extend(bpull_cands)
        candidates.extend(vflush_cands)

    return candidates, loaded


def ev_label(c: Candidate) -> str:
    parts = []
    if c.ev_fold1 is not None:
        parts.append(f"F1={c.ev_fold1:+.2f}R")
    if c.ev_fold2 is not None:
        parts.append(f"F2={c.ev_fold2:+.2f}R")
    return " ".join(parts) if parts else "—"


def priority_score(c: Candidate) -> tuple:
    opp = 1 if c.higher_relation == "opposing" else 0
    ev = (c.ev_fold1 or 0) + (c.ev_fold2 or 0)
    return (opp, ev, c.confidence)


def main() -> int:
    p = argparse.ArgumentParser(description="Scan Scheme B pools for bottom×h=opposing signals")
    p.add_argument("--pool", nargs="+", choices=list(POOLS), default=SCHEME_B_POOLS,
                   help="pools to scan (default: 6-pool Scheme B)")
    p.add_argument("--window-days", type=int, default=7,
                   help="look-back window in calendar days (default 7)")
    p.add_argument("-o", "--output", type=Path, help="write JSON results here")
    p.add_argument("--all-directions", action="store_true",
                   help="show all bottom signals, not just h=opposing")
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    args = p.parse_args()

    cutoff = date.today() - timedelta(days=args.window_days)
    print(f"Scheme B Portfolio Scanner — bottom × h=opposing")
    print(f"Window : last {args.window_days} days (≥ {cutoff})")
    print(f"Pools  : {', '.join(args.pool)}")
    print(f"OOS EV : portfolio fold1={PORTFOLIO_EV_FOLD1:+.3f}R  fold2={PORTFOLIO_EV_FOLD2:+.3f}R")
    print()

    all_candidates: list[Candidate] = []
    total_loaded = 0
    for pool_name in args.pool:
        cfg = POOLS[pool_name]
        cands, loaded = scan_pool(pool_name, cfg, cutoff, args.window_days, args.quant_data_root)
        all_candidates.extend(cands)
        total_loaded += loaded

    # Always split by h=opposing so the groups are well-defined regardless of flag.
    # --all-directions merely controls whether the non-opposing group is printed.
    opposing = [c for c in all_candidates if c.higher_relation == "opposing"]
    other    = [c for c in all_candidates if c.higher_relation != "opposing"]

    opposing.sort(key=priority_score, reverse=True)
    other.sort(key=priority_score, reverse=True)

    def _fmt_date_short(d: date) -> str:
        return d.strftime("%b-%d")

    def print_table(rows: list[Candidate], header: str) -> None:
        if not rows:
            return
        print(f"{'─'*90}")
        print(f"  {header}  (n={len(rows)})")
        print(f"{'─'*90}")
        print(f"  {'Pool':<12} {'Symbol':<22} {'Date':<11} {'Sub':<10} "
              f"{'Conf':<5} {'1h':<10} {'15m':<10} {'OOS EV':<20} {'ATR':>7}")
        print(f"  {'-'*85}")
        for c in rows:
            atr_str = f"{c.atr_est:.2f}" if c.atr_est else "—"
            print(f"  {c.pool:<12} {c.symbol:<22} {c.signal_date!s:<11} "
                  f"{c.subtype:<10} {c.confidence:.2f}  "
                  f"{c.higher_relation:<10} {c.lower_relation:<10} "
                  f"{ev_label(c):<20} {atr_str:>7}")
            # Entry level detail line
            parts: list[str] = []
            if c.ref_low_price is not None and c.ref_low_date is not None:
                cand_lo  = c.cand_low_price if c.cand_low_price is not None else c.entry_close
                slope_str = (f"slope={c.dd_slope_per_bar:+.3f}/bar"
                             if c.dd_slope_per_bar is not None else "")
                today_str = (f"  DD_now={c.dd_level_today:.2f}"
                             if c.dd_level_today is not None else "")
                inval_str = (f"  inval={c.invalidation_level:.2f}"
                             if c.invalidation_level is not None else "")
                parts.append(
                    f"DD[{c.ref_low_price:.2f}({_fmt_date_short(c.ref_low_date)})"
                    f"→{cand_lo:.2f}({_fmt_date_short(c.signal_date)})]"
                    f"  {slope_str}{today_str}{inval_str}"
                )
            if c.swing_lows:
                slo = "  ".join(f"{p:.2f}({_fmt_date_short(d)})" for d, p in c.swing_lows)
                parts.append(f"sLow:[{slo}]")
            if parts:
                print(f"  {'':36}↳ {parts[0]}")
                if len(parts) > 1:
                    print(f"  {'':38}{parts[1]}")
        print()

    if opposing:
        print_table(opposing, "★ PRIORITY — bottom × h=opposing (OOS-validated)")
    else:
        print(f"  No bottom × h=opposing signals in last {args.window_days} days.")
        print()

    if other and args.all_directions:
        print_table(other, "  bottom (h=supporting / neutral / unknown)")

    # Summary
    total_syms = sum(len(POOLS[p]["symbols"]) for p in args.pool)
    print(f"Scanned {total_loaded}/{total_syms} symbols with data  |  "
          f"bottom signals found: {len(all_candidates)}  |  "
          f"h=opposing: {len(opposing)}")

    if args.output:
        out = {
            "scan_date": date.today().isoformat(),
            "window_days": args.window_days,
            "portfolio_ev": {"fold1": PORTFOLIO_EV_FOLD1, "fold2": PORTFOLIO_EV_FOLD2},
            "opposing": [
                {"pool": c.pool, "symbol": c.symbol, "date": c.signal_date.isoformat(),
                 "subtype": c.subtype, "confidence": c.confidence,
                 "higher_relation": c.higher_relation, "lower_relation": c.lower_relation,
                 "ev_fold1": c.ev_fold1, "ev_fold2": c.ev_fold2,
                 "entry_close": c.entry_close, "atr_est": c.atr_est,
                 "invalidation_level": c.invalidation_level,
                 "dd_line": {
                     "ref_low_price": c.ref_low_price,
                     "ref_low_date": c.ref_low_date.isoformat() if c.ref_low_date else None,
                     "cand_low_price": c.cand_low_price,
                     "signal_date": c.signal_date.isoformat(),
                     "slope_per_bar": c.dd_slope_per_bar,
                     "level_today": c.dd_level_today,
                 },
                 "swing_lows": [
                     {"date": d.isoformat(), "price": p} for d, p in c.swing_lows
                 ]}
                for c in opposing
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print(f"JSON → {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
