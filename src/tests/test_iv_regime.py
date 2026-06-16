"""Unit tests for engine/options/iv_regime.py — the Feitian Rule 2 IV-regime gate
(causal expanding-window IV-rank, drop rich-IV signals). Look-ahead-free; pure logic."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

iv_regime = importlib.import_module("engine.options.iv_regime")
causal_iv_rank = iv_regime.causal_iv_rank
iv_regime_keep = iv_regime.iv_regime_keep
iv_regime_decision = iv_regime.iv_regime_decision


def test_rank_none_during_warmup():
    # fewer than `warmup` prior signals → cannot rank
    assert causal_iv_rank(0.2, [0.1, 0.3], warmup=40) is None
    assert causal_iv_rank(0.2, list(range(39)), warmup=40) is None


def test_rank_is_fraction_of_strictly_lower_priors():
    priors = [i / 100 for i in range(40)]      # 0.00..0.39, n=40
    # current 0.205 → strictly-below count = 0.00..0.20 = 21 values → 21/40
    assert causal_iv_rank(0.205, priors, warmup=40) == 21 / 40
    # current below all → 0.0 ; above all → 1.0 (40/40)
    assert causal_iv_rank(-1.0, priors, warmup=40) == 0.0
    assert causal_iv_rank(99.0, priors, warmup=40) == 1.0


def test_gate_keeps_low_rank_drops_high_rank_inclusive_boundary():
    assert iv_regime_keep(0.33, max_rank=0.66) is True
    assert iv_regime_keep(0.66, max_rank=0.66) is True       # boundary inclusive (<=)
    assert iv_regime_keep(0.67, max_rank=0.66) is False
    assert iv_regime_keep(1.0, max_rank=0.66) is False


def test_warmup_none_respects_allow_flag():
    assert iv_regime_keep(None, allow_during_warmup=False) is False   # conservative default
    assert iv_regime_keep(None, allow_during_warmup=True) is True


def test_decision_reasons():
    priors = [i / 100 for i in range(40)]      # 0.00..0.39
    kept = iv_regime_decision(0.10, priors, max_rank=0.66)            # rank 11/40=0.275 → keep
    assert kept["keep"] is True and kept["reason"] is None
    dropped = iv_regime_decision(0.39, priors, max_rank=0.66)         # rank 39/40=0.975 → drop
    assert dropped["keep"] is False and "iv_rank_rich" in dropped["reason"]
    warm = iv_regime_decision(0.2, [0.1, 0.2], max_rank=0.66)         # insufficient history
    assert warm["iv_rank"] is None and warm["keep"] is False and "iv_warmup" in warm["reason"]


def test_none_iv_is_unrankable():
    assert causal_iv_rank(None, [0.1] * 50) is None
    assert iv_regime_decision(None, [0.1] * 50)["keep"] is False


def test_non_finite_iv_is_unrankable_not_cheapest():
    # NaN/inf current IV must NOT rank as 0.0 (cheapest) and get kept — it's unrankable → drop
    assert causal_iv_rank(float("nan"), [0.1] * 50) is None
    assert causal_iv_rank(float("inf"), [0.1] * 50) is None
    assert iv_regime_decision(float("nan"), [0.1] * 50)["keep"] is False
    # NaN values inside the prior history are filtered out before ranking
    assert causal_iv_rank(0.2, [0.1] * 45 + [float("nan")] * 10, warmup=40) == 1.0
