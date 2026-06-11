"""Tests for Parquet-backed option loading in analyze_options_payoff."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Legacy quant_data tooling surface — not installed since the 2026-06-11
# WSL migration (data fetching moved to quant-cli). Skip until ported.
pytest.importorskip("quant_data")

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.models import ContractData, Exchange, Interval, OptionType, Product


def _make_contract(symbol: str, portfolio: str, expiry: datetime,
                   strike: float, ct: OptionType) -> ContractData:
    return ContractData(
        symbol=symbol,
        exchange=Exchange.NYSE,
        product=Product.OPTION,
        option_portfolio=portfolio,
        option_strike=strike,
        option_type=ct,
        option_expiry=expiry,
        option_underlying=f"{portfolio}.NYSE",
        option_index=symbol[-9:],
    )


def _make_bars_df(dts_and_closes: list[tuple[datetime, float, float]]) -> pd.DataFrame:
    """Build a DataFrame matching ParquetStorage.load_bar_data output.

    Each tuple: (datetime_utc_naive, open_price, close_price).
    """
    rows = []
    for dt, open_, close in dts_and_closes:
        rows.append({
            "datetime":    pd.Timestamp(dt, tz="UTC"),
            "open_price":  open_,
            "high_price":  close * 1.1,
            "low_price":   close * 0.9,
            "close_price": close,
            "volume":      1000.0,
        })
    return pd.DataFrame(rows)


def test_load_option_rows_parquet_returns_dataframe(tmp_path):
    """_load_option_rows_parquet returns a DataFrame with expected columns."""
    from scripts.analyze_options_payoff import _load_option_rows_parquet

    contract = _make_contract(
        "SPY250620C00550000", "SPY",
        datetime(2025, 6, 20), 550.0, OptionType.CALL,
    )
    bars_df = _make_bars_df([
        (datetime(2025, 5, 1), 4.5, 5.0),
        (datetime(2025, 5, 2), 5.0, 5.5),
        (datetime(2025, 5, 5), 5.5, 6.0),
        (datetime(2025, 5, 6), 6.0, 6.5),
        (datetime(2025, 5, 7), 6.5, 7.0),
        (datetime(2025, 5, 8), 7.0, 7.5),
    ])

    signals = pd.DataFrame([{
        "date": "2025-04-30",
        "symbol": "SPY",
        "direction": "bottom",
        "higher_relation": "opposing",
        "entry": 545.0,
        "confidence": 0.8,
    }])

    from quant_data.storage import ParquetStorage
    with patch.object(ParquetStorage, "load_contract_data", return_value=[contract]), \
         patch.object(ParquetStorage, "load_bar_data", return_value=bars_df):
        storage = ParquetStorage(tmp_path)
        df = _load_option_rows_parquet(
            storage=storage,
            portfolios=["SPY"],
            exchange=Exchange.NYSE,
            interval=Interval.DAILY,
            signals=signals,
        )

    assert not df.empty
    assert "contract" in df.columns
    assert "strike" in df.columns
    assert "contract_type" in df.columns
    assert "h5_ret" in df.columns
    assert df.iloc[0]["contract"] == "SPY250620C00550000"
    assert df.iloc[0]["contract_type"] == "call"
    assert df.iloc[0]["entry_premium"] == 4.5  # first bar after signal = bars[0].open_price


def test_load_option_rows_parquet_skips_expired(tmp_path):
    """Contracts expired before signal date are skipped."""
    from scripts.analyze_options_payoff import _load_option_rows_parquet

    contract = _make_contract(
        "SPY250101C00550000", "SPY",
        datetime(2025, 1, 1), 550.0, OptionType.CALL,  # expired before signal
    )
    bars_df = _make_bars_df([
        (datetime(2024, 12, 31), 5.0, 5.0),
    ])

    signals = pd.DataFrame([{
        "date": "2025-04-30",
        "symbol": "SPY",
        "direction": "bottom",
        "higher_relation": "opposing",
        "entry": 545.0,
        "confidence": 0.8,
    }])

    from quant_data.storage import ParquetStorage
    with patch.object(ParquetStorage, "load_contract_data", return_value=[contract]), \
         patch.object(ParquetStorage, "load_bar_data", return_value=bars_df):
        storage = ParquetStorage(tmp_path)
        df = _load_option_rows_parquet(
            storage=storage,
            portfolios=["SPY"],
            exchange=Exchange.NYSE,
            interval=Interval.DAILY,
            signals=signals,
        )

    assert df.empty
