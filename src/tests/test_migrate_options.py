"""Tests for migrate_options_to_parquet helpers."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Legacy quant_data tooling surface — not installed since the 2026-06-11
# WSL migration (data fetching moved to quant-cli). Skip until ported.
pytest.importorskip("quant_data")

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_parse_occ_symbol_call():
    from scripts.migrate_options_to_parquet import parse_occ_symbol
    result = parse_occ_symbol("SPY250516C00515000")
    assert result["portfolio"] == "SPY"
    assert result["expiry"] == datetime(2025, 5, 16)
    assert result["option_type"] == "call"
    assert result["strike"] == 515.0
    assert result["option_index"] == "C00515000"


def test_parse_occ_symbol_put():
    from scripts.migrate_options_to_parquet import parse_occ_symbol
    result = parse_occ_symbol("SPY250516P00490000")
    assert result["option_type"] == "put"
    assert result["strike"] == 490.0
    assert result["option_index"] == "P00490000"


def test_parse_occ_symbol_spxw():
    """SPXW has a longer root — portfolio extracted correctly."""
    from scripts.migrate_options_to_parquet import parse_occ_symbol
    result = parse_occ_symbol("SPXW250516C05200000")
    assert result["portfolio"] == "SPXW"
    assert result["expiry"] == datetime(2025, 5, 16)
    assert result["strike"] == 5200.0
    assert result["option_index"] == "C05200000"


def test_bar_dict_to_bar_data():
    from scripts.migrate_options_to_parquet import bar_dict_to_bar_data
    from quant_data.models import Exchange, Interval
    bar = {"time": 1745208000, "open": 20.24, "high": 22.0, "low": 14.59, "close": 16.83, "volume": 2778}
    result = bar_dict_to_bar_data(bar, "SPY250516C00515000", Exchange.NYSE, Interval.DAILY)
    assert result.symbol == "SPY250516C00515000"
    assert result.open_price == 20.24
    assert result.volume == 2778
    assert result.datetime == datetime(2025, 4, 21, 4, 0, 0)  # 1745208000 UTC


def test_migrate_file_creates_bars_and_contract(tmp_path):
    """migrate_json_file returns (ContractData, list[BarData]) from a minimal JSON."""
    from scripts.migrate_options_to_parquet import migrate_json_file
    from quant_data.models import Exchange, Interval, Product, OptionType

    payload = {
        "contract": "O:SPY250516C00515000",
        "underlying": "spy",
        "signal_date": "2025-04-21",
        "otm_rank": 2,
        "strike": 515.0,
        "liquidity": {"avg_daily_volume": 285.7, "liquidity_flag": "ok"},
        "bars": [
            {"time": 1745208000, "open": 20.24, "high": 22.0, "low": 14.59, "close": 16.83, "volume": 2778},
            {"time": 1745294400, "open": 19.5,  "high": 25.13, "low": 18.84, "close": 23.21, "volume": 948},
        ],
    }
    f = tmp_path / "o_spy250516c00515000_daily.json"
    f.write_text(json.dumps(payload))

    contract, bars = migrate_json_file(f, Exchange.NYSE, Interval.DAILY)

    assert contract.symbol == "SPY250516C00515000"
    assert contract.product == Product.OPTION
    assert contract.exchange == Exchange.NYSE
    assert contract.option_portfolio == "SPY"
    assert contract.option_type == OptionType.CALL
    assert contract.option_strike == 515.0
    assert contract.option_expiry == datetime(2025, 5, 16)
    assert len(bars) == 2
    assert bars[0].open_price == 20.24
