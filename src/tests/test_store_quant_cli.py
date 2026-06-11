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
    # 22:00 Beijing == 14:00 UTC window START (polygon) -> period_end 15:00 UTC
    _write(tmp_path, "hour", "SPY.AMEX", [_bar(datetime(2025, 3, 3, 22, 0))])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 15:00", tz="UTC")]


def test_us_5min_start_stamp_shifted_to_period_end(tmp_path):
    _write(tmp_path, "min5", "SPY.AMEX", [_bar(datetime(2025, 3, 3, 22, 0))])
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "5min", as_of=AS_OF)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 14:05", tz="UTC")]


def test_us_hourly_as_of_guard_excludes_in_flight_bar(tmp_path):
    # Bar covering 14:00-15:00 UTC must NOT be visible at as_of 14:30
    _write(tmp_path, "hour", "SPY.AMEX", [
        _bar(datetime(2025, 3, 3, 21, 0)),   # 13:00-14:00 UTC -> end 14:00
        _bar(datetime(2025, 3, 3, 22, 0)),   # 14:00-15:00 UTC -> end 15:00
    ])
    as_of = datetime(2025, 3, 3, 14, 30, tzinfo=timezone.utc)
    bf = BarStore(tmp_path).load_barframe("SPY", "XNYS", "60min", as_of=as_of)
    assert list(bf.df["timestamp"]) == [pd.Timestamp("2025-03-03 14:00", tz="UTC")]


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
    with pytest.raises(ValueError, match="SHFE.cu0"):
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
