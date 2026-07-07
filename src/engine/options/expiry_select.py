"""Production option expiry-month selection.

User-locked rule (2026-06-12): 期权到期日如果有 2 周以上选本月，
要不然选次月 — take the nearest listed option month when its OPTION
expiry is at least ``MIN_DAYS_TO_EXPIRY`` (14) days from the signal,
otherwise the NEXT listed month.

Option expiry != futures expiry: SHFE commodity options stop trading on
the 5th-to-last trading day of the month BEFORE the delivery month.
``approx_option_expiry`` mirrors the planning-grade precision of the
selectors' futures-expiry helpers (weekend-adjusted, no holiday
calendar); backtests should pass exact ``expiries`` derived from chain
data instead (the chain's last bar IS the option's last trading day).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

MIN_DAYS_TO_EXPIRY = 14


def _business_days_back(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def approx_option_expiry(delivery_year: int, delivery_month: int) -> date:
    """~5th-to-last trading day of the month before delivery (no holidays)."""
    year, month = delivery_year, delivery_month - 1
    if month == 0:
        year, month = year - 1, 12
    last = date(year, month, calendar.monthrange(year, month)[1])
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    return _business_days_back(last, 4)


def snap_strikes_to_listed(
    listed: list[float], *, targets: list[float], spot: float
) -> list[float]:
    """Map theoretical strike targets onto LISTED strikes.

    For each target pick the nearest listed strike above ``spot`` not
    already taken; subsequent picks only move upward (OTM ladder).
    Returns fewer strikes when the chain runs out.
    """
    avail = sorted({s for s in listed if s > spot})
    out: list[float] = []
    for t in targets:
        if not avail:
            break
        best = min(avail, key=lambda s: abs(s - t))
        out.append(best)
        avail = [s for s in avail if s > best]
    return out


def select_expiry_month(
    signal_date: date,
    listed_months: list[str],
    underlying: str,
    *,
    expiries: dict[str, date] | None = None,
    min_days: int = MIN_DAYS_TO_EXPIRY,
) -> str | None:
    """Pick the expiry month per the production rule.

    Args:
        signal_date: signal day.
        listed_months: listed option months, "YYMM" strings (any order).
        underlying: product code (reserved for product-specific expiry
            rules; the SHFE month-before approximation covers ag/au).
        expiries: optional exact option-expiry override per month
            (backtest: chain last-bar dates).
        min_days: the 2-week threshold.

    Returns:
        The chosen "YYMM" month, or None when no listed month has an
        option expiry >= min_days away.
    """
    def expiry_of(m: str) -> date:
        if expiries is not None and m in expiries:
            return expiries[m]
        return approx_option_expiry(2000 + int(m[:2]), int(m[2:]))

    candidates = sorted(set(listed_months))
    for m in candidates:
        if (expiry_of(m) - signal_date).days >= min_days:
            return m
    return None


def select_expiry_exact(
    signal_date: date,
    expiries: list[date],
    *,
    min_days: int = MIN_DAYS_TO_EXPIRY,
) -> date | None:
    """Pick the nearest exact expiry >= ``min_days`` from the signal.

    The same production rule as ``select_expiry_month`` but on exact
    expiry dates — for US OCC chains where one month holds multiple
    expiries (weeklies) and the contract carries its exact expiry
    (OptionContract.expiry).

    Returns None when no expiry is >= min_days away.
    """
    for exp in sorted(set(expiries)):
        if (exp - signal_date).days >= min_days:
            return exp
    return None
