"""CN gold (au) OTM call option selector.

Selects OTM call strikes ranked by distance from underlying, choosing
the nearest expiry with 20-60 DTE from signal_date.

SHFE au options expire on the last trading day of the expiry month.
We approximate using the last calendar day of the month adjusted for
weekends (Saturday→Friday, Sunday→Friday). Holiday adjustments are not
applied (acceptable for planning purposes — confirm before execution).

au strike spacing: 8 yuan/gram in practice for current contracts (the
minimum tick is 2 yuan/gram but SHFE lists strikes at 8-yuan intervals
near current price levels). `_round_to_8()` rounds to nearest 8.

OTM rank percentage offsets — same as ag (derived from realized OTM
chain analysis):
  Rank 1 (near ATM / 1st OTM): ~1.71% above underlying
  Rank 2                       : ~2.93% above underlying
  Rank 3                       : ~4.14% above underlying
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# OTM offset for each rank (fraction above underlying price)
_OTM_OFFSETS: list[float] = [0.0171, 0.0293, 0.0414]

# au strike rounding granularity (yuan/gram). SHFE lists au option strikes
# at 8-yuan intervals for contracts with underlying ~700-1000 yuan/gram.
_AU_STRIKE_STEP: int = 8

# Minimum DTE for au options. Set to 25 (vs ag's 20) to avoid near-expiry
# front-month contracts which have poor liquidity and high gamma risk for au.
# A 21-DTE au contract near end-of-month has effectively no time cushion.
_AU_MIN_DTE: int = 25


def _round_to_step(price: float, step: int = _AU_STRIKE_STEP) -> int:
    """Round price to nearest multiple of step."""
    return int(round(price / step) * step)


def _expiry_date_for_month_au(year: int, month: int) -> date:
    """Return approximate expiry date for an au contract (SHFE).

    SHFE au options expire on the last trading day of the expiry month.
    We use the last calendar day of the month adjusted for weekends:
      Saturday → prior Friday
      Sunday   → prior Friday
    No holiday calendar applied.
    """
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    weekday = d.weekday()  # 0=Mon … 6=Sun
    if weekday == 5:    # Saturday → Friday (last_day - 1)
        d = date(year, month, last_day - 1)
    elif weekday == 6:  # Sunday → Friday (last_day - 2)
        d = date(year, month, last_day - 2)
    return d


def _candidate_expiry_months(signal_date: date) -> list[tuple[int, int]]:
    """Generate (year, month) pairs for the next 6 months from signal_date."""
    candidates = []
    year, month = signal_date.year, signal_date.month
    for _ in range(6):
        candidates.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return candidates


def _yymm(year: int, month: int) -> str:
    """Format (year, month) as two-digit-year + zero-padded month, e.g. 2507."""
    return f"{year % 100:02d}{month:02d}"


def select_otm_calls_au(
    underlying_price: float,
    signal_date: date,
    n_strikes: int = 3,
    mm_target_pct: float | None = None,
) -> list[dict]:
    """Return up to n_strikes OTM call options for au, sorted by OTM distance.

    Expiry selection: first contract with 25-60 DTE from signal_date.
    The floor is 25 (not 20 as for ag) to avoid near-expiry front-month
    contracts which have poor liquidity in au. If no contract lands in
    that window, the nearest future contract with DTE >= 25 is used as
    a fallback.

    Each returned dict contains:
      strike          (int)   strike price in yuan/gram
      otm_pct         (float) percentage above underlying, e.g. 1.71
      expiry_month    (str)   YYMM format, e.g. "2507"
      contract_sym    (str)   e.g. "au2507c800"
      days_to_expiry  (int)   calendar DTE from signal_date to expiry

    Args:
        underlying_price: Current au futures price (yuan/gram).
        signal_date:      Date of the bottom signal.
        n_strikes:        Number of OTM strikes to return (default 3).

    Returns:
        List of dicts sorted by otm_pct ascending (nearest OTM first).
        Empty list if no suitable expiry found.
    """
    chosen_expiry: Optional[date] = None
    chosen_ym: Optional[tuple[int, int]] = None
    fallback_expiry: Optional[date] = None
    fallback_ym: Optional[tuple[int, int]] = None

    for year, month in _candidate_expiry_months(signal_date):
        expiry = _expiry_date_for_month_au(year, month)
        dte = (expiry - signal_date).days
        if dte < _AU_MIN_DTE:
            continue
        if fallback_expiry is None:
            fallback_expiry = expiry
            fallback_ym = (year, month)
        if dte <= 60:
            chosen_expiry = expiry
            chosen_ym = (year, month)
            break

    if chosen_expiry is None:
        chosen_expiry = fallback_expiry
        chosen_ym = fallback_ym

    if chosen_expiry is None or chosen_ym is None:
        return []

    dte = (chosen_expiry - signal_date).days
    expiry_code = _yymm(chosen_ym[0], chosen_ym[1])

    results = []
    seen_strikes: set[int] = set()
    for rank_idx, offset in enumerate(_OTM_OFFSETS[:n_strikes], start=1):
        raw_strike = underlying_price * (1.0 + offset)
        strike = _round_to_step(raw_strike)
        # Ensure strictly above underlying (round up by one step if needed)
        if strike <= underlying_price:
            strike += _AU_STRIKE_STEP
        # Ensure no duplicate strike across ranks (increment until unique)
        while strike in seen_strikes:
            strike += _AU_STRIKE_STEP
        seen_strikes.add(strike)

        actual_otm_pct = (strike / underlying_price - 1.0) * 100.0
        contract_sym = f"au{expiry_code}c{strike}"

        results.append({
            "rank": rank_idx,
            "strike": strike,
            "otm_pct": round(actual_otm_pct, 2),
            "expiry_month": expiry_code,
            "expiry_date": chosen_expiry.isoformat(),
            "contract_sym": contract_sym,
            "days_to_expiry": dte,
            "mm_target_pct": None,
            "is_mm_strike": False,
        })

    results.sort(key=lambda d: d["otm_pct"])

    effective_mm = mm_target_pct if (mm_target_pct is not None and 0 < mm_target_pct <= 10.0) else None
    for r in results:
        r["mm_target_pct"] = effective_mm
    if effective_mm is not None and results:
        mm_idx = min(range(len(results)), key=lambda i: abs(results[i]["otm_pct"] - effective_mm))
        results[mm_idx]["is_mm_strike"] = True

    return results


# ---------------------------------------------------------------------------
# Black-Scholes IV back-out via bisection (duplicated from cn_ag_selector
# to keep this module self-contained; both use identical implementations)
# ---------------------------------------------------------------------------

def _bs_call_price(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """Black-Scholes European call price."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    def _ncdf(x: float) -> float:
        if x < 0:
            return 1.0 - _ncdf(-x)
        t = 1.0 / (1.0 + 0.2316419 * x)
        poly = t * (0.319381530
                    + t * (-0.356563782
                           + t * (1.781477937
                                  + t * (-1.821255978
                                         + t * 1.330274429))))
        return 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x ** 2) * poly

    return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)


def estimate_iv_au(
    option_price: float,
    strike: float,
    underlying: float,
    days_to_expiry: int,
    r: float = 0.02,
) -> float | None:
    """Back out implied volatility from a market option price via bisection.

    Uses Black-Scholes European call formula. Returns None when:
    - The market price is below intrinsic value.
    - Bisection fails to converge within 200 iterations.
    - days_to_expiry <= 0.

    Returns:
        Implied volatility as a fraction (e.g. 0.17 = 17%) or None.
    """
    if days_to_expiry <= 0:
        return None

    T = days_to_expiry / 365.0
    intrinsic = max(underlying - strike, 0.0)

    if option_price < intrinsic - 1e-9:
        return None

    lo_sigma, hi_sigma = 0.001, 20.0
    lo_price = _bs_call_price(underlying, strike, T, r, lo_sigma)
    hi_price = _bs_call_price(underlying, strike, T, r, hi_sigma)

    if option_price < lo_price or option_price > hi_price:
        return None

    for _ in range(200):
        mid_sigma = (lo_sigma + hi_sigma) / 2.0
        mid_price = _bs_call_price(underlying, strike, T, r, mid_sigma)
        if abs(mid_price - option_price) < 1e-8:
            return mid_sigma
        if mid_price < option_price:
            lo_sigma = mid_sigma
        else:
            hi_sigma = mid_sigma
        if hi_sigma - lo_sigma < 1e-10:
            break

    return (lo_sigma + hi_sigma) / 2.0


# ---------------------------------------------------------------------------
# Historical price lookup + IV enrichment
# ---------------------------------------------------------------------------

def lookup_option_price_au(
    contract_sym: str,
    signal_date: date,
    data_dir: Path,
) -> float | None:
    """Return the close price of an au contract on or before signal_date.

    Mirrors cn_ag_selector.lookup_option_price() — same search strategy:
      1. {contract_sym}_{YYYYMMDD}_daily.json  — most recent dated file ≤ signal_date
      2. {contract_sym}_daily.json              — rolling file fallback
    """
    signal_ts = datetime(signal_date.year, signal_date.month, signal_date.day,
                         23, 59, 59, tzinfo=timezone.utc).timestamp()

    dated_files: list[tuple[date, Path]] = []
    sym_lower = contract_sym.lower()
    expected_prefix = f"{sym_lower}_"
    for p in data_dir.glob(f"{sym_lower}_*_daily.json"):
        stem = p.stem
        if stem.endswith("_daily"):
            stem = stem[:-6]
        # Strict format: {sym_lower}_{YYYYMMDD} — skip _shf_ and other annotated variants
        if not stem.startswith(expected_prefix):
            continue
        date_part = stem[len(expected_prefix):]
        if len(date_part) != 8:
            continue
        try:
            file_date = datetime.strptime(date_part, "%Y%m%d").date()
        except ValueError:
            continue
        dated_files.append((file_date, p))

    dated_files.sort(key=lambda x: x[0], reverse=True)
    candidate_path: Path | None = None
    for file_date, path in dated_files:
        if file_date <= signal_date:
            candidate_path = path
            break

    if candidate_path is None:
        rolling = data_dir / f"{sym_lower}_daily.json"
        if rolling.exists():
            candidate_path = rolling

    if candidate_path is None:
        return None

    try:
        data = json.loads(candidate_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    bars = data.get("bars") if isinstance(data, dict) else data
    if not isinstance(bars, list) or not bars:
        return None

    best_bar = None
    best_ts = -1.0
    for bar in bars:
        ts = bar.get("time")
        cl = bar.get("close")
        if ts is None or cl is None:
            continue
        ts = float(ts)
        cl = float(cl)
        if cl <= 0:
            continue
        if ts <= signal_ts and ts > best_ts:
            best_ts = ts
            best_bar = cl

    return best_bar


def enrich_with_iv_au(
    calls: list[dict],
    signal_date: date,
    underlying_price: float,
    data_dir: Path,
    *,
    quant_root: Path | None = None,
) -> list[dict]:
    """Add 'option_price', 'iv', and 'price_source' fields to each au call dict in-place.

    Tries TqSdk live prices first (batch call via tqsdk_feed, which works
    for au symbols since the regex is generic). Falls back to local JSON
    files for any contract where live price is unavailable.

    Sets option_price/iv/price_source to None when no price data is available.
    Returns the same list (mutated).
    """
    from data.bar_loader import DEFAULT_QUANT_ROOT
    from data.option_store import get_store
    from engine.options.black76 import implied_vol
    from engine.options.tqsdk_feed import fetch_live_option_prices

    from datetime import date as _date
    today = _date.today()
    use_live = (today - signal_date).days <= 1

    syms = [c["contract_sym"] for c in calls]
    live_prices: dict[str, float | None] = {}
    if use_live:
        live_prices = fetch_live_option_prices(syms)  # all-None if creds not set

    store = get_store(quant_root if quant_root is not None else DEFAULT_QUANT_ROOT)

    for call in calls:
        sym: str = call["contract_sym"]
        dte: int = call["days_to_expiry"]
        strike: int = call["strike"]

        price = live_prices.get(sym) if use_live else None
        source = "live"
        if price is None:
            price = store.close_on(sym, signal_date)
            source = "store"
        if price is None:
            price = lookup_option_price_au(sym, signal_date, data_dir)
            source = "file"

        call["option_price"] = round(price, 2) if price is not None else None
        call["price_source"] = source if price is not None else None
        call["iv"] = None

        if price is not None and price > 0:
            opt_type = sym.rstrip("0123456789")[-1].upper()
            iv = implied_vol(
                price, underlying_price, float(strike), dte / 365.0,
                opt_type=opt_type,
            )
            call["iv"] = round(iv * 100, 2) if iv is not None else None

    return calls
