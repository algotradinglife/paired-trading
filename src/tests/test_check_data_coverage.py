"""Core verdict logic of scripts/check_data_coverage.py (read-only probe)."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from scripts.check_data_coverage import (
    check_continuous_coverage,
    check_options_depth,
    check_us_hourly_years,
)


def _bar(dt: datetime, px: float = 100.0, vol: float = 5000.0) -> dict:
    return {
        "datetime": dt, "open": px, "high": px + 1, "low": px - 1,
        "close": px, "volume": vol, "turnover": px * vol, "open_interest": 0.0,
    }


def _write(root, folder, name, bars):
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(d / f"{name}.parquet", index=False)


def test_continuous_coverage_pass_and_miss(tmp_path):
    days = pd.bdate_range("2021-02-01", "2026-06-10")
    _write(tmp_path, "daily", "SHFE.rb2110",
           [_bar(d.to_pydatetime()) for d in days[:300]])
    _write(tmp_path, "daily", "SHFE.rb2210",
           [_bar(d.to_pydatetime()) for d in days[250:]])
    ok = check_continuous_coverage(
        tmp_path, "SHFE", "rb",
        target_start=date(2021, 9, 1), as_of=date(2026, 6, 12),
    )
    assert ok.status == "OK"
    assert ok.start <= date(2021, 9, 1)

    # cu: only recent months -> MISS with the actual start reported
    _write(tmp_path, "daily", "SHFE.cu2607",
           [_bar(d.to_pydatetime()) for d in days[-200:]])
    miss = check_continuous_coverage(
        tmp_path, "SHFE", "cu",
        target_start=date(2021, 9, 1), as_of=date(2026, 6, 12),
    )
    assert miss.status == "MISS"
    assert miss.start > date(2021, 9, 1)

    absent = check_continuous_coverage(
        tmp_path, "DCE", "p",
        target_start=date(2021, 9, 1), as_of=date(2026, 6, 12),
    )
    assert absent.status == "MISS"
    assert absent.start is None


def test_us_hourly_years_detects_hole(tmp_path):
    rows = []
    for year, n in ((2021, 2000), (2022, 1000), (2023, 3900)):  # 2022 hole
        ts = pd.date_range(f"{year}-01-04", periods=n, freq="h")
        rows += [_bar(t.to_pydatetime()) for t in ts]
    _write(tmp_path, "hour", "SPY.AMEX", rows)
    res = check_us_hourly_years(
        tmp_path, "SPY", years=(2021, 2022, 2023),
        min_bars={2021: 1800, "default": 3500},
    )
    assert res.status == "MISS"
    assert "2022" in res.detail and "2021" not in res.detail

    # 2021 (half-year nominal coverage) passes with its lower threshold
    res2 = check_us_hourly_years(
        tmp_path, "SPY", years=(2021, 2023),
        min_bars={2021: 1800, "default": 3500},
    )
    assert res2.status == "OK"


def test_options_depth_checks_put_call_and_history(tmp_path):
    _write(tmp_path, "daily", "SHFE.ag2412C8300",
           [_bar(datetime(2024, 3, 1))])
    _write(tmp_path, "daily", "SHFE.ag2412P8300",
           [_bar(datetime(2024, 3, 1))])
    ok = check_options_depth(tmp_path, "ag", target_earliest=date(2024, 7, 1))
    assert ok.status == "OK"

    # au: calls only, recent only -> MISS mentions both problems
    _write(tmp_path, "daily", "SHFE.au2607C780",
           [_bar(datetime(2026, 5, 1))])
    miss = check_options_depth(tmp_path, "au", target_earliest=date(2024, 7, 1))
    assert miss.status == "MISS"
    assert "no puts" in miss.detail

    absent = check_options_depth(tmp_path, "sc", target_earliest=date(2024, 7, 1))
    assert absent.status == "MISS"
