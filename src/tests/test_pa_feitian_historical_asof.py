from __future__ import annotations

import ast
import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.historical_asof import (
    build_historical_asof_artifacts,
    load_asof_protocol,
    verify_historical_asof_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = REPO_ROOT / "docs/research/pa-feitian-m6-historical-asof-protocol-v1.json"


def _small_protocol() -> dict:
    protocol = load_asof_protocol(PROTOCOL)
    protocol["universe"] = [
        member for member in protocol["universe"] if member["id"] == "shfe_ag_continuous"
    ]
    protocol["decisions"] = [
        {
            "id": "bounded_test_decision",
            "decision_ts_utc": "2026-06-02T00:00:00Z",
            "universe_id": "shfe_ag_continuous",
        }
    ]
    protocol["levels"] = ["D"]
    protocol["minimum_rows"] = {"D": 2}
    return protocol


def _write_daily(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03"]),
            "open": [1.0, 2.0, 999.0],
            "high": [2.0, 3.0, 1000.0],
            "low": [0.5, 1.5, 998.0],
            "close": [1.5, 2.5, 999.5],
            "volume": [10.0, 20.0, 999.0],
            "open_interest": [5.0, 6.0, 999.0],
        }
    ).to_parquet(path, index=False)


def test_builder_truncates_every_series_and_never_scans_or_reselects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "quant"
    _write_daily(root / "daily" / "SHFE.ag0.parquet")
    # A tempting option file must not be discovered or selected.
    _write_daily(root / "daily" / "SHFE.ag2608C18800.parquet")

    def reject_glob(*_args, **_kwargs):
        raise AssertionError("bounded as-of lane must not scan the store")

    monkeypatch.setattr(Path, "glob", reject_glob)
    artifact, audit = build_historical_asof_artifacts(
        protocol=_small_protocol(),
        protocol_path=PROTOCOL,
        quant_data_root=root,
        generated_at_utc=datetime(2026, 7, 11, 14, tzinfo=UTC),
        source_commit="test",
    )

    series = artifact["snapshots"][0]["series"][0]
    assert [row["timestamp"] for row in series["bars"]] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert all(row["close"] != 999.5 for row in series["bars"])
    assert artifact["guardrails"]["raw_store_scan"] is False
    assert artifact["guardrails"]["contract_selection"] == "none"
    assert artifact["guardrails"]["contract_reselection"] is False
    assert audit["funnel"] == {
        "requested_series": 1,
        "supported_series": 1,
        "data_blocked_series": 0,
    }


def test_builder_code_has_no_implicit_today_or_now_call() -> None:
    paths = [
        REPO_ROOT / "src/engine/pa_feitian/historical_asof.py",
        REPO_ROOT / "src/scripts/build_pa_feitian_historical_asof.py",
    ]
    calls: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"today", "now", "utcnow"}:
                    calls.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert calls == []


def test_verifier_rejects_injected_future_bar(tmp_path: Path) -> None:
    root = tmp_path / "quant"
    _write_daily(root / "daily" / "SHFE.ag0.parquet")
    artifact, _ = build_historical_asof_artifacts(
        protocol=_small_protocol(),
        protocol_path=PROTOCOL,
        quant_data_root=root,
        generated_at_utc=datetime(2026, 7, 11, 14, tzinfo=UTC),
        source_commit="test",
    )
    corrupted = copy.deepcopy(artifact)
    corrupted["snapshots"][0]["series"][0]["bars"].append(
        {"timestamp": "2026-06-03T00:00:00Z", "close": 999.5}
    )
    with pytest.raises(ValueError, match="future bar"):
        verify_historical_asof_artifact(corrupted)


def test_protocol_rejects_raw_store_scan(tmp_path: Path) -> None:
    payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    payload["source_policy"]["allow_raw_store_scan"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="allow_raw_store_scan"):
        load_asof_protocol(path)


def test_empty_explicit_store_is_classified_not_imputed(tmp_path: Path) -> None:
    artifact, audit = build_historical_asof_artifacts(
        protocol=_small_protocol(),
        protocol_path=PROTOCOL,
        quant_data_root=tmp_path / "empty",
        generated_at_utc=datetime(2026, 7, 11, 14, tzinfo=UTC),
        source_commit="test",
    )
    series = artifact["snapshots"][0]["series"][0]
    assert series["status"] == "data_blocked"
    assert series["bars"] == []
    assert series["payload_hash"] is None
    assert audit["funnel"]["data_blocked_series"] == 1
    assert {row["capability"]: row["status"] for row in audit["capabilities"]} == {
        "source_identity_pinning": "supported",
        "strict_asof_aggregation_mechanics": "supported",
        "underlying_ohlcv_asof": "data_present_but_unverified",
        "roll_provenance": "data_present_but_unverified",
        "delta_dte": "blocked",
        "causal_iv": "data_present_but_unverified",
        "regime": "blocked",
        "option_price_cadence": "blocked",
        "dd_line": "blocked",
        "bid_ask": "blocked",
    }
