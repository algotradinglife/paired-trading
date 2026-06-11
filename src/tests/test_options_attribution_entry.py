"""Entry construction for the options attribution harness (codex P2 x2).

- the simulation runs in GROSS price space: the entry handed to
  simulate_entry must be the raw offset-bar close, NOT cost-adjusted —
  costs are applied once, analytically, in _net_mult
- paths shorter than ENTRY_OFFSET+1 bars are skipped entirely; falling
  back to row 0 would reintroduce the signal-day-close look-ahead the
  offset exists to avoid
"""
from __future__ import annotations

import pandas as pd

from scripts.backtest_options_attribution import ENTRY_OFFSET, _entry_for_path


def _path(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "open": closes, "high": [c + 2 for c in closes],
        "low": [max(c - 2, 0.1) for c in closes], "close": closes,
    })


def test_short_path_is_skipped_not_row0():
    opt = _path([100.0])  # only the signal-day bar
    assert _entry_for_path(opt, tick=1.0, stop_ticks=5) is None


def test_entry_is_raw_offset_close_without_cost():
    opt = _path([100.0, 110.0, 120.0])
    entry = _entry_for_path(opt, tick=1.0, stop_ticks=5)
    assert entry is not None
    assert entry["entry_idx"] == ENTRY_OFFSET
    assert entry["entry_price"] == 110.0          # raw close, no cost markup
    assert entry["stop_price"] == 110.0 - 5 * 1.0


def test_nonpositive_offset_close_is_skipped():
    opt = _path([100.0, 0.0, 120.0])
    assert _entry_for_path(opt, tick=1.0, stop_ticks=5) is None
