"""Production expiry-month rule (user-locked 2026-06-12):

    期权到期日如果有 2 周以上选本月，要不然选次月
    — nearest listed option month when its OPTION expiry is >= 14 days
    from the signal, otherwise the NEXT listed month.

Option expiry != futures expiry: SHFE commodity options stop trading on
the 5th-to-last trading day of the month BEFORE the delivery month.
"""
from __future__ import annotations

from datetime import date

from engine.options.expiry_select import (
    approx_option_expiry,
    select_expiry_month,
)


def test_option_expiry_is_month_before_delivery():
    # au2412 options expire late November 2024, NOT December
    e = approx_option_expiry(2024, 12)
    assert e.year == 2024 and e.month == 11
    assert 20 <= e.day <= 28      # ~5 trading days before month end


def test_two_weeks_or_more_picks_current_month():
    # ag2412 option expiry ~2024-11-24; signal 14+ days before it
    months = ["2412", "2501"]
    got = select_expiry_month(date(2024, 11, 7), months, "ag")
    assert got == "2412"


def test_under_two_weeks_rolls_to_next_month():
    months = ["2412", "2501"]
    got = select_expiry_month(date(2024, 11, 15), months, "ag")
    assert got == "2501"


def test_bimonthly_listing_rolls_two_calendar_months():
    # au-style listing: next listed month after 2412 is 2502
    months = ["2412", "2502", "2504"]
    got = select_expiry_month(date(2024, 11, 15), months, "au")
    assert got == "2502"


def test_already_expired_months_skipped():
    months = ["2410", "2412", "2501"]
    got = select_expiry_month(date(2024, 11, 7), months, "ag")
    assert got == "2412"      # 2410 options long expired


def test_explicit_expiries_override_approximation():
    # backtest path: chain-end dates (true option expiries) supplied
    months = ["2412", "2501"]
    expiries = {"2412": date(2024, 11, 20), "2501": date(2024, 12, 24)}
    # 13 days to 2412 expiry -> roll to 2501
    assert select_expiry_month(date(2024, 11, 7), months, "ag",
                               expiries=expiries) == "2501"


def test_no_candidate_returns_none():
    assert select_expiry_month(date(2026, 1, 5), ["2408"], "ag") is None


# --- select_expiry_exact（US OCC 精确到期，t_aa79fb13）---------------------
def test_exact_nearest_at_least_14d():
    from engine.options.expiry_select import select_expiry_exact
    exps = [date(2025, 1, 10), date(2025, 1, 31), date(2025, 2, 21)]
    # 2025-01-02 距 01-10 仅 8d → 滚到 01-31（同月 weekly，月粒度区分不了）
    assert select_expiry_exact(date(2025, 1, 2), exps) == date(2025, 1, 31)
    # 距 01-10 恰 14d → 选 01-10
    assert select_expiry_exact(date(2024, 12, 27), exps) == date(2025, 1, 10)


def test_exact_no_candidate_returns_none():
    from engine.options.expiry_select import select_expiry_exact
    assert select_expiry_exact(date(2025, 3, 1), [date(2025, 3, 7)]) is None
    assert select_expiry_exact(date(2025, 3, 1), []) is None
