"""CN silver (ag) OTM call option selector.

Selects OTM call strikes ranked by distance from underlying, choosing
the nearest expiry with 20-60 DTE from signal_date.

SHFE ag options expire on the 17th of the expiry month (or prior
business day if the 17th is a weekend/holiday). We approximate using
the fixed 17th and add a one-business-day buffer when it falls on a
weekend; holiday adjustments are not applied (acceptable for planning
purposes — actual expiry should be confirmed before execution).

ag strike spacing: 100 yuan/gram (CNY/kg × 1000 converts, but ag
quotes are already per gram on SHFE options).

OTM rank percentage offsets derived from prior analysis of realized
ag OTM chains:
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

# ag expiry day of month (approximate — actual expiry is last trading day
# on or before the 17th, adjusted for holidays by the exchange)
_AG_EXPIRY_DOM: int = 17


def _expiry_date_for_month(year: int, month: int) -> date:
    """Return approximate expiry date for an ag contract (SHFE).

    Uses the 17th of the month. When the 17th is Saturday, bumps back to
    Friday (16th). When Sunday, bumps back to Friday (15th). No holiday
    calendar applied.
    """
    d = date(year, month, _AG_EXPIRY_DOM)
    weekday = d.weekday()  # 0=Mon … 6=Sun
    if weekday == 5:    # Saturday → prior Friday (16th)
        d = date(year, month, 16)
    elif weekday == 6:  # Sunday → prior Friday (15th)
        d = date(year, month, 15)
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
    """Format (year, month) as two-digit-year + zero-padded month, e.g. 2501."""
    return f"{year % 100:02d}{month:02d}"


def _round_to_100(price: float) -> int:
    """Round price to nearest 100 yuan/gram."""
    return int(round(price / 100.0) * 100)


def select_otm_calls(
    underlying_price: float,
    signal_date: date,
    n_strikes: int = 3,
    mm_target_pct: float | None = None,
) -> list[dict]:
    """Return up to n_strikes OTM call options for ag, sorted by OTM distance.

    Expiry selection: first contract with 20-60 DTE from signal_date.
    If no contract lands in that window, the nearest future contract
    with DTE >= 20 is used as a fallback (e.g. if the window is
    temporarily uncovered).

    Each returned dict contains:
      strike          (int)   strike price in yuan/gram
      otm_pct         (float) percentage above underlying, e.g. 1.71
      expiry_month    (str)   YYMM format, e.g. "2507"
      contract_sym    (str)   e.g. "ag2507c8300"
      days_to_expiry  (int)   calendar DTE from signal_date to expiry
      mm_target_pct   (float|None)  measured-move target % (passed through)
      is_mm_strike    (bool)  True for the strike closest to mm_target_pct

    Args:
        underlying_price: Current ag futures price (yuan/gram).
        signal_date:      Date of the bottom signal.
        n_strikes:        Number of OTM strikes to return (default 3).
        mm_target_pct:    Measured-move target as % above underlying (e.g. 3.2
                          means target is 3.2% above entry). When provided and
                          in the 0-10% range, the result closest to this target
                          is tagged with is_mm_strike=True. Values >10% are
                          treated as None (MM unreliable beyond 10% per backtest).

    Returns:
        List of dicts sorted by otm_pct ascending (nearest OTM first).
        Empty list if no suitable expiry found (should not happen in
        normal operation within 6 months).
    """
    # Pick expiry: first month with 20-60 DTE; fallback to nearest ≥20 DTE
    chosen_expiry: Optional[date] = None
    chosen_ym: Optional[tuple[int, int]] = None
    fallback_expiry: Optional[date] = None
    fallback_ym: Optional[tuple[int, int]] = None

    for year, month in _candidate_expiry_months(signal_date):
        expiry = _expiry_date_for_month(year, month)
        dte = (expiry - signal_date).days
        if dte < 20:
            continue
        if fallback_expiry is None:
            fallback_expiry = expiry
            fallback_ym = (year, month)
        if dte <= 60:
            chosen_expiry = expiry
            chosen_ym = (year, month)
            break

    if chosen_expiry is None:
        # Use fallback (DTE >= 20, even if > 60)
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
        strike = _round_to_100(raw_strike)
        # Ensure strictly above underlying
        if strike <= underlying_price:
            strike += 100
        # Ensure no duplicate strike across ranks (increment until unique)
        while strike in seen_strikes:
            strike += 100
        seen_strikes.add(strike)

        actual_otm_pct = (strike / underlying_price - 1.0) * 100.0
        contract_sym = f"ag{expiry_code}c{strike}"

        results.append({
            "rank": rank_idx,
            "strike": strike,
            "otm_pct": round(actual_otm_pct, 2),
            "expiry_month": expiry_code,
            "expiry_date": chosen_expiry.isoformat(),
            "contract_sym": contract_sym,
            "days_to_expiry": dte,
            "mm_target_pct": None,   # filled below
            "is_mm_strike": False,   # filled below
        })

    # Sort by otm_pct ascending (nearest OTM first)
    results.sort(key=lambda d: d["otm_pct"])

    # Tag MM strike: the one whose otm_pct is closest to mm_target_pct.
    # Only applied when target is in [0, 10]% — beyond 10% hit rate is <20%.
    effective_mm = mm_target_pct if (mm_target_pct is not None and 0 < mm_target_pct <= 10.0) else None
    for r in results:
        r["mm_target_pct"] = effective_mm
    if effective_mm is not None and results:
        mm_idx = min(range(len(results)), key=lambda i: abs(results[i]["otm_pct"] - effective_mm))
        results[mm_idx]["is_mm_strike"] = True

    return results


# ---------------------------------------------------------------------------
# Black-Scholes IV back-out via bisection
# ---------------------------------------------------------------------------

def _bs_call_price(
    S: float, K: float, T: float, r: float, sigma: float
) -> float:
    """Black-Scholes European call price.

    Args:
        S:     Underlying price.
        K:     Strike price.
        T:     Time to expiry in years.
        r:     Risk-free rate (continuous compounding).
        sigma: Volatility (annualised, e.g. 0.20 for 20%).

    Returns:
        Call option theoretical price. Returns intrinsic value when T<=0
        or sigma<=0 to avoid division-by-zero.
    """
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    def _ncdf(x: float) -> float:
        # Abramowitz & Stegun approximation — no scipy needed
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


def estimate_iv(
    option_price: float,
    strike: float,
    underlying: float,
    days_to_expiry: int,
    r: float = 0.02,
) -> float | None:
    """Back out implied volatility from a market option price via bisection.

    Uses Black-Scholes European call formula. Returns None when:
    - The market price is below intrinsic value (no IV solution possible).
    - Bisection fails to converge within 200 iterations.
    - days_to_expiry <= 0.

    Args:
        option_price:    Market price of the call option.
        strike:          Strike price.
        underlying:      Current underlying (futures) price.
        days_to_expiry:  Calendar days to option expiry.
        r:               Risk-free rate (default 2%, annual continuous).

    Returns:
        Implied volatility as a fraction (e.g. 0.17 = 17%) or None.
    """
    if days_to_expiry <= 0:
        return None

    T = days_to_expiry / 365.0
    intrinsic = max(underlying - strike, 0.0)

    # Price below intrinsic → no BS solution
    if option_price < intrinsic - 1e-9:
        return None

    # Bisection search over [0.001, 20.0] (0.1% – 2000% IV)
    lo_sigma, hi_sigma = 0.001, 20.0
    lo_price = _bs_call_price(underlying, strike, T, r, lo_sigma)
    hi_price = _bs_call_price(underlying, strike, T, r, hi_sigma)

    if option_price < lo_price or option_price > hi_price:
        return None  # Price outside solvable range

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

def lookup_option_price(
    contract_sym: str,
    signal_date: date,
    data_dir: Path,
) -> float | None:
    """Return the close price of a contract on or before signal_date.

    Search order:
      1. {contract_sym}_{YYYYMMDD}_daily.json  — exact or nearest date ≤ signal_date
      2. {contract_sym}_daily.json              — rolling file fallback

    For matched files the bar whose Unix timestamp falls closest to but not
    after signal_date (midnight UTC) is returned. Returns None if no file
    exists or no valid bar is found.
    """
    # Use end-of-day (23:59:59 UTC) so that bars timestamped during the
    # trading session on signal_date (e.g. 01:00 UTC for CN morning open)
    # are included.
    signal_ts = datetime(signal_date.year, signal_date.month, signal_date.day,
                         23, 59, 59, tzinfo=timezone.utc).timestamp()

    # ---- collect candidate dated files (pattern: contract_sym_YYYYMMDD_daily.json) ----
    dated_files: list[tuple[date, Path]] = []
    sym_lower = contract_sym.lower()
    expected_prefix = f"{sym_lower}_"
    for p in data_dir.glob(f"{sym_lower}_*_daily.json"):
        stem = p.stem  # strip .json
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

    # Sort by date descending; pick the most recent file whose date ≤ signal_date
    dated_files.sort(key=lambda x: x[0], reverse=True)
    candidate_path: Path | None = None
    for file_date, path in dated_files:
        if file_date <= signal_date:
            candidate_path = path
            break

    # Fallback: rolling file (no date suffix)
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

    # Find bar with the largest timestamp ≤ signal_ts (end-of-day)
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


def enrich_with_iv(
    calls: list[dict],
    signal_date: date,
    underlying_price: float,
    data_dir: Path,
) -> list[dict]:
    """Add 'option_price', 'iv', and 'price_source' fields to each call dict in-place.

    Tries TqSdk live prices first (batch call). For any contract where TqSdk
    returns None (credentials not set, network error, stale market), falls back
    to lookup_option_price() which reads local JSON files.

    Sets option_price/iv/price_source to None when no price data is available.
    Returns the same list (mutated).
    """
    from engine.options.tqsdk_feed import fetch_live_option_prices

    from datetime import date as _date
    # Live quotes are only meaningful for today's or yesterday's signals.
    # For older signals the contract may be expired or market context has shifted.
    today = _date.today()
    use_live = (today - signal_date).days <= 1

    syms = [c["contract_sym"] for c in calls]
    live_prices: dict[str, float | None] = {}
    if use_live:
        live_prices = fetch_live_option_prices(syms)  # all-None if creds not set

    for call in calls:
        sym: str = call["contract_sym"]
        dte: int = call["days_to_expiry"]
        strike: int = call["strike"]

        price = live_prices.get(sym) if use_live else None  # try live first
        source = "live"
        if price is None:
            price = lookup_option_price(sym, signal_date, data_dir)  # local fallback
            source = "file"

        call["option_price"] = round(price, 2) if price is not None else None
        call["price_source"] = source if price is not None else None
        call["iv"] = None

        if price is not None and price > 0:
            iv = estimate_iv(price, float(strike), underlying_price, dte)
            call["iv"] = round(iv * 100, 2) if iv is not None else None

    return calls
