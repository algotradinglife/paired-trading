"""Regression: backtest_full_stack emits a real data_hash (not None).

Until this wiring, full_stack wrote data_hash=None, so the validator's
data-vs-code drift attribution (validate_baselines.py --full) was inert.
_data_hash_for_bars hashes every bar series that fed the replay (daily +
60min per symbol) so a data refresh is distinguishable from a code change.
"""
import pandas as pd

from scripts.backtest_full_stack import _data_hash_for_bars


def _df(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=len(closes), tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1] * len(closes),
    })


def test_empty_bars_map_yields_none():
    # No bars loaded -> None, so the validator tells "data outage" from "data X".
    assert _data_hash_for_bars({}) is None


def test_non_empty_yields_sha256_hash():
    h = _data_hash_for_bars({"cu@D": _df([1.0, 2.0, 3.0])})
    assert isinstance(h, str) and h.startswith("sha256:")


def test_deterministic_regardless_of_insertion_order():
    a = _data_hash_for_bars({"cu@D": _df([1.0, 2.0]), "ag@D": _df([3.0, 4.0])})
    b = _data_hash_for_bars({"ag@D": _df([3.0, 4.0]), "cu@D": _df([1.0, 2.0])})
    assert a == b


def test_daily_and_60min_keyed_distinctly_both_contribute():
    # Same symbol's daily and 60min must not collide on one key; a change to
    # only the 60min series must move the hash.
    base = {"cu@D": _df([1.0, 2.0, 3.0]), "cu@60min": _df([1.0, 2.0, 3.0])}
    changed = {"cu@D": _df([1.0, 2.0, 3.0]), "cu@60min": _df([1.0, 9.0, 3.0])}
    assert _data_hash_for_bars(base) != _data_hash_for_bars(changed)
