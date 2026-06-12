"""Snap theoretical selector contracts to LISTED, DATA-COVERED contracts.

The ag/au selectors pick expiry by pure DTE arithmetic and strikes by
rounded %OTM — blind to SHFE listings (au options list only every other
month; options expire EARLIER than their futures; strikes only as
listed). The attribution harness must measure tradable contracts:
choose the nearest listed month inside a widened DTE window whose
contracts actually have bars from the signal date (min_cover), then the
nearest listed OTM strike.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from data.option_store import OptionStore
from scripts.backtest_options_attribution import _snap_to_listed


def _bars_from(start: datetime, n: int = 60, close: float = 100.0) -> list[dict]:
    return [{
        "datetime": start + timedelta(days=i), "open": close, "high": close + 1,
        "low": close - 1, "close": close, "volume": 10.0, "turnover": close,
        "open_interest": 1.0,
    } for i in range(n)]


def _write(root, name, bars):
    d = root / "daily"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(d / f"{name}.parquet", index=False)


SIG = date(2024, 11, 1)
LIVE = datetime(2024, 10, 25)   # bars span the signal date


def test_exact_listed_and_covered_contract_kept(tmp_path):
    _write(tmp_path, "SHFE.ag2412C8200", _bars_from(LIVE))
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "ag", "ag2412c8200", 8200, 8050.0, SIG)
    assert got is not None and got["contract_sym"] == "ag2412c8200"
    assert got["snapped"] is False


def test_unlisted_month_snaps_to_covered_listed_month(tmp_path):
    # selector chose 2501 (unlisted); 2412 is listed AND covered
    _write(tmp_path, "SHFE.ag2412C8200", _bars_from(LIVE))
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "ag", "ag2501c8200", 8200, 8050.0, SIG)
    assert got is not None and got["contract_sym"] == "ag2412c8200"
    assert got["snapped"] is True


def test_expired_option_month_skipped_for_covered_one(tmp_path):
    # 2411 options stopped trading before the signal (options expire
    # earlier than futures) — must skip to the covered 2412 chain
    _write(tmp_path, "SHFE.ag2411C8200",
           _bars_from(datetime(2024, 9, 1), n=10))      # ends 2024-09-10
    _write(tmp_path, "SHFE.ag2412C8300", _bars_from(LIVE))
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "ag", "ag2411c8200", 8200, 8050.0, SIG)
    assert got is not None and got["contract_sym"] == "ag2412c8300"


def test_bimonthly_gap_covered_by_widened_window(tmp_path):
    # au-style: signal lands where the next even month is ~65-70 DTE —
    # outside the selector's 60d cap but inside the snap window
    _write(tmp_path, "SHFE.au2502C648",
           _bars_from(datetime(2024, 12, 1), n=40))
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "au", "au2501c648", 648, 640.0,
                          date(2024, 12, 19))
    assert got is not None and got["contract_sym"] == "au2502c648"


def test_unlisted_strike_snaps_to_nearest_otm(tmp_path):
    _write(tmp_path, "SHFE.ag2412C8100", _bars_from(LIVE))
    _write(tmp_path, "SHFE.ag2412C8400", _bars_from(LIVE))
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "ag", "ag2412c8200", 8200, 8050.0, SIG)
    assert got["contract_sym"] == "ag2412c8100"   # >spot 8050, closest to 8200
    assert got["snapped"] is True


def test_contract_listed_after_signal_not_covered(tmp_path):
    # codex P1: a chain whose FIRST bar is after the signal was not
    # tradable at the signal — plenty of later bars must not qualify it
    # (entry would silently shift weeks forward)
    _write(tmp_path, "SHFE.ag2412C8200",
           _bars_from(datetime(2024, 12, 11), n=40))     # lists AFTER SIG
    _write(tmp_path, "SHFE.ag2412C8300", _bars_from(LIVE))  # tradable at SIG
    store = OptionStore(tmp_path)
    got = _snap_to_listed(store, "ag", "ag2412c8200", 8200, 8050.0, SIG)
    assert got is not None
    assert got["contract_sym"] == "ag2412c8300"   # not the late-listed 8200


def test_nothing_covered_returns_none(tmp_path):
    _write(tmp_path, "SHFE.ag2408C8200", _bars_from(datetime(2024, 7, 1)))
    store = OptionStore(tmp_path)
    assert _snap_to_listed(store, "ag", "ag2603c8200", 8200, 8050.0,
                           date(2026, 1, 5)) is None
