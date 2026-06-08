"""Unit tests for SWEET_SPOTS PA-native matching in scripts/score_today.py.

Regression coverage for B1-2 (2026-06-08) — before the fix, all PA records
came out with `matched_sweet_spots=[]` because the only US rule
(`US-bot-swing-mid-h20`) keyed on `prior_swing_distance_pct`, a DIF-lane
context feature that PA detectors never populate.  This module pins the
PA-native rule predicates so a future SWEET_SPOTS edit can't silently
regress to "0/N matched".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib

score_today = importlib.import_module("scripts.score_today")
match_rule = score_today.match_rule
SWEET_SPOTS = score_today.SWEET_SPOTS
SweetSpotRule = score_today.SweetSpotRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pa_us_60min_rec(
    *,
    pa_trend: str = "uptrend",
    pa_legs: int = 0,
    direction: str = "bottom",
    subtype: str = "pa_us_60min_uptrend",
    level: str = "pa_us_60min",
) -> dict:
    """Build a minimal PA US 60min record dict (mirrors score_today output)."""
    return {
        "direction": direction,
        "level": level,
        "subtype": subtype,
        "pa_trend": pa_trend,
        "pa_legs": pa_legs,
        "matched_sweet_spots": [],
    }


def _us_pa_rules() -> list[SweetSpotRule]:
    """The US-equity PA-native rules currently shipped in SWEET_SPOTS."""
    return [r for r in SWEET_SPOTS if r.pool_class == "us_equity"]


# ---------------------------------------------------------------------------
# Rule-table shape
# ---------------------------------------------------------------------------

def test_us_pa_rules_present():
    """B1-2: at least one PA-native US rule lives in SWEET_SPOTS."""
    rules = _us_pa_rules()
    assert rules, "expected PA-native US rules after B1-2 fix"
    rids = {r.rule_id for r in rules}
    assert "US-PA-60min-uptrend-hopp" in rids
    assert "US-PA-60min-uptrend-legs1" in rids


def test_us_pa_rules_use_pa_native_constraints():
    """The new rules must NOT rely on DIF-lane bucket constraints."""
    for r in _us_pa_rules():
        assert r.swing_constraint is None, f"{r.rule_id} still uses DIF swing_constraint"
        assert r.wick_constraint is None, f"{r.rule_id} still uses DIF wick_constraint"
        assert r.vol_constraint is None, f"{r.rule_id} still uses DIF vol_constraint"
        assert r.level_constraint is not None or r.feature_constraints is not None, (
            f"{r.rule_id} has no PA-native predicate"
        )


def test_us_pa_rules_flagged_as_draft():
    """Until 60/40 re-validation, PA-native US rules must carry the draft note."""
    for r in _us_pa_rules():
        assert "draft" in r.validation_status.lower(), (
            f"{r.rule_id} should be marked draft until OOS re-validation"
        )


# ---------------------------------------------------------------------------
# match_rule — PA-native predicates
# ---------------------------------------------------------------------------

def test_pa_us_60min_uptrend_legs0_matches_base_only():
    """legs=0 records should match the base rule, NOT the legs=1 premium rule."""
    rec = _pa_us_60min_rec(pa_trend="uptrend", pa_legs=0)
    rules = {r.rule_id: r for r in _us_pa_rules()}
    base = rules["US-PA-60min-uptrend-hopp"]
    premium = rules["US-PA-60min-uptrend-legs1"]
    assert match_rule(base, rec["direction"], rec["subtype"], ctx={}, rec=rec,
                       sig_level=rec["level"]) is True
    assert match_rule(premium, rec["direction"], rec["subtype"], ctx={}, rec=rec,
                       sig_level=rec["level"]) is False


def test_pa_us_60min_uptrend_legs1_matches_both():
    rec = _pa_us_60min_rec(pa_trend="uptrend", pa_legs=1,
                            subtype="pa_us_60min_uptrend_legs1")
    rules = {r.rule_id: r for r in _us_pa_rules()}
    for rid in ("US-PA-60min-uptrend-hopp", "US-PA-60min-uptrend-legs1"):
        assert match_rule(rules[rid], rec["direction"], rec["subtype"], ctx={},
                           rec=rec, sig_level=rec["level"]) is True, rid


def test_pa_us_60min_downtrend_no_match():
    rec = _pa_us_60min_rec(pa_trend="downtrend", pa_legs=1)
    for r in _us_pa_rules():
        assert match_rule(r, rec["direction"], rec["subtype"], ctx={}, rec=rec,
                           sig_level=rec["level"]) is False, r.rule_id


def test_pa_us_dif_pos_does_not_match_60min_rules():
    """Different level — even with uptrend+legs1, the level_constraint blocks it."""
    rec = {
        "direction": "bottom",
        "level": "pa_us_dif_pos",  # NOT pa_us_60min
        "subtype": "pa_us_bull",
        "pa_trend": "uptrend",
        "pa_legs": 1,
    }
    for r in _us_pa_rules():
        assert match_rule(r, rec["direction"], rec["subtype"], ctx={}, rec=rec,
                           sig_level=rec["level"]) is False, r.rule_id


def test_context_a_record_no_match():
    """context_a records lack pa_trend/pa_legs entirely."""
    rec = {
        "direction": "bottom",
        "level": "context_a",
        "subtype": "context_a",
    }
    for r in _us_pa_rules():
        assert match_rule(r, rec["direction"], rec["subtype"], ctx={}, rec=rec,
                           sig_level=rec["level"]) is False


# ---------------------------------------------------------------------------
# Backward compatibility — DIF-lane match_rule (rec=None path)
# ---------------------------------------------------------------------------

def test_legacy_dif_call_signature_still_works():
    """Old DIF call site passes (rule, dir, subtype, ctx) without rec/sig_level."""
    # Synthesise a CN-index 'standard' bottom — matches CN-bot-standard-h5.
    cn_rule = next(r for r in SWEET_SPOTS if r.rule_id == "CN-bot-standard-h5")
    assert match_rule(cn_rule, "bottom", "standard", ctx={}) is True
    assert match_rule(cn_rule, "bottom", "weakness", ctx={}) is False
    assert match_rule(cn_rule, "top", "standard", ctx={}) is False


def test_legacy_dif_call_rejects_pa_native_rules_when_rec_none():
    """A PA-native rule must NOT match when called via the legacy 4-arg path
    (no rec, no sig_level) — the level_constraint should fail closed."""
    pa_rule = next(r for r in _us_pa_rules() if r.rule_id == "US-PA-60min-uptrend-hopp")
    # 4-arg call — rec defaults to None, sig_level defaults to None.
    assert match_rule(pa_rule, "bottom", "pa_us_60min_uptrend", ctx={}) is False


# ---------------------------------------------------------------------------
# Annotate helper
# ---------------------------------------------------------------------------

def test_annotate_helper_populates_matched_sweet_spots():
    """_annotate_pa_sweet_spots mutates the record in place."""
    rec = _pa_us_60min_rec(pa_trend="uptrend", pa_legs=1,
                            subtype="pa_us_60min_uptrend_legs1")
    score_today._annotate_pa_sweet_spots(rec, _us_pa_rules())
    assert set(rec["matched_sweet_spots"]) == {
        "US-PA-60min-uptrend-hopp",
        "US-PA-60min-uptrend-legs1",
    }


def test_annotate_helper_no_match_leaves_empty_list():
    rec = _pa_us_60min_rec(pa_trend="downtrend", pa_legs=2)
    score_today._annotate_pa_sweet_spots(rec, _us_pa_rules())
    assert rec["matched_sweet_spots"] == []
