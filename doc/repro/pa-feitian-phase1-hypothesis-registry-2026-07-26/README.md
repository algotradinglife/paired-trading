# PA / Feitian Phase 1 hypothesis registry freeze

This packet freezes the version 1 Phase 1 hypothesis registry after the
M6-EXP-013 negative gate. It contains three source-traceable hypotheses and
selects exactly one successor experiment before enrollment or outcome
inspection.

The selected experiment is `P1-EXP-001`, a prospective descriptive test of the
already fixed causal signal-day IV-rank mechanism. Its prospective
training/validation/single-use-holdout windows, SHFE ag/au long-call universe,
Black-76 IV inversion convention, 40-observation warmup, 0.66 rank cutoff,
17-completed-daily-bar response, sealed admission ledgers, exclusions, staged
sample gates, equal-weighted within-product estimand, 17-trading-day
moving-block bootstrap, and mutually exclusive classification rules are fixed
in the registry.

`P1-EXP-001` is materially distinct from M6-EXP-013. It does not reuse or alter
the rejected structural-label mapping, its 1/3/5-bar horizons, its training
gate, or its fixed eight-series corpus. M6-EXP-013 remains negative or
inconclusive, with an empty candidate set and no holdout application.

The runner comparison remains parked until its risk basis and policy semantics
are source-complete. The DD-line W-retest hypothesis is explicitly labelled a
non-authentic proxy and remains blocked on intraday option bars and historical
bid/ask evidence.

No market data, outcome, parameter search, M7/M8 work, production mutation,
live trading, or execution evidence is part of this issue.

## Artifacts

- `docs/research/pa-feitian-phase1-hypothesis-registry-v1.json`
- `docs/research/pa-feitian-phase1-hypothesis-registry-v1.lock.json`
- `src/engine/pa_feitian/hypothesis_registry.py`
- `src/scripts/validate_pa_feitian_hypothesis_registry.py`
- `src/tests/test_pa_feitian_hypothesis_registry.py`

## Verify

```sh
cd src
uv run python -m scripts.validate_pa_feitian_hypothesis_registry --repo-root ..
uv run pytest tests/test_pa_feitian_hypothesis_registry.py -q
```

The validator verifies the four issue-mandated source hashes, hypothesis
provenance, the single-selection invariant, the frozen M6 rejection boundary,
the selected parameters, and both the lock values and validator-pinned v1
anchors for the full-registry and canonical-design hashes. Any future result
must bind those hashes; a changed registry requires a new registry version and
experiment id.
