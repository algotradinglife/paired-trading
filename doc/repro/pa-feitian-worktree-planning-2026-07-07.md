# PA / Feitian Worktree Planning

Date: 2026-07-07
Repo: `algotradinglife/paired-trading`
Branch: `coordination/pa-feitian-design-review`
Source review packet: `doc/repro/pa-feitian-codex-worktree-review-2026-07-07.md`

## 1. Executive Decision

Approve the current worktree / session / branch orchestration with required guardrails.

Do **not** start broad `strategy` or `frontend` implementation immediately. The next high-leverage step is a small shared contract branch that defines a minimal file-backed PA / Feitian snapshot API:

```text
strategy produces pa_feitian_snapshot_v0.json
frontend consumes only pa_feitian_snapshot_v0.json and renders a read-only dashboard shell
```

Only after this contract is reviewed should the two implementation sessions branch into deeper strategy quantification and richer frontend interaction work.

## 2. Current Coordination State

The coordination packet records the intended branch and worktree model:

```text
baseline/paired-trading-v01
strategy/pa-feitian-v02
frontend/pa-feitian-dashboard
coordination/pa-feitian-design-review
```

The project root remains the baseline/reference surface:

```text
/home/drwho1985/workspace/quant/strats/paired-trading
```

Long-running Codex sessions should work only inside project-local worktrees:

```text
.worktrees/strategy
.worktrees/frontend
.worktrees/coordination
```

Session mapping:

```text
strategy-session     -> strategy/pa-feitian-v02
frontend-session     -> frontend/pa-feitian-dashboard
coordination-session -> coordination/pa-feitian-design-review
```

This model is sound because it gives each long-running Codex session its own branch and filesystem surface while keeping the baseline branch stable for reference.

## 3. Required Guardrails Before Implementation

### 3.1 Promote or freeze the baseline

Preferred path:

```text
baseline/paired-trading-v01 -> main
```

Then create all PA / Feitian implementation branches from the promoted baseline.

If baseline cannot be promoted yet, explicitly declare `baseline/paired-trading-v01` as the temporary base for all PA / Feitian work and keep `main` out of the PA / Feitian review path until the baseline promotion is settled.

Reason: if `strategy` and `frontend` start implementation while baseline is still ahead of `main`, later PRs will mix baseline history with actual feature changes and become hard to review.

### 3.2 Keep coordination docs-only

`coordination/pa-feitian-design-review` should remain orchestration-only:

- review packets
- planning docs
- branch/session/Hermes sequencing notes
- no business logic
- no strategy code
- no frontend code
- no shared contract implementation

If coordination starts carrying implementation, it becomes a third implementation branch and will complicate integration.

### 3.3 Make `.worktrees/` exclusion portable

The packet says `.worktrees/` is excluded via `.git/info/exclude`. That is local-only. Add a repository-level ignore rule:

```text
.worktrees/
```

This is a collaboration safety belt, not a strategy change.

## 4. Shared Contract First

Create a short-lived branch:

```text
shared/pa-feitian-contract-v0
```

Purpose: define the minimal contract between strategy producer and frontend consumer before either side invents incompatible fields.

Recommended files:

```text
doc/schemas/pa_feitian_snapshot_v0.schema.json
src/engine/pa_feitian/contract.py
src/scripts/emit_pa_feitian_snapshot.py
src/tests/fixtures/pa_feitian_snapshot_v0.json
src/tests/test_pa_feitian_contract.py
```

Recommended responsibility split:

| File | Responsibility |
|---|---|
| `doc/schemas/pa_feitian_snapshot_v0.schema.json` | Stable JSON boundary consumed by both branches |
| `src/engine/pa_feitian/contract.py` | Python type / validation / serialization helpers |
| `src/scripts/emit_pa_feitian_snapshot.py` | File-backed producer CLI |
| `src/tests/fixtures/pa_feitian_snapshot_v0.json` | Committed fixture for frontend and contract tests |
| `src/tests/test_pa_feitian_contract.py` | Schema / fixture / compatibility tests |

Do not place full strategy logic or dashboard logic in this shared branch. It should stay small and easy to merge into both `strategy` and `frontend`.

## 5. Minimal Snapshot Contract

The first contract should be intentionally small. It should prove that strategy can produce a stable artifact and frontend can render it.

Suggested top-level shape:

```json
{
  "schema_version": "pa_feitian_snapshot_v0",
  "generated_at_utc": "2026-07-07T00:00:00Z",
  "source_commit": "<git-sha>",
  "run_config": {},
  "data_quality": {},
  "summary": {},
  "signals": [],
  "warnings": []
}
```

Suggested `signals[]` fields:

| Field | Meaning |
|---|---|
| `id` | Stable signal id |
| `instrument` | Product or underlying instrument |
| `contract` | Contract symbol if applicable |
| `interval` | Bar interval |
| `ts_utc` | Signal timestamp in UTC |
| `underlying_signal` | PA / divergence / breakout alert source |
| `features_det` | No-lookahead deterministic features |
| `decision` | Strategy decision; may be null in v0 |
| `decision_trace` | Decision-chain trace; may be null or partial in v0 |
| `option_leg` | call / put, strike, DTE, delta / OTM rank if known |
| `iv_regime` | IV-rank gate annotation |
| `exit_policy` | runner / fixed TP / tick stop / data-blocked status |
| `outcome` | Mechanical outcome if available |
| `status` | `keep`, `drop`, `advisory`, `data_blocked`, or `model_dominated` |
| `caveats` | Explicit warnings such as missing bid/ask or modeled price dominance |

Important distinction: do not collapse underlying-R outcome and option-premium outcome into one ambiguous `r` field. Use explicit names such as:

```text
underlying_r_outcome
premium_r_outcome
option_runner_outcome
proxy_outcome
```

Feitian option timing must be evaluated in premium space. Underlying-R evidence can be attached as context, but should not be treated as the final option strategy outcome.

## 6. Strategy Work Order

Strategy should claim work only after the shared contract branch exists or as the producer side of that contract.

### STRAT-001A — Snapshot producer CLI

Implement a CLI that emits a deterministic JSON snapshot:

```text
src/scripts/emit_pa_feitian_snapshot.py --out data/review/pa_feitian_snapshot_v0.json
```

Constraints:

- file-backed only
- no frontend dependency
- no raw data pipeline writes
- no execution / order placement
- no broad Feitian strategy expansion yet

### STRAT-001B — IV-regime annotation

Use existing pure IV-regime gate logic as an annotation layer.

Output should include:

```json
"iv_regime": {
  "iv_rank": 0.42,
  "keep": true,
  "reason": null
}
```

If IV history is insufficient, mark it explicitly:

```json
"iv_regime": {
  "iv_rank": null,
  "keep": false,
  "reason": "iv_warmup(<40 prior signals)"
}
```

### STRAT-001C — Option leg fields

Expose option-leg selection fields without overstating production readiness:

```json
"option_leg": {
  "side": "call",
  "strike": null,
  "dte": null,
  "otm_rank": null,
  "delta_estimate": null,
  "selection_status": "advisory"
}
```

If data is missing, use `data_blocked`, not fabricated values.

### STRAT-001D — Exit policy status

Represent the current state of runner / fixed TP / tick-stop logic explicitly.

Examples:

```json
"exit_policy": {
  "mode": "runner",
  "status": "advisory",
  "reason": "premium runner preferred; production integration pending"
}
```

```json
"exit_policy": {
  "mode": "tick_stop",
  "status": "data_blocked",
  "reason": "tick-level premium stop requires intraday option bid/ask"
}
```

### STRAT-001E — Contract tests

Add tests that verify:

- fixture validates against schema
- producer output validates against schema
- timestamps are UTC
- `features_det` is no-lookahead
- `outcome` is not overwritten by decision-side labels
- `status` is one of the allowed enum values

## 7. Frontend Work Order

Frontend should not begin business UI work until the committed schema and fixture exist.

It may then start from the fixture, not from live strategy internals.

### FE-001A — Read-only dashboard shell

Build a dashboard that reads:

```text
src/tests/fixtures/pa_feitian_snapshot_v0.json
```

and renders:

- summary cards
- signals table
- keep / drop / advisory / data-blocked counts
- warnings panel

### FE-001B — Defensive states

Handle:

- empty `signals[]`
- schema mismatch
- unknown `schema_version`
- missing optional fields
- `data_blocked`
- `model_dominated`
- `advisory`

### FE-001C — Signal drill-down

Clicking a signal should show:

- underlying alert
- deterministic features
- IV-regime decision
- option-leg annotation
- exit-policy annotation
- decision trace
- caveats
- outcome fields

### FE-001D — Integration path

Only after the fixture UI works should frontend consume a generated snapshot path from strategy.

Frontend must not:

- compute strategy fields itself
- read raw data stores
- call data pipeline commands
- infer missing contract fields
- depend on ignored `data/review/*.jsonl` artifacts as the only input

## 8. Hermes Card Split

Keep the current `STRAT-001` and `FE-001` as parent epics. Split actual work into smaller claimable cards.

Recommended cards:

```text
COORD-001 baseline promotion decision
COORD-002 add repo-level .worktrees ignore
CONTRACT-001 pa_feitian_snapshot_v0 schema + fixture
CONTRACT-002 contract validation test
STRAT-001A snapshot producer CLI
STRAT-001B IV-regime annotation
STRAT-001C option-leg annotation
STRAT-001D exit-policy status annotations
STRAT-001E golden snapshot tests
FE-001A read-only dashboard shell from fixture
FE-001B defensive schema / empty / blocked states
FE-001C signal drill-down viewer
FE-001D generated snapshot integration
INTEG-001 strategy emits snapshot, frontend renders it, tests pass
```

Recommended claim order:

```text
COORD-001 / COORD-002
  -> CONTRACT-001 / CONTRACT-002
  -> STRAT-001A + FE-001A
  -> STRAT-001B/C/D + FE-001B/C
  -> INTEG-001
```

## 9. Integration Branch and Merge Model

Recommended conservative path:

```text
baseline/paired-trading-v01
    -> shared/pa-feitian-contract-v0
    -> strategy/pa-feitian-v02
    -> frontend/pa-feitian-dashboard
    -> integration/pa-feitian-v02
    -> main
```

Operationally:

1. Merge shared contract into `strategy` and `frontend` before either branch builds on the contract.
2. Keep strategy and frontend PRs reviewable on their own.
3. Use `integration/pa-feitian-v02` only to verify that the producer and consumer align.
4. Do not use integration as a dumping ground for unresolved implementation work.

## 10. First Integration Milestone

The first milestone should be narrow and concrete:

```text
strategy emits pa_feitian_snapshot_v0.json
frontend renders pa_feitian_snapshot_v0.json
both pass contract tests
```

Acceptance criteria:

| Area | Acceptance |
|---|---|
| Schema | Snapshot validates against `pa_feitian_snapshot_v0.schema.json` |
| Fixture | Committed fixture renders offline |
| Strategy | Producer emits deterministic file-backed snapshot |
| Frontend | Dashboard reads only snapshot / fixture |
| Drill-down | Signal detail page shows trace, IV, option leg, exit policy, caveats |
| Defensive states | Empty / blocked / model-dominated / advisory states are visible |
| Tests | Strategy contract tests and frontend fixture-render tests pass |
| Repo boundary | No frontend raw-data access; no strategy data-pipeline writes |

## 11. Risk Register

### R1 — Baseline not promoted before implementation

Impact: PRs mix baseline history with feature changes and become difficult to review.

Mitigation: promote baseline first or formally freeze it as the PA / Feitian base.

### R2 — Shared contract branch grows into implementation

Impact: shared branch becomes hard to merge into both strategy and frontend.

Mitigation: keep shared branch to schema, fixture, validation, and a minimal producer stub only.

### R3 — Frontend defines fields before contract exists

Impact: frontend schema drifts and forces strategy-side rework.

Mitigation: frontend starts only from committed fixture and schema.

### R4 — Premium-space and underlying-R outcomes are mixed

Impact: Feitian option strategy may be incorrectly accepted or rejected.

Mitigation: explicitly separate premium-space, underlying-R, proxy, and runner outcomes.

### R5 — Data-blocked areas are hidden by optimistic UI

Impact: dashboard appears production-ready despite missing bid/ask, put chain, or intraday option data.

Mitigation: expose `data_blocked`, `model_dominated`, and `advisory` as first-class statuses.

### R6 — Strategy/front-end sessions violate repo boundary

Impact: sessions accidentally read or mutate raw data pipeline state.

Mitigation: strategy consumes existing store outputs and emits snapshots; frontend consumes snapshots only. Any data availability or raw-data gap goes through data-engineer cards.

## 12. Final Recommendation

Proceed with the orchestration plan, but only under this operating rule:

```text
No broad strategy or frontend implementation before pa_feitian_snapshot_v0 exists.
```

Recommended immediate next actions:

1. Decide baseline promotion / freeze policy.
2. Add `.worktrees/` to repo-level ignore.
3. Create `shared/pa-feitian-contract-v0`.
4. Add schema + fixture + validation test.
5. Let strategy implement snapshot producer.
6. Let frontend build read-only shell from fixture.
7. Use integration branch only for producer-consumer alignment.

This keeps the project reviewable, prevents contract drift, and preserves the separation between strategy research, frontend presentation, data pipeline responsibilities, and coordination state.
