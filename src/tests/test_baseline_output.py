import pandas as pd
from scripts._baseline_output import compute_data_hash


def _df(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=len(closes), tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1] * len(closes),
    })


def test_data_hash_is_deterministic():
    bars = [("cu", _df([1.0, 2.0, 3.0])), ("ag", _df([4.0, 5.0]))]
    assert compute_data_hash(bars) == compute_data_hash(list(reversed(bars)))


def test_data_hash_changes_on_any_row_edit():
    h0 = compute_data_hash([("cu", _df([1.0, 2.0, 3.0]))])
    h1 = compute_data_hash([("cu", _df([1.0, 9.0, 3.0]))])
    assert h0 != h1


def test_data_hash_changes_on_truncation():
    h0 = compute_data_hash([("cu", _df([1.0, 2.0, 3.0]))])
    h1 = compute_data_hash([("cu", _df([1.0, 2.0]))])
    assert h0 != h1
