from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.continuous_source_audit import (
    aggregate_strict_asof,
    build_continuous_source_audit,
)
from engine.pa_feitian.historical_asof import load_asof_protocol
from engine.pa_feitian.manifest import sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = REPO_ROOT / "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json"


def _five_min(extreme_future: bool = False) -> pd.DataFrame:
    timestamps = list(pd.date_range("2026-06-01 21:05", "2026-06-01 23:55", freq="5min"))
    timestamps += list(pd.date_range("2026-06-02 00:00", "2026-06-02 02:30", freq="5min"))
    timestamps += list(pd.date_range("2026-06-02 09:05", "2026-06-02 10:15", freq="5min"))
    timestamps += list(pd.date_range("2026-06-02 10:35", "2026-06-02 11:30", freq="5min"))
    timestamps += list(pd.date_range("2026-06-02 13:35", "2026-06-02 15:00", freq="5min"))
    if extreme_future:
        timestamps += list(pd.date_range("2026-06-03 09:05", "2026-06-03 09:15", freq="5min"))
    count = len(timestamps)
    values = [float(index + 1) for index in range(count)]
    frame = pd.DataFrame(
        {
            "datetime": timestamps,
            "open": values,
            "high": [value + 1 for value in values],
            "low": [value - 1 for value in values],
            "close": [value + 0.5 for value in values],
            "volume": 1.0,
            "turnover": 1.0,
            "open_interest": 1.0,
            "main_month": "202606",
            "is_roll": False,
        }
    )
    if extreme_future:
        frame.loc[frame["datetime"].dt.date > datetime(2026, 6, 2).date(), "close"] = 1e9
    return frame


def test_aggregation_filters_future_before_calendar_and_resample() -> None:
    cutoff = datetime(2026, 6, 2, 7, tzinfo=UTC)
    base = aggregate_strict_asof(
        _five_min(), decision_ts_utc=cutoff, lookback_calendar_days=120
    )
    tainted = aggregate_strict_asof(
        _five_min(extreme_future=True),
        decision_ts_utc=cutoff,
        lookback_calendar_days=120,
    )
    for level in ("D", "W", "60min", "15min"):
        pd.testing.assert_frame_equal(base[level], tainted[level])
        assert not base[level].empty
        assert base[level]["timestamp"].max() <= pd.Timestamp(cutoff)


def _write_candidate_fixture(root: Path, protocol: dict) -> None:
    root.mkdir(parents=True)
    daily = pd.DataFrame(
        {
            "date": [datetime(2026, 6, 2).date()],
            "main_month": ["2606"],
            "F": [100.0],
            "atm_iv": [0.2],
            "iv_25dc": [0.21],
            "iv_25dp": [0.19],
            "rr_25d": [0.02],
            "n_call": [2],
            "n_put": [2],
        }
    )
    regime = pd.DataFrame(
        {
            "date": [datetime(2026, 6, 2).date()],
            "close": [100.0],
            "iv_rank": [0.5],
            "atr_pct": [0.01],
            "rvol20": [0.1],
            "ema20_slope": [0.0],
            "adx14": [20.0],
            "vol_chg": [0.0],
            "oi_chg": [0.0],
            "regime": ["range"],
        }
    )
    for candidate in protocol["candidate_sources"]:
        path = root / candidate["filename"]
        if candidate["kind"] == "underlying_5min":
            frame = _five_min()
            # Directly detectable calendar-midnight annotation problem.
            midnight = frame.index[frame["datetime"] == pd.Timestamp("2026-06-02 00:00")][0]
            frame.loc[midnight:, "main_month"] = "202608"
            frame.loc[midnight, "is_roll"] = True
        elif candidate["kind"] == "option_ivskew":
            frame = daily
        else:
            frame = regime
        frame.to_parquet(path, index=False)
        candidate["sha256"] = sha256_file(path)


def _fixture_protocol(root: Path) -> dict:
    protocol = copy.deepcopy(load_asof_protocol(PROTOCOL))
    protocol["universe"] = [
        member for member in protocol["universe"] if member["id"] == "shfe_ag_continuous"
    ]
    protocol["decisions"] = [
        {
            "id": "fixture_decision",
            "decision_ts_utc": "2026-06-02T07:00:00Z",
            "universe_id": "shfe_ag_continuous",
        }
    ]
    _write_candidate_fixture(root, protocol)
    return protocol


def test_audit_reads_only_exact_sources_and_quarantines_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "continuous"
    protocol = _fixture_protocol(root)

    def reject_glob(*_args, **_kwargs):
        raise AssertionError("continuous source audit must not discover files")

    monkeypatch.setattr(Path, "glob", reject_glob)
    artifact, audit = build_continuous_source_audit(
        protocol=protocol,
        protocol_path=PROTOCOL,
        continuous_root=root,
        generated_at_utc=datetime(2026, 7, 11, 16, tzinfo=UTC),
        source_commit="test",
    )
    assert len(audit["source_audit"]) == 6
    assert all(
        source["candidate_status"] == "data_present_but_unverified"
        for source in audit["source_audit"]
    )
    five_min = [source for source in audit["source_audit"] if source["kind"] == "underlying_5min"]
    assert all(source["quality_and_roll"]["midnight_roll_annotations"] == 1 for source in five_min)
    assert artifact["candidate_data_eligible_for_score_today"] is False
    assert all(
        row["strict_asof_passed"] and row["status"] == "data_present_but_unverified"
        for row in audit["aggregation_audit"]
    )


def test_audit_rejects_source_identity_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "continuous"
    protocol = _fixture_protocol(root)
    protocol["candidate_sources"][0]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        build_continuous_source_audit(
            protocol=protocol,
            protocol_path=PROTOCOL,
            continuous_root=root,
            generated_at_utc=datetime(2026, 7, 11, 16, tzinfo=UTC),
            source_commit="test",
        )
