"""DIR annotation wiring on score_today emit lanes (integration).

Runs score_today's main() in-process on one real symbol and asserts the
emitted records carry the DIR verdict fields. Data-dependent (same
precedent as test_options_emission_faithfulness) — skipped when the
quant store isn't wired.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1]
_STORE = _SRC / "data" / "quant" / "daily"

pytestmark = pytest.mark.skipif(
    not _STORE.is_dir(), reason="quant store not wired (data/quant symlink)"
)

_DIR_KEYS = {"direction_verdict", "direction_confidence", "direction_sources"}


@pytest.fixture(scope="module")
def cu_scored(tmp_path_factory):
    out = tmp_path_factory.mktemp("score") / "cu.json"
    argv_backup = sys.argv
    sys.argv = [
        "score_today.py",
        "--symbols", "kq_m_shfe_cu",
        "--instrument-class", "cn_metal_futures",
        "--window-days", "1500",
        "-o", str(out),
    ]
    try:
        import scripts.score_today as st
        st.main()
    finally:
        sys.argv = argv_backup
    return json.loads(out.read_text())["scored"]


def test_context_a_records_carry_dir_verdict(cu_scored):
    recs = [r for r in cu_scored if r.get("level") == "context_a"]
    assert recs, "no context_a records emitted in window — fixture too narrow"
    for r in recs:
        assert _DIR_KEYS <= set(r), f"context_a record missing DIR fields: {sorted(r)}"
        assert r["direction_verdict"] in ("long_call", "long_put", "skip")


def test_pa_h2_records_carry_dir_verdict(cu_scored):
    # regression guard for the existing pa_h2 wiring
    recs = [r for r in cu_scored if r.get("level") == "pa_h2"]
    for r in recs:
        assert _DIR_KEYS <= set(r)
