# Research OS Workflow

This document defines how research work moves from a GitHub issue to reviewed
evidence and then, when authorized, to `main`. [`STATUS.md`](STATUS.md) is the
source of truth for the current research gate; the issue and its bound artifacts
are the source of truth for an individual task.

## Start Gate

Before implementation or evidence work begins:

1. A GitHub issue must define the objective, exact start state, deliverables,
   boundaries, acceptance criteria, owner, and target branch.
2. Align the working copy or Jujutsu workspace to the issue's exact baseline.
   Preserve unrelated local changes and report any alignment conflict.
3. Read the latest `STATUS.md` gate and every prerequisite named by the issue.
4. Move the issue to `state/in-progress` only after the prerequisites pass.

No open-ended research, outcome-driven corpus changes, or work beyond the
issue's authorization is part of the task.

## Branch and PR Flow

```text
role task branch or bookmark -> develop -> integration/promotion -> main
```

- Strategy, Data, and scoped engineering work target `develop` unless the issue
  explicitly defines another reviewed integration target.
- Promotion work targets `main` only after its prerequisite role changes are
  reviewed and present on `develop`.
- Every PR names its issue, exact head, base branch, validation commands,
  verdict, and remaining boundaries.
- Do not treat a merge as strategy approval. The bound research verdict and
  the current `STATUS.md` gate remain authoritative.

## Issue Status Routing

Use the repository's exact `state/*` labels:

```text
state/ready -> state/in-progress -> state/review -> state/awaiting-review
                                                       |
                                                       v
                                               state/reviewing -> state/completed

Any active state may move to state/blocked and return when its named dependency
is resolved. state/cancelled is terminal and maps to GitHub's not-planned close
reason. state/review may move directly to state/reviewing when a reviewer is
already available.
```

| Move to | Meaning | Notification owner |
| --- | --- | --- |
| `state/ready` | Scope and prerequisites are ready to start | Session selected by the `owner/*` label |
| `state/in-progress` | The assigned owner is actively working | Assigned owner |
| `state/review` | Deliverables and validation packet are ready | PI/reviewer |
| `state/reviewing` | Review is actively running | PI/reviewer |
| `state/awaiting-review` | A required independent review is queued | PI/reviewer |
| `state/blocked` | A named dependency or evidence gate prevents progress | PI |
| `state/completed` | Acceptance is met and the issue is closed as completed | Assigned owner |
| `state/cancelled` | Work will not proceed under this issue | PI and assigned owner |

Ownership labels are `owner/strategist`, `owner/data`, and `owner/engineer`.

## PI Review

PI validates a PR against:

- **Goal alignment**: the PR does what the issue asks.
- **Scope boundary**: there is no scope creep or missing required scope.
- **Roadmap fit**: the change respects the current project gate.
- **Plan consistency**: implementation and evidence match the declared design.
- **Research integrity**: causal cutoffs, frozen inputs, provenance, negative
  results, and fail-closed behavior are preserved.

PI has sole merge authority. Outcomes are `APPROVED` or
`CHANGES_REQUIRED`.

## Engineering Validation (EV)

When the issue or PI requires EV, use a fresh, independent, read-only reviewer
after the exact PR head is fixed. The implementation session must not issue its
own independence verdict.

### Universal checks

1. Confirm the exact PR head, base, issue, and release binding when applicable.
2. Run the issue's required tests and verifiers from a clean checkout.
3. Reproduce committed artifacts and compare bytes or declared hashes.
4. Check issue acceptance, scope, public-safety/redaction, and repository diff.
5. Re-read the current PR and issue state immediately before the verdict.

### Evidence-contract checks

When the issue defines an archive or staged evidence chain, also verify:

1. archive membership and recursive SHA-256 bindings;
2. complete clean replay and byte/package identity;
3. every declared source-to-output binding, such as
   `source -> G0 -> panel -> B0/B1`;
4. missing, rejected, negative, and insufficient-sample cells reconcile
   without silent dropping.

### Receipt format

```text
[ENGINEERING VALIDATION][PASS|CHANGES_REQUIRED|STALE_EV_REQUEST]
Reviewer: <independent reviewer/session>
Requested by: PI
Exact HEAD: <40-character SHA>
Issue: <number>
Release: <tag or not-applicable>
Mutations: none
Tests: <commands and results>
Clean replay: <result or not-applicable>
Findings: <none or actionable findings>
```

## Current Research Boundary

The 2026-08-03 gate preserves `stop_p1_exp_002`, M6R `no_candidate`, and the
M6M decision `method_reconciled_recommend_path`. M6F then recovered a
source-authorized prospective construct protocol and an accepted sealed
confirmation-reserve route, but the accepted causal-measurement capability
receipt failed all ten interfaces. Its terminal is therefore
`source_fidelity_measurement_failure`.

This is a closed-negative research result. It does not falsify or validate the
authentic Feitian chain, and it cannot open a preregistration-design Issue. No
follow-on research task is automatically authorized. The next permitted action
is a PI strategy/method disposition decision; any later execution of that
decision requires its own reviewed Issue and exact boundary.

The reserve remains sealed, unseen, and unreleased. Experiment, backtest,
preregistration design, M7, M8, M9, implementation, live/shadow trading, and
execution remain blocked. The exact evidence, contamination, and disposition
options are recorded in `STATUS.md`.
