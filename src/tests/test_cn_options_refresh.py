"""Tests for _refresh_cn_options in refresh_daily.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Legacy quant_data tooling surface — not installed since the 2026-06-11
# WSL migration (data fetching moved to quant-cli). Skip until ported.
pytest.importorskip("quant_data")

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_refresh_cn_options_calls_update_all_for_each_portfolio():
    """_refresh_cn_options calls OptionsManager.update_all for each supported portfolio."""
    from scripts.refresh_daily import _refresh_cn_options

    mock_manager = MagicMock()
    mock_manager.update_all.return_value = {"AU2506C380": 5}

    with patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager), \
         patch("scripts.refresh_daily.AkshareOptionsDatafeed"), \
         patch("scripts.refresh_daily.ParquetStorage"):
        results = _refresh_cn_options(lookback_days=30, expiry_window_days=90)

    # Should be called once per portfolio (at least 4: au, ag, cu, rb)
    assert mock_manager.update_all.call_count >= 4


def test_refresh_cn_options_returns_totals():
    from scripts.refresh_daily import _refresh_cn_options

    mock_manager = MagicMock()
    mock_manager.update_all.return_value = {"AU2506C380": 3, "AU2506C382": 7}

    with patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager), \
         patch("scripts.refresh_daily.AkshareOptionsDatafeed"), \
         patch("scripts.refresh_daily.ParquetStorage"):
        results = _refresh_cn_options()

    assert isinstance(results, dict)
    assert all(isinstance(v, int) for v in results.values())


def test_refresh_cn_options_errors_dont_abort():
    """An error on one portfolio doesn't abort the others."""
    from scripts.refresh_daily import _refresh_cn_options

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")
        return {"SYM": 1}

    mock_manager = MagicMock()
    mock_manager.update_all.side_effect = side_effect

    with patch("scripts.refresh_daily.OptionsManager", return_value=mock_manager), \
         patch("scripts.refresh_daily.AkshareOptionsDatafeed"), \
         patch("scripts.refresh_daily.ParquetStorage"):
        results = _refresh_cn_options()

    # Should have continued past the first error
    assert mock_manager.update_all.call_count > 1
