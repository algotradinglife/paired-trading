import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/research/pa-feitian-m6-bare-k-premium-path-protocol-v1.json"
EVIDENCE_PATH = ROOT / "doc/repro/pa-feitian-m6-bare-k-protocol-2026-07-12/bare_k_protocol_evidence_v1.json"
EXPECTED_CONTRACT_SHA256 = "8934b1c301a9e25adf6e00c9f2328c542e2f02e24efdb8b87d48b3c65f8d6dc8"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _prefix(rows: list[dict], cutoff: str) -> list[dict]:
    limit = datetime.fromisoformat(cutoff.replace("Z", "+00:00")).astimezone(timezone.utc)
    return [
        row
        for row in rows
        if datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).astimezone(timezone.utc) <= limit
    ]


def _classify(
    *,
    explicit_alert: bool,
    direction: str | None = None,
    unit_membership: bool = False,
    required_bar: bool = False,
    authentic_rule: bool = False,
    predicates_pass: bool = False,
) -> str:
    if not explicit_alert:
        return "blocked_missing_explicit_pa_alert"
    if direction not in {"bottom_or_bullish", "top_or_bearish"}:
        return "abstain_direction"
    if not unit_membership:
        return "blocked_missing_unit_membership"
    if not required_bar:
        return "abstain_missing_required_bar"
    if not authentic_rule:
        return "blocked_authentic_rule_unrecovered"
    return "confirmed_bare_k" if predicates_pass else "alert_only"


def test_contract_is_hash_pinned_and_protocol_only() -> None:
    contract = _load(CONTRACT_PATH)
    evidence = _load(EVIDENCE_PATH)

    assert hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest() == EXPECTED_CONTRACT_SHA256
    assert evidence["contract"]["sha256"] == f"sha256:{EXPECTED_CONTRACT_SHA256}"
    assert contract["frozen_before_external_research_or_data_inspection"] is True
    assert contract["research_mode"] == "retrospective_finalized_protocol_only"
    assert contract["guardrails"]["proxy_or_imputation"] is False
    assert contract["guardrails"]["outcomes_or_performance"] is False
    assert contract["output_contract"]["performance_fields"] is False
    assert contract["output_contract"]["selection_artifact"] is False


def test_input_capability_gaps_preserve_blocked_states() -> None:
    evidence = _load(EVIDENCE_PATH)
    states = {item["capability_state"] for item in evidence["bound_input_verification"]}

    assert states == {"blocked_missing_explicit_pa_alert", "blocked_missing_unit_membership"}
    assert evidence["source_research_audit"]["rule_recovery_state"] == "blocked_authentic_rule_unrecovered"
    assert evidence["protocol_state_summary"]["confirmed_bare_k_reachable"] is False


def test_post_cutoff_append_cannot_change_consumed_prefix() -> None:
    cutoff = "2025-01-02T07:00:00Z"
    rows = [{"ts": "2025-01-02T06:55:00Z", "close": 10}]
    future_extreme = {"ts": "2025-01-02T07:05:00Z", "close": 999999}

    assert _prefix(rows + [future_extreme], cutoff) == _prefix(rows, cutoff)


def test_state_precedence_rejects_confirmation_without_frozen_rule() -> None:
    assert _classify(explicit_alert=False) == "blocked_missing_explicit_pa_alert"
    assert _classify(explicit_alert=True, direction="flat") == "abstain_direction"
    assert _classify(explicit_alert=True, direction="bottom_or_bullish") == "blocked_missing_unit_membership"
    assert (
        _classify(explicit_alert=True, direction="bottom_or_bullish", unit_membership=True)
        == "abstain_missing_required_bar"
    )
    assert (
        _classify(
            explicit_alert=True,
            direction="bottom_or_bullish",
            unit_membership=True,
            required_bar=True,
        )
        == "blocked_authentic_rule_unrecovered"
    )


def test_public_packet_has_only_public_safe_source_aliases_and_hashes() -> None:
    evidence = _load(EVIDENCE_PATH)
    serialized = EVIDENCE_PATH.read_text()

    assert "/home/" not in serialized
    assert "/Users/" not in serialized
    assert "drwho1985" not in serialized.lower()
    for source in evidence["source_research_audit"]["sources"]:
        assert source["alias"].startswith("public://")
        prefix, digest = source["sha256"].split(":", 1)
        assert prefix == "sha256"
        assert len(digest) == 64
        int(digest, 16)
