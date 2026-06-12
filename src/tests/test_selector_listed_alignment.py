"""Production selectors pick listed contracts (expiry rule + strikes).

select_otm_calls / select_otm_calls_au must:
  - choose the expiry month per the user-locked rule (>=14d to OPTION
    expiry -> nearest listed month, else next listed)
  - snap theoretical %OTM strikes to LISTED strikes of that chain
  - fall back to the old theoretical behaviour when no chain is synced
    (store empty for the product)
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from engine.options.cn_ag_selector import select_otm_calls
from engine.options.cn_au_selector import select_otm_calls_au
from engine.options.expiry_select import snap_strikes_to_listed


def _bar(dt: datetime, close: float = 100.0) -> dict:
    return {
        "datetime": dt, "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 10.0, "turnover": close, "open_interest": 1.0,
    }


def _write(root, name):
    d = root / "daily"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([_bar(datetime(2024, 10, 25))]).to_parquet(
        d / f"{name}.parquet", index=False)


# ---------------------------------------------------------------------------
# snap_strikes_to_listed
# ---------------------------------------------------------------------------

def test_snap_strikes_nearest_listed_above_spot():
    listed = [8000, 8100, 8300, 8600]
    got = snap_strikes_to_listed(listed, targets=[8190, 8290, 8390], spot=8050.0)
    assert got == [8100, 8300, 8600]   # nearest listed, deduped upward


def test_snap_strikes_runs_out_returns_fewer():
    got = snap_strikes_to_listed([8100], targets=[8190, 8290, 8390], spot=8050.0)
    assert got == [8100]


# ---------------------------------------------------------------------------
# ag selector end-to-end against a synthetic store
# ---------------------------------------------------------------------------

@pytest.fixture
def ag_store(tmp_path):
    for n in ("SHFE.ag2412C8100", "SHFE.ag2412C8300", "SHFE.ag2412C8500",
              "SHFE.ag2501C8200", "SHFE.ag2501C8400", "SHFE.ag2501C8600"):
        _write(tmp_path, n)
    return tmp_path


def test_ag_two_weeks_picks_nearest_listed_month(ag_store):
    # 2024-11-07: ag2412 option expiry ~2024-11-22 (>=14d) -> 2412 chain
    calls = select_otm_calls(8050.0, date(2024, 11, 7), quant_root=ag_store)
    assert calls and all(c["expiry_month"] == "2412" for c in calls)
    assert [c["strike"] for c in calls] == [8100, 8300, 8500]
    assert calls[0]["contract_sym"] == "ag2412c8100"


def test_ag_under_two_weeks_rolls_to_next_listed(ag_store):
    # 2024-11-15: <14d to the 2412 option expiry -> 2501 chain
    calls = select_otm_calls(8050.0, date(2024, 11, 15), quant_root=ag_store)
    assert calls and all(c["expiry_month"] == "2501" for c in calls)
    assert [c["strike"] for c in calls] == [8200, 8400, 8600]


def test_signal_before_chain_listing_falls_back_to_theoretical(tmp_path):
    # Historical replay: the chain in the store lists AFTER the signal —
    # the listed path must not engage (catalog is as-of-now, not as-of-
    # signal), preserving the old theoretical behaviour.
    for n in ("SHFE.ag2412C8100", "SHFE.ag2412C8300"):
        _write(tmp_path, n)   # first bar 2024-10-25
    calls = select_otm_calls(8050.0, date(2024, 6, 3), quant_root=tmp_path)
    assert len(calls) == 3
    assert all(c["strike"] % 100 == 0 for c in calls)   # theoretical strikes


def test_ag_empty_store_falls_back_to_theoretical(tmp_path):
    (tmp_path / "daily").mkdir()
    calls = select_otm_calls(8050.0, date(2024, 11, 7), quant_root=tmp_path)
    assert len(calls) == 3
    assert all(c["strike"] % 100 == 0 for c in calls)   # old rounding path


def test_listed_strikes_below_spot_fall_back_to_theoretical(tmp_path):
    # The synced chain is an ATM±N snapshot from an earlier price level;
    # after a rally every synced strike sits below spot. The real
    # exchange always lists higher strikes — keep the rule's month but
    # use theoretical strikes instead of returning nothing.
    for n in ("SHFE.ag2412C8100", "SHFE.ag2412C8300"):
        _write(tmp_path, n)
    calls = select_otm_calls(9000.0, date(2024, 11, 7), quant_root=tmp_path)
    assert len(calls) == 3
    assert all(c["expiry_month"] == "2412" for c in calls)
    assert all(c["strike"] > 9000 and c["strike"] % 100 == 0 for c in calls)


def test_au_rule_applies_with_bimonthly_chain(tmp_path):
    for n in ("SHFE.au2412C632", "SHFE.au2412C640",
              "SHFE.au2502C648", "SHFE.au2502C656"):
        _write(tmp_path, n)
    # <14d to the 2412 option expiry (~2024-11-22) -> bimonthly next = 2502
    calls = select_otm_calls_au(628.0, date(2024, 11, 15), quant_root=tmp_path)
    assert calls and all(c["expiry_month"] == "2502" for c in calls)
    assert [c["strike"] for c in calls][:2] == [648, 656]
