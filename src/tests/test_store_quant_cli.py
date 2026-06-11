"""BarStore against the quant-cli flat Parquet layout.

Contract under test (faithful to the legacy quant-data pipeline so that
detector calibration carries over):

  - layout: {root}/{daily,hour,min15,min5,weekly}/{FILENAME}.parquet
  - schema: datetime (naive), open/high/low/close/volume/turnover/open_interest
  - CN intraday stamps are naive Beijing period-END  -> Asia/Shanghai -> UTC
  - CN daily/weekly stamps are naive midnight        -> labeled UTC midnight as-is
    (legacy store localized the date marker to UTC; converting via Shanghai
    would shift the date)
  - US intraday stamps are naive Beijing (fetch-host tz) period-START
                                                     -> Asia/Shanghai -> UTC
  - US daily stamps are naive midnight of the ET trade date
                                                     -> exchange session close UTC
  - filenames: CN futures "EXCH.sym" (SHFE.cu0 / CZCE.MA0), US "SYM.AMEX"
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from data.store import BarStore


def _bar(dt: datetime, px: float = 100.0, vol: float = 10.0) -> dict:
    return {
        "datetime": dt,
        "open": px,
        "high": px + 1.0,
        "low": px - 1.0,
        "close": px + 0.5,
        "volume": vol,
        "turnover": px * vol,
        "open_interest": 5.0,
    }


def _write(root: Path, folder: str, name: str, bars: list[dict]) -> None:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(d / f"{name}.parquet", index=False)


AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Timestamp semantics
# ---------------------------------------------------------------------------

def test_cn_hourly_localizes_beijing_to_utc(tmp_path):
    _write(tmp_path, "hour", "SHFE.cu0", [
        _bar(datetime(2025, 3, 3, 10, 0)),
        _bar(datetime(2025, 3, 3, 11, 15)),
    ])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "60min", as_of=AS_OF)
    got = list(bf.df["timestamp"])
    assert got == [
        pd.Timestamp("2025-03-03 02:00", tz="UTC"),
        pd.Timestamp("2025-03-03 03:15", tz="UTC"),
    ]


def test_cn_daily_midnight_kept_as_utc_midnight(tmp_path):
    _write(tmp_path, "daily", "SHFE.cu0", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "D", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 00:00", tz="UTC")]


def test_cn_weekly_reads_weekly_folder_midnight_utc(tmp_path):
    _write(tmp_path, "weekly", "SHFE.cu0", [_bar(datetime(2025, 2, 28))])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "W", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-02-28 00:00", tz="UTC")]


def test_us_hourly_start_stamp_shifted_to_period_end(tmp_path):
    # 23:00 Beijing == 15:00 UTC window START (polygon, 10:00 ET)
    # -> period_end 16:00 UTC (11:00 ET)
    _write(tmp_path, "hour", "SPY.AMEX", [_bar(datetime(2025, 3, 3, 23, 0))])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 16:00", tz="UTC")]


def test_us_5min_start_stamp_shifted_to_period_end(tmp_path):
    # 22:30 Beijing == 09:30 ET start -> period_end 09:35 ET == 14:35 UTC
    _write(tmp_path, "min5", "SPY.AMEX", [_bar(datetime(2025, 3, 3, 22, 30))])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "5min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 14:35", tz="UTC")]


def test_us_intraday_keeps_only_legacy_session_bars(tmp_path):
    # Legacy-feed contract (verified vs pa_us_60min baseline cells
    # 2026-06-11): keep period_end in (10:00, 16:00] ET. The 09:00-10:00
    # ET bar is dropped too — its OHLC mixes 09:00-09:30 premarket trades
    # and the bar did not exist in the legacy feed.
    # 2025-03-03 is EST (UTC-5); Beijing naive start-stamps:
    _write(tmp_path, "hour", "SPY.AMEX", [
        _bar(datetime(2025, 3, 3, 21, 0)),   # 08:00-09:00 ET premarket  -> drop
        _bar(datetime(2025, 3, 3, 22, 0)),   # 09:00-10:00 ET first bar  -> drop
        _bar(datetime(2025, 3, 3, 23, 0)),   # 10:00-11:00 ET            -> keep
        _bar(datetime(2025, 3, 4, 4, 0)),    # 15:00-16:00 ET            -> keep
        _bar(datetime(2025, 3, 4, 5, 0)),    # 16:00-17:00 ET post       -> drop
    ])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [
        pd.Timestamp("2025-03-03 16:00", tz="UTC"),  # end 11:00 ET
        pd.Timestamp("2025-03-03 21:00", tz="UTC"),  # end 16:00 ET
    ]


def test_us_intraday_respects_early_close_sessions(tmp_path):
    # 2024-11-29 (Black Friday) closes 13:00 ET. Bars after the early
    # close are post-market and must be dropped despite ending <= 16:00.
    # EST: 23:00 Beijing 11-28 == 10:00 ET start (end 11:00, keep);
    #      2:00 Beijing 11-30 == 13:00 ET start (end 14:00, post -> drop)
    _write(tmp_path, "hour", "SPY.AMEX", [
        _bar(datetime(2024, 11, 29, 23, 0)),  # 10:00-11:00 ET -> keep
        _bar(datetime(2024, 11, 30, 2, 0)),   # 13:00-14:00 ET post-close -> drop
    ])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [
        pd.Timestamp("2024-11-29 16:00", tz="UTC"),  # end 11:00 ET
    ]


def test_cn_intraday_not_session_filtered(tmp_path):
    # CN night-session bars must survive (the US regular-session rule
    # must not leak into CN handling)
    _write(tmp_path, "hour", "SHFE.cu0", [
        _bar(datetime(2025, 3, 3, 22, 0)),   # night session 21:00-22:00
        _bar(datetime(2025, 3, 4, 1, 0)),    # night session 00:00-01:00
    ])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "60min", as_of=AS_OF)
    assert len(bf.df) == 2


def test_us_hourly_as_of_guard_excludes_in_flight_bar(tmp_path):
    # Bar covering 16:00-17:00 UTC must NOT be visible at as_of 16:30
    _write(tmp_path, "hour", "SPY.AMEX", [
        _bar(datetime(2025, 3, 3, 23, 0)),   # 15:00-16:00 UTC -> end 16:00
        _bar(datetime(2025, 3, 4, 0, 0)),    # 16:00-17:00 UTC -> end 17:00
    ])
    as_of = datetime(2025, 3, 3, 16, 30, tzinfo=timezone.utc)
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=as_of)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 16:00", tz="UTC")]


def test_us_daily_maps_to_session_close(tmp_path):
    _write(tmp_path, "daily", "SPY.AMEX", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "D", as_of=AS_OF)
    # 2025-03-03 is an EST session; NYSE closes 16:00 ET == 21:00 UTC
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 21:00", tz="UTC")]


def test_us_daily_drops_non_session_dates(tmp_path):
    _write(tmp_path, "daily", "SPY.AMEX", [
        _bar(datetime(2025, 3, 1)),   # Saturday
        _bar(datetime(2025, 3, 3)),
    ])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "D", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 21:00", tz="UTC")]


# ---------------------------------------------------------------------------
# Symbol / filename mapping
# ---------------------------------------------------------------------------

def test_czce_symbol_maps_to_exchange_prefixed_file(tmp_path):
    _write(tmp_path, "daily", "CZCE.MA0", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("MA0", "XZCE", "D", as_of=AS_OF)
    assert len(bf.df) == 1


def test_ine_symbol_maps_to_exchange_prefixed_file(tmp_path):
    _write(tmp_path, "daily", "INE.sc0", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("sc0", "XINE", "D", as_of=AS_OF)
    assert len(bf.df) == 1


def test_missing_file_raises_value_error_with_path(tmp_path):
    (tmp_path / "daily").mkdir()
    with pytest.raises(ValueError, match="SHFE.cu2509"):
        BarStore(tmp_path).load_barframe("cu2509", "XSHF", "D", as_of=AS_OF)


def test_continuous_symbol_without_contracts_raises(tmp_path):
    (tmp_path / "daily").mkdir()
    with pytest.raises(ValueError, match="No contract files"):
        BarStore(tmp_path).load_barframe("cu0", "XSHF", "D", as_of=AS_OF)


def test_unsupported_level_raises_key_error(tmp_path):
    with pytest.raises(KeyError, match="4h"):
        BarStore(tmp_path).load_barframe("cu0", "XSHF", "4h", as_of=AS_OF)


def test_unsupported_exchange_raises_key_error(tmp_path):
    with pytest.raises(KeyError, match="XXXX"):
        BarStore(tmp_path).load_barframe("cu0", "XXXX", "D", as_of=AS_OF)


# ---------------------------------------------------------------------------
# Frame contract
# ---------------------------------------------------------------------------

def test_columns_keep_oi_drop_turnover(tmp_path):
    _write(tmp_path, "daily", "SHFE.cu0", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "D", as_of=AS_OF)
    assert list(bf.df.columns) == [
        "timestamp", "open", "high", "low", "close", "volume", "open_interest",
    ]


def test_as_of_leak_guard_drops_future_bars(tmp_path):
    _write(tmp_path, "hour", "SHFE.cu0", [
        _bar(datetime(2025, 3, 3, 10, 0)),
        _bar(datetime(2025, 3, 3, 11, 15)),
    ])
    as_of = datetime(2025, 3, 3, 2, 30, tzinfo=timezone.utc)  # between the two
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "60min", as_of=as_of)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 02:00", tz="UTC")]


def test_start_end_window_filters_bars(tmp_path):
    _write(tmp_path, "daily", "SHFE.cu0", [
        _bar(datetime(2025, 3, 3)),
        _bar(datetime(2025, 3, 4)),
        _bar(datetime(2025, 3, 5)),
    ])
    bf = BarStore(tmp_path).load_barframe(
        "cu0", "XSHF", "D",
        start=datetime(2025, 3, 4, tzinfo=timezone.utc),
        end=datetime(2025, 3, 4, tzinfo=timezone.utc),
        as_of=AS_OF,
    )
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-04 00:00", tz="UTC")]


def test_barframe_metadata(tmp_path):
    _write(tmp_path, "daily", "SHFE.cu0", [_bar(datetime(2025, 3, 3))])
    bf = BarStore(tmp_path).load_barframe("cu0", "XSHF", "D", as_of=AS_OF)
    assert bf.provider == "quant_data"
    assert bf.symbol == "CU0"
    assert bf.level == "D"
    assert bf.exchange == "XSHF"
    assert bf.last_completed_ts == datetime(2025, 3, 3, tzinfo=timezone.utc)
    assert bf.payload_hash
