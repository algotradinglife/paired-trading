"""Tests for _refresh_us_options in refresh_daily."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import scripts.refresh_daily as rd


def test_refresh_us_options_calls_update_all_for_each_symbol(tmp_path):
    """_refresh_us_options calls manager.update_all once per US underlying."""
    mock_manager = MagicMock()
    mock_manager.update_all.return_value = {"SPY250620C00550000": 5}

    with (
        patch("scripts.refresh_daily.PolygonOptionsDatafeed"),
        patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager),
        patch("scripts.refresh_daily._DATA_ROOT", tmp_path),
    ):
        result = rd._refresh_us_options(lookback_days=7, expiry_window_days=30)

    assert mock_manager.update_all.call_count == len(rd._US_SYMBOLS)
    assert isinstance(result, dict)


def test_refresh_us_options_returns_totals(tmp_path):
    """_refresh_us_options aggregates bar counts from update_all."""
    mock_manager = MagicMock()
    mock_manager.update_all.return_value = {"SPY250620C00550000": 10, "SPY250620P00530000": 8}

    with (
        patch("scripts.refresh_daily.PolygonOptionsDatafeed"),
        patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager),
        patch("scripts.refresh_daily._DATA_ROOT", tmp_path),
    ):
        result = rd._refresh_us_options()

    # Every symbol gets called; each returns 18 bars
    first_sym = rd._US_SYMBOLS[0][0]
    assert result[first_sym] == 18


def test_refresh_us_options_errors_dont_abort(tmp_path):
    """An exception on one symbol is caught and the rest continue."""
    mock_manager = MagicMock()
    call_count = 0

    def update_all_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")
        return {"SYM250620C00100000": 3}

    mock_manager.update_all.side_effect = update_all_side_effect

    with (
        patch("scripts.refresh_daily.PolygonOptionsDatafeed"),
        patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager),
        patch("scripts.refresh_daily._DATA_ROOT", tmp_path),
    ):
        result = rd._refresh_us_options()

    assert mock_manager.update_all.call_count == len(rd._US_SYMBOLS)
    # First symbol errored, others succeeded
    assert len(result) == len(rd._US_SYMBOLS) - 1
