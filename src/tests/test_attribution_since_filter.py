"""--since market-era sub-window for the attribution harness.

The option store's history starts 2024-07; full-window runs are
structurally MODEL_DOMINATED (2021-2023 trades have no market data).
--since restricts emissions to the market-covered era so the verdict
can be market-backed; --is-cutoff-year re-splits IS/OOS inside it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scripts.backtest_options_attribution import _filter_emissions, fold_of


@dataclass
class _E:
    sig_date: date


def test_filter_emissions_keeps_on_or_after_since():
    ems = [_E(date(2023, 5, 1)), _E(date(2024, 7, 1)), _E(date(2025, 1, 2))]
    out = _filter_emissions(ems, date(2024, 7, 1))
    assert [e.sig_date for e in out] == [date(2024, 7, 1), date(2025, 1, 2)]


def test_filter_emissions_none_passthrough():
    ems = [_E(date(2023, 5, 1))]
    assert _filter_emissions(ems, None) is ems


def test_fold_of_respects_cutoff_override():
    import scripts.backtest_options_attribution as m
    old = m.IS_CUTOFF_YEAR
    try:
        m.IS_CUTOFF_YEAR = 2024
        assert fold_of(2024) == "is"
        assert fold_of(2025) == "oos"
    finally:
        m.IS_CUTOFF_YEAR = old
