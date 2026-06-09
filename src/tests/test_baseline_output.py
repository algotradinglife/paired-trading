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


# Task 2 -----------------------------------------------------------------------
from scripts._baseline_output import fold_samples_from_period_df


def test_fold_samples_maps_periods_and_computes():
    df = pd.DataFrame({
        "period": ["IS", "IS", "OOS1", "OOS2", "OOS2"],
        "r": [1.0, -1.0, 0.5, 2.0, -1.0],
    })
    out = fold_samples_from_period_df(df)
    assert out["is"] == {"n": 2, "ev_r": 0.0, "win_pct": 50.0}
    assert out["f1"] == {"n": 1, "ev_r": 0.5, "win_pct": 100.0}
    assert out["f2"] == {"n": 2, "ev_r": 0.5, "win_pct": 50.0}
    assert out["f3"] == {"n": None, "ev_r": None, "win_pct": None}


# Task 3 -----------------------------------------------------------------------
import json
from scripts._baseline_output import write_baseline_output, SCHEMA


def test_write_folds_output(tmp_path):
    p = tmp_path / "out.json"
    write_baseline_output(p, kind="folds", lane="bpull", pool="cn_metal_futures",
                          samples={"is": {"n": 1, "ev_r": 0.1, "win_pct": 100.0}},
                          data_hash="sha256:abc", params_echo={"stop_mult": 1.5})
    doc = json.loads(p.read_text())
    assert doc["schema"] == SCHEMA and doc["kind"] == "folds"
    assert doc["lane"] == "bpull" and doc["samples"]["is"]["n"] == 1


def test_write_full_stack_output(tmp_path):
    p = tmp_path / "fs.json"
    lanes = {"bpull": {"kq_m_shfe_cu": {"n": 17, "ev_r": 0.13, "win_pct": 64.0}}}
    write_baseline_output(p, kind="full_stack", lanes=lanes, data_hash="sha256:def")
    doc = json.loads(p.read_text())
    assert doc["kind"] == "full_stack" and doc["lanes"]["bpull"]["kq_m_shfe_cu"]["n"] == 17


def test_write_rejects_unknown_kind(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_baseline_output(tmp_path / "x.json", kind="bogus")
