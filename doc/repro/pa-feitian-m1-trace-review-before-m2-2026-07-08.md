# PA / Feitian Review Packet Before M2 Planning

Date: 2026-07-08

Repo: `algotradinglife/paired-trading`

Branch for this packet: `coordination/pa-feitian-m2-review`

Main commit under review: `4a4c5c3d791ef21f8d26c3eddc04d8d0ab4d0f53`

## Request to ChatGPT

Please review the completed PA / Feitian M1 + trace-v1 work before proposing the next work plan.

Use a two-stage response:

1. Review verdict on the work already merged to `main`.
2. M2 plan only after the review verdict.

Do not skip straight to implementation planning. The first priority is to identify whether the completed foundation is coherent, whether any boundary or contract issues should be repaired first, and whether the next milestone should be adjusted.

## Review Scope

The completed work turns the PA / Feitian subjective option-timing decision chain into a reproducible, versioned snapshot path:

- A shared `pa_feitian_snapshot_v0` contract.
- A scorecard-backed strategy producer that emits validated snapshots from `score_today` style JSON records.
- A read-only dashboard shell that consumes copied snapshot fixtures, not raw data stores.
- A `decision_trace_v1` shadow contract for structured subjective decision-chain review.
- Dashboard rendering for `decision_trace_v1.nodes`, with `pa_feitian_snapshot_v0` fallback preserved.

The work is intentionally not yet a full live trading system. It is a contract-first, fixture-backed, reproducible baseline for later market-data-backed and review-loop work.

## Mainline Merge History

Current `main` first-parent PA / Feitian history:

- PR #1: integration branch into `baseline/paired-trading-v01`.
- PR #2: promote `baseline/paired-trading-v01` to `main`.
- PR #3: `strategy/pa-feitian-scorecard-producer-refactor`.
- PR #4: `frontend/pa-feitian-generated-snapshot-copy`.
- PR #5: `shared/pa-feitian-contract-v1-trace` design note.
- PR #6: `shared/pa-feitian-decision-trace-v1`.
- PR #7: `frontend/pa-feitian-decision-trace-v1`.

Recent `main` commits:

```text
4a4c5c3 Merge pull request #7 from algotradinglife/frontend/pa-feitian-decision-trace-v1
5d361a0 Render PA Feitian decision trace v1 in dashboard
dd8bf44 Merge pull request #6 from algotradinglife/shared/pa-feitian-decision-trace-v1
dea6c91 Implement PA Feitian decision trace v1 shadow contract
b7ac428 Merge pull request #5 from algotradinglife/shared/pa-feitian-contract-v1-trace
d57a354 Document PA Feitian decision trace v1 design
c30c44d Merge pull request #4 from algotradinglife/frontend/pa-feitian-generated-snapshot-copy
173a26d Generalize PA Feitian dashboard snapshot copy
a7d033f Merge pull request #3 from algotradinglife/strategy/pa-feitian-scorecard-producer-refactor
```

## Key Files

Shared contract and schemas:

- `doc/schemas/pa_feitian_snapshot_v0.schema.json`
- `doc/schemas/pa_feitian_decision_trace_v1.schema.json`
- `doc/schemas/pa_feitian_snapshot_v1.schema.json`
- `src/engine/pa_feitian/contract.py`
- `src/engine/pa_feitian/scorecard_producer.py`
- `src/scripts/emit_pa_feitian_snapshot.py`

Fixtures and tests:

- `src/tests/fixtures/pa_feitian_snapshot_v0.json`
- `src/tests/fixtures/pa_feitian_snapshot_v1.json`
- `src/tests/test_pa_feitian_contract.py`
- `src/tests/test_pa_feitian_scorecard_producer.py`
- `src/tests/test_pa_feitian_e2e_smoke.py`

Frontend:

- `frontend/pa-feitian-dashboard/app.mjs`
- `frontend/pa-feitian-dashboard/scripts/copy-snapshot-fixture.mjs`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v0.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json`
- `frontend/pa-feitian-dashboard/test/dashboard-smoke.test.mjs`

Design:

- `doc/design/pa-feitian-decision-trace-v1-2026-07-08.md`

## Completed Behavior

### Contract

- `pa_feitian_snapshot_v0` remains supported.
- `pa_feitian_snapshot_v1` is added as an explicit shadow contract.
- `decision_trace_v1` contains structured trace nodes with:
  - trace version
  - action
  - status
  - summary
  - input refs
  - nodes
  - per-node evidence
- The v1 fixture covers:
  - `keep`
  - `data_blocked`
  - `model_dominated`

### Strategy Producer

- Scorecard-to-snapshot conversion is in `src/engine/pa_feitian/scorecard_producer.py`.
- `contract.py` is primarily schema/model/load/write validation.
- Producer input is a score_today-style JSON artifact.
- The producer does not read raw market data stores or mutate data pipeline state.
- Producer default remains `pa_feitian_snapshot_v0`.
- v1 output requires an explicit option:

```bash
python src/scripts/emit_pa_feitian_snapshot.py \
  --out /tmp/pa_feitian_snapshot_v1.json \
  --source-commit <commit> \
  --contract-version pa_feitian_snapshot_v1
```

### Frontend

- Dashboard is static and read-only.
- It fetches copied snapshot fixtures from `frontend/pa-feitian-dashboard/fixtures/`.
- It does not fetch raw data, strategy internals, or data stores.
- Dashboard now defaults to `pa_feitian_snapshot_v1`.
- Dashboard renders `decision_trace_v1.nodes` in signal drill-down.
- Dashboard preserves `pa_feitian_snapshot_v0` legacy `decision_trace` fallback.
- The frontend v1 fixture matches `src/tests/fixtures/pa_feitian_snapshot_v1.json` byte-for-byte.

## Verification Already Run During Integration

For PR #6:

- PA / Feitian contract, producer, and E2E pytest: `14 passed`
- Ruff on PA / Feitian contract/producer/script/tests: passed
- `git diff --check`: clean
- JSON parse checks for v1 schemas and v1 fixture: passed
- CLI smoke:
  - default output is v0 and does not include `decision_trace_v1`
  - explicit v1 emits `decision_trace_v1`

For PR #7:

- `cd frontend/pa-feitian-dashboard && npm run smoke`: `7 passed`
- `git diff --check`: clean
- frontend v1 fixture matches shared v1 fixture byte-for-byte
- HTTP smoke was checked locally after PR creation before merge

## Known Intentional Limits

These are not necessarily bugs, but should be reviewed before M2:

- The v1 contract is a shadow contract, not yet the default producer output.
- The frontend defaults to a copied v1 fixture, not a live/generated artifact path.
- The producer consumes scorecard JSON but does not yet prove a full real market-data run from current data access interfaces.
- `decision_trace_v1` currently traces decision nodes derived from scorecard records; it is not yet a complete interactive subjective review ledger.
- There is no persistent run manifest tying together:
  - source scorecard artifact
  - snapshot artifact
  - source commit
  - input hashes
  - dashboard fixture copy
  - reviewer decision state
- There is no separate audit/replay UI yet for comparing trace nodes across multiple runs or review outcomes.

## Questions for Review Stage

Please answer these before proposing M2 implementation cards:

1. Does the current contract boundary make sense?
   - Shared contract owns schemas/models/load/write.
   - Strategy producer owns scorecard-to-snapshot conversion.
   - Frontend consumes copied snapshot artifacts only.

2. Is `decision_trace_v1` adequate as a first structured representation of the PA / Feitian subjective decision chain?
   - If not, identify the minimum blocking changes before more implementation.

3. Is the v0/v1 compatibility story coherent?
   - Producer default is v0.
   - Dashboard default is v1 fixture.
   - Dashboard preserves v0 fallback.

4. Are there hidden coupling risks between frontend rendering and strategy internals?

5. Are the current tests sufficient for this stage?
   - What tests should be added before M2?

6. Are there data provenance or reproducibility gaps that must be repaired before using real market score_today artifacts?

7. Are there naming, schema, or milestone-boundary problems that should be fixed immediately while the surface area is still small?

## Questions for M2 Planning Stage

Only after giving the review verdict, propose the next milestone plan.

Please structure the M2 proposal as:

- Objective.
- Non-goals.
- Workstream split.
- Suggested branch/worktree/session split.
- Shared contract changes, if any.
- Strategy cards.
- Frontend cards.
- Integration/review gates.
- Verification requirements.
- Risks and ordering constraints.

Candidate M2 direction for consideration:

- Real score_today artifact path:
  - produce a deterministic score_today JSON artifact from available data interfaces
  - record input/source metadata
  - convert it to `pa_feitian_snapshot_v1`
- Reproducibility manifest:
  - artifact hashes
  - source commit
  - config
  - data access status
  - generated snapshot path
- Dashboard generated snapshot mode:
  - consume generated snapshots copied into frontend fixture path
  - distinguish fixture/generated/review snapshots clearly
- Decision-chain review workflow:
  - trace node drill-down suitable for reviewer audit
  - eventually record reviewer overrides or annotations, but only if the contract boundary is ready

## Desired Output

Please return:

1. `REVIEW VERDICT`
   - `APPROVE`, `APPROVE WITH NON-BLOCKING FOLLOW-UPS`, or `BLOCK`
   - blocking findings first, with file/path references where possible

2. `FOUNDATION ASSESSMENT`
   - short assessment of contract, producer, dashboard, testing, and reproducibility

3. `M2 PLAN`
   - only after the verdict
   - concrete cards/workstreams and acceptance criteria

4. `RISKS`
   - especially risks around data access, schema migration, UI overfitting to fixtures, and subjective decision-chain fidelity
