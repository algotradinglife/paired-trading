# PA / Feitian M2 Execution Plan

Date: 2026-07-08

Planning branch: `coordination/pa-feitian-m2-review`

Foundation main commit: `4a4c5c3d791ef21f8d26c3eddc04d8d0ab4d0f53`

## Review Verdict

ChatGPT verdict for REVIEW-003:

`APPROVE WITH NON-BLOCKING FOLLOW-UPS`

There are no blocking findings before M2 planning.

## M2 Objective

Create a reproducible artifact path:

```text
score_today artifact
  -> pa_feitian_snapshot_v1
  -> run manifest
  -> copied dashboard snapshot
  -> reviewer-facing trace drill-down
```

## Non-Goals

- No live trading.
- No order execution.
- No persistent reviewer override database.
- No full premium-space outcome simulator.
- No bid/ask tick-stop validation.
- No global promotion of v1 as the default producer output.

## Non-Blocking Follow-Ups Included In M2

- Add a run manifest schema and manifest writer tying together scorecard artifact, snapshot artifact, source commit, CLI args/config, input/output hashes, frontend copy path, and review state.
- Add JSON Schema validation with external ref resolution for `pa_feitian_snapshot_v1` -> `pa_feitian_decision_trace_v1`.
- Add generated v1 snapshot frontend smoke coverage, not only committed fixture smoke.
- Add visible dashboard labels for fixture/generated/review snapshot modes.
- Keep v1 shadow until reviewed against generated `score_today` artifacts.

## Hermes Card Topology

### Shared

Card: `t_540fec78`

Title: `M2-SHARED-001 run manifest contract and schema validation`

Branch/worktree:

- Branch: `shared/pa-feitian-m2-manifest`
- Worktree: `.worktrees/shared-m2-manifest`
- Assignee: `shared-m2-session`

Status policy:

- Initially scheduled.
- Start only after user/coordinator M2 kickoff.

Acceptance summary:

- Manifest schema and fixture validate deterministically.
- Snapshot v1 schema validation resolves `pa_feitian_decision_trace_v1` external/ref dependency.
- Focused pytest, ruff, and `git diff --check` pass.

### Strategy

Card: `t_4d568e81`

Title: `M2-STRAT-001 deterministic score_today artifact to v1 snapshot and manifest`

Branch/worktree:

- Branch: `strategy/pa-feitian-m2-real-scorecard-artifact`
- Worktree: `.worktrees/strategy-m2-scorecard`
- Assignee: `strategy-m2-session`

Depends on:

- `t_540fec78`

Acceptance summary:

- Deterministic `score_today` artifact -> `pa_feitian_snapshot_v1` -> manifest path is reproducible from CLI/test.
- Manifest hash fields are stable across repeated identical runs.
- Existing v0 producer behavior remains unchanged.
- Data access status is classified explicitly.

### Frontend

Card: `t_eed9b39a`

Title: `M2-FE-001 generated/review snapshot dashboard mode`

Branch/worktree:

- Branch: `frontend/pa-feitian-m2-generated-review-mode`
- Worktree: `.worktrees/frontend-m2-generated-review`
- Assignee: `frontend-m2-session`

Depends on:

- `t_540fec78`
- `t_4d568e81`

Acceptance summary:

- Dashboard renders fixture/generated/review labels without ambiguity.
- Dashboard can consume generated v1 snapshots copied into frontend fixtures.
- Manifest/provenance panel renders deterministic metadata when present.
- Existing v0 fallback smoke remains passing.

### M2 Review Gate

Card: `t_002324c5`

Title: `M2-REVIEW-001 review M2 artifacts before integration`

Branch/worktree:

- Branch: `coordination/pa-feitian-m2-review`
- Worktree: `.worktrees/m2-review`
- Assignee: `coordination-session`

Depends on:

- `t_540fec78`
- `t_4d568e81`
- `t_eed9b39a`

Acceptance summary:

- GitHub-visible review packet records branch SHAs, changed files, artifact paths, manifest examples, verification commands, and known risks.
- ChatGPT verdict is collected before integration.
- Blocking findings become repair cards.

### Integration

Card: `t_d2367cec`

Title: `M2-INTEG-001 integrate PA/Feitian M2 artifact path`

Branch/worktree:

- Branch: `integration/pa-feitian-v02-m2`
- Worktree: `.worktrees/integration-m2`
- Assignee: `coordination-session`

Depends on:

- `t_002324c5`

Merge order:

1. `shared/pa-feitian-m2-manifest`
2. `strategy/pa-feitian-m2-real-scorecard-artifact`
3. `frontend/pa-feitian-m2-generated-review-mode`

Acceptance summary:

- Integration branch is pushed to origin.
- End-to-end smoke proves `score_today` artifact -> `pa_feitian_snapshot_v1` -> manifest -> frontend copied/generated render.
- Required pytest, ruff, frontend smoke, and `git diff --check` pass.

## Worker Session Policy

- One active implementation card maps to one worktree and one Codex session.
- Do not create worker sessions until the corresponding card is unblocked for kickoff.
- Close worker sessions after their branch is pushed and the card is completed.
- Keep `paired-trading-codex` as the coordinator session.

