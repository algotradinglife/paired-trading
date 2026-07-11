# PA / Feitian M6 Final Internal Review Packet — 2026-07-11

Review owner: Codex internal review

Review base: `bdcce5d` (M5 merged)

Engineering foundation under review: `db26211` (`PA/Feitian M6: reproducible real baseline evidence (#22)`)

## Final Decision

```text
M6_ENGINEERING_FOUNDATION_MERGED
M6_STRATEGY_SCREENING_BLOCKED
DO_NOT_ADVANCE_TO_M7
```

The M6 engineering foundation is merged: typed evaluation contracts, an
artifact-only M5 baseline evaluator, no-lookahead checks, controlled-comparison
machinery, dashboard review support, and reproducible real baseline evidence
are present and independently verified.

M6 strategy screening is blocked. The runtime OptionStore `daily/` root used
for this review contains zero files, so the original premium paths required to
evaluate any recoverable candidate exit policy are unavailable. No candidate
M5 sidecar, M6 candidate dataset, candidate aggregate, relative-baseline
result, ranking, or strategy inference was generated. The checked-in outcome
is therefore `data_blocked`, unavailable, and inconclusive—not negative or
promising evidence.

Consequently, M6 does not satisfy its screening gate for M7. Do not begin M7
semi-automated decision-console work from this evidence packet.

## Evidence Reviewed

The real baseline packet projects the four existing M5 observed premium
outcomes without rescanning a market store, rerunning `score_today`, or
reselecting contracts.

| Baseline measure | Result |
| --- | ---: |
| Effective events | 4 |
| Mean premium R | `-1.00090361445` |
| Premium-R win rate (`R > 0`) | `0.0` |
| Cluster-bootstrap 95% CI | `[-1.00271084335, -1.0]` |
| Walk-forward folds | 2; each OOS result `insufficient_sample` |
| No-lookahead verifier | passed for both folds |

These are descriptive baseline observations only. They do not demonstrate an
edge, approve the M5 policy, or substitute underlying R for premium R.

The blocked candidate record identifies the missing recoverable paths for:

- `au2606c1152`
- `au2606c1136`
- `ag2607c19900`
- `ag2608c18800`

Before a candidate policy may be evaluated, recover the provenance-bearing
daily OptionStore OHLC series for every contract; ensure that each series begins
strictly after its decision and covers the declared holding window; reproduce
the applicable M5 selected-option-bar hashes; then declare the retrospective
candidate before traversal and generate a new M5 sidecar, M6 artifacts, and
verifier. This packet must not be rewritten to imply that recovery occurred.

## Artifact Integrity

The independently rebuilt and validated baseline manifest pins:

| Artifact | SHA-256 |
| --- | --- |
| Evaluation dataset | `sha256:b7307d5617698c089309b1facea7ce6782ce2962d4295c8b6ca1906f2a1773ba` |
| Evaluation aggregate | `sha256:6613ca6b6536d942f5750d168170038559b3be270540f86aa488041528fd2d3c` |

Relevant review paths:

- M6 scope: [pa-feitian-m6-strategy-evaluation-scope-2026-07-11.md](../design/pa-feitian-m6-strategy-evaluation-scope-2026-07-11.md)
- Real baseline and blocked-candidate packet: [pa-feitian-m6-real-evidence-2026-07-11](pa-feitian-m6-real-evidence-2026-07-11/README.md)
- Candidate availability record: [candidate_availability_v1.json](pa-feitian-m6-real-evidence-2026-07-11/candidate_availability_v1.json)

## Independently Run Scoped Checks

All commands below were run from the integration worktree after the engineering
foundation merge. The supplied isolated M6 Python environment was used because
the repository-local `uv` resolver cannot resolve its worktree-relative
`quant-cli` source path.

| Check | Result |
| --- | --- |
| `PYTHONPATH=src /tmp/paired-trading-m6-venv/bin/python -m pytest src/tests/test_pa_feitian_evaluation_contract.py src/tests/test_pa_feitian_baseline_evaluator.py src/tests/test_pa_feitian_policy_comparison.py src/tests/test_pa_feitian_review_artifact_builder.py -q` | `24 passed` |
| `PYTHONPATH=src /tmp/paired-trading-m6-venv/bin/python -m pytest src/tests/test_pa_feitian*.py src/tests/test_eval_tbreak_premium.py -q` | `109 passed` |
| `/tmp/paired-trading-m6-venv/bin/ruff check src/engine/pa_feitian src/scripts/evaluate_pa_feitian_m6_baseline.py src/scripts/compare_pa_feitian_m6_policies.py src/tests/test_pa_feitian_evaluation_contract.py src/tests/test_pa_feitian_baseline_evaluator.py src/tests/test_pa_feitian_policy_comparison.py src/tests/test_pa_feitian_review_artifact_builder.py` | `All checks passed!` |
| `npm run smoke` in `frontend/pa-feitian-dashboard` | `22 passed` |
| `QUANT_DATA_ROOT=…/quant/data/quant PA_FEITIAN_PYTHON=/tmp/paired-trading-m6-venv/bin/python node doc/repro/pa-feitian-m6-real-evidence-2026-07-11/verify.mjs` | `{"ok":true,"candidate_evidence":"data_blocked_unavailable"}` |
| `git diff --check bdcce5d..HEAD` | clean |
| Changed-file secret/private-key pattern review | clean |

The deterministic verifier rebuilt the baseline dataset, aggregate, and
manifest; validated typed contracts and pinned hashes; confirmed an empty
runtime `daily/` directory; and left tracked artifacts unchanged.

## Guardrails Confirmed

- No live trading, order execution, broker integration, or automatic strategy
  approval path was introduced.
- The dashboard consumes copied artifacts; it does not query an OptionStore or
  scoring pipeline.
- Candidate absence is retained as `data_blocked` / inconclusive rather than
  being imputed from baseline or underlying results.
- M7 remains gated on recoverable candidate premium paths and a completed,
  comparable M6 screening result.
