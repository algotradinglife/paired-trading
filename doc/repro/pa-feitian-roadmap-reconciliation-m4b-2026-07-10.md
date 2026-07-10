# PA/Feitian Roadmap Reconciliation: M4b

Date: 2026-07-10

Repository: `algotradinglife/paired-trading`

Base commit: `3c2b50e` (`PA/Feitian M4: reproducible daily review artifact loop`)

## Why This Exists

The ChatGPT roadmap defines M4 as:

```text
M4: real data / real score_today path
```

The merged PR #14 completed the reusable artifact loop:

```text
score_today artifact or deterministic fixture fallback
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1
  -> copied dashboard fixtures
  -> renderDashboard(snapshot, manifest, decisionIntent)
```

That is necessary M4 infrastructure, but it is not the complete roadmap M4
unless a real score_today artifact can be produced from the current data
interfaces and passed through the loop without fixture fallback.

To keep the roadmap precise:

- merged PR #14 is treated as **M4a: review artifact loop infrastructure**.
- the next milestone is **M4b: real score_today production path**.
- **M5 remains Premium-space outcome harness** and must not be redefined as
  daily review operations.

## Roadmap Alignment

| Stage | Roadmap Objective | Current State |
| --- | --- | --- |
| M1 | Snapshot contract and read-only dashboard | Complete |
| M2 | Reproducible artifact and manifest | Complete |
| M3 | Reviewer audit loop | Partially complete: reviewer view and decision-intent sidecar exist, but persistent override / annotation ledger is not complete |
| M4a | Review artifact loop infrastructure | Complete via PR #14 |
| M4b | Real data / real score_today production path | Next |
| M5 | Premium-space outcome harness | Not started |
| M6 | Strategy evaluation and filtering | Not started |
| M7 | Semi-automated decision console | Not started |
| M8 | Small-scale shadow/live monitoring | Not started |
| M9 | Controlled execution candidate | Not started |

## M4b Objective

Produce a real score_today artifact from the current repository data interfaces
and prove it can flow through the already-merged M4a loop:

```text
current data interfaces
  -> real score_today artifact
  -> M4a builder
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1
  -> copied dashboard fixtures
  -> renderDashboard(snapshot, manifest, decisionIntent)
```

## M4b Acceptance Criteria

- A documented data-interface audit identifies the current score_today entry
  points, required data roots, required symbols/pools, and known blockers.
- At least one real score_today artifact can be emitted from current data
  interfaces without synthetic rows.
- The artifact is classified as `real_data_available` only when it is produced
  from real current data interfaces.
- Fixture fallback remains available for deterministic tests, but M4b evidence
  must include a non-fixture path.
- The M4a builder consumes the real artifact and emits snapshot v1, run manifest
  v1, decision-intent sidecar, and dashboard copies.
- Tests or smoke scripts prove the real-artifact path without raw market scans
  inside the frontend.
- Final ChatGPT acceptance happens only after M4b integration is complete.

## Non-goals

- No live trading.
- No order execution.
- No automatic trade approval.
- No promotion of decision intent into snapshot v2.
- No premium-space outcome harness. That is M5.
- No broad frontend redesign unless required by real-artifact review state.

## Proposed Workstreams

1. `M4B-DATA-001`: Audit current data interfaces for real score_today production.
2. `M4B-STRAT-001`: Emit a real score_today artifact from the audited data path.
3. `M4B-PIPE-001`: Feed the real artifact through the M4a builder and manifest loop.
4. `M4B-INTEG-001`: Integrate the real score_today production path.
5. `M4B-FINAL-001`: Final ChatGPT M4b acceptance and merge.

## Implementation Guardrails

- Prefer existing `score_today` and options-selector code paths over new parallel
  scoring logic.
- Keep frontend artifact-only.
- Keep `pa_feitian_snapshot_v1` and decision-intent sidecar semantics unchanged.
- Classify missing data explicitly as `data_blocked` or `unknown`, not as real.
- Do not mark deterministic fixture output as `real_data_available`.
- Keep generated artifacts deterministic enough for audit: explicit input path,
  source commit, CLI args, data access status, and hashes.

