# PA / Feitian M3 Scope Review Packet

Date: 2026-07-09
Branch: `coordination/pa-feitian-m3-scope-review`
Base: `main` at `c7b20060c8da7237623d86525977c94d60de42a5`
Status: ready for ChatGPT scope review before implementation

## Current State

M2 is merged into `main` through PR #11.

Current M2 artifact path:

```text
score_today artifact
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> frontend fixture copy
  -> frontend renderDashboard(snapshot, manifest)
```

Important current files:

- `src/engine/pa_feitian/contract.py`
- `src/engine/pa_feitian/scorecard_producer.py`
- `src/engine/pa_feitian/manifest.py`
- `src/engine/pa_feitian/schema_validation.py`
- `doc/schemas/pa_feitian_snapshot_v1.schema.json`
- `doc/schemas/pa_feitian_decision_trace_v1.schema.json`
- `doc/schemas/pa_feitian_run_manifest_v1.schema.json`
- `frontend/pa-feitian-dashboard/app.mjs`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_run_manifest_v1.json`

The local post-merge cleanup removed implementation worktrees that were fully
merged into `origin/main`. Local remaining worktrees are only coordination
review branches plus this M3 planning branch.

## M3 Objective

M3 should move from reproducible artifact plumbing into focused PA / Feitian
v0.2 decision-chain quantization.

The source handoff says v0.2 should focus on:

1. stop-clear illusion;
2. late / pullback / MACD watch boundary;
3. `watch -> armed_watch -> trade_ready` second trigger;
4. thin/stale right-tail handling;
5. product-direction layering.

M3 should not be a broad retuning project. It should preserve the current
reproducible snapshot + manifest discipline and produce reviewer-visible
decision-chain evidence.

## Non-Goals

- No live trading.
- No order execution.
- No broad parameter sweep.
- No ML retuning.
- No posterior outcome leakage into decision-time rules.
- No futures-R stop substitution for option execution.
- No promotion of watch right-tail into trade-ready.
- No AU put promotion unless explicitly approved later.
- No global default change from snapshot v0/v1 without explicit integration
  approval.

## Known Constraints

The v0.2 handoff emphasizes fidelity over EV:

- `false_trade = 0` is more important than catching every right-tail runner.
- Premium-space execution must use option premium stop/entry/outcome space.
- Stop-first then right-tail is a diagnostic, not a valid trade.
- `4%-12%` stop distance is only a necessary AU-call risk-budget gate, not a
  sufficient trade signal.

Important golden cases from the handoff:

- `p7e_a04c62c53446_0080`: AU call stop-clear illusion; should not become
  trade-ready.
- `p7e_c0493d86aee2_0054`: CZCE.ma.call stop-clear illusion; should not become
  trade-ready.
- `p7e_f88d962c3fb8_0077`: CZCE.ta.call clear-stop stop-first; should not
  become trade-ready.
- AU put `0097/0098/0099`: observation-only.
- AU call A-class trades `0012/0019/0057/0058`: should not be killed without
  explicit premium-stop / confirmation evidence.
- `p7e_365569db90e4_0081`: thin/stale right-tail; liquidity gate should not be
  relaxed by posterior right-tail.

## Proposed M3 Shape

M3 should start with an audit-only task before implementation.

### Workstream 1: Strategy Audit

Branch proposal: `strategy/pa-feitian-m3-v02-audit`

Output a read-only implementation map:

- Where v0.1 rule tree / decision chain currently lives.
- Where `stop_clarity`, `stop_ref_source`, `reason_codes`,
  `decision_trace`, and `would_trade` are generated.
- How premium validation reads predictions / packets / posterior outcomes.
- Which tests protect no-lookahead, premium-space stop, trade/watch split, and
  product-direction split.
- The smallest implementation points for v0.2 focused fixes.

This task should not edit production code.

### Workstream 2: Shared Contract Decision

Branch proposal: `shared/pa-feitian-m3-decision-intent`

Open design question:

Should M3 create a new `pa_feitian_snapshot_v2`, or keep snapshot v1 stable and
add a sidecar decision-intent artifact referenced by the manifest?

Candidate fields needed for M3:

- `decision_state`: `watch | armed_watch | trade_ready | observation_runner |
  reject`
- `execution_allowed`: boolean
- `product_direction_tier`
- `premium_stop`: source, entry premium, stop premium, distance pct
- `confirmation`: premium breakout/reclaim/pullback/1B-2B-3B evidence
- `liquidity`: nonzero volume ratio, stale bar ratio, recovery status
- `reason_codes`: structured list
- `no_lookahead_inputs`: input refs and digests

Contract should remain explicit and schema-validated.

### Workstream 3: Strategy v0.2 Adapter

Branch proposal: `strategy/pa-feitian-m3-v02-adapter`

Only after audit + contract review:

- Implement stop-clear downgrade rule.
- Implement `watch -> armed_watch -> trade_ready` readiness state.
- Implement AU call 4%-12% premium stop-distance soft gate.
- Downgrade `half_loss_fixed` from true clear stop.
- Prevent MACD alert-only from becoming trade-ready.
- Add thin/stale right-tail observation reason codes.
- Preserve AU put as observation-only.
- Add focused tests for all golden cases.

The adapter must not use posterior premium outcomes as decision-time signals.
Posterior outcomes may only appear in evaluation annotations.

### Workstream 4: Frontend Reviewer View

Branch proposal: `frontend/pa-feitian-m3-decision-review`

The dashboard should show reviewer-facing decision-chain evidence:

- snapshot / manifest provenance;
- decision state labels;
- reason code drill-down;
- premium-stop distance and source;
- confirmation status;
- liquidity status;
- product-direction tier;
- clear warning when a row is observation-only or posterior diagnostic.

Frontend should continue consuming committed/generated artifacts only. It should
not read raw data pipelines.

### Workstream 5: Integration

Branch proposal: `integration/pa-feitian-v02-m3`

Acceptance path:

```text
v0.2 focused input fixture
  -> decision-state artifact / snapshot
  -> run manifest
  -> frontend fixture copy
  -> dashboard reviewer drill-down
```

Required checks should include:

- focused Python tests for contract + strategy adapter;
- golden-case regression tests;
- no-lookahead tests;
- JSON Schema validation with external refs;
- frontend smoke for reviewer decision-state view;
- `git diff --check`.

## Proposed Hermes Cards

1. `M3-PLAN-001`: prepare M3 scope review packet.
2. `M3-REVIEW-001`: collect ChatGPT review verdict before M3 implementation.
3. `M3-AUDIT-001`: read-only v0.2 implementation map.
4. `M3-CONTRACT-001`: contract/sidecar design for decision readiness.
5. `M3-STRAT-001`: focused v0.2 strategy adapter.
6. `M3-FE-001`: frontend reviewer decision-chain view.
7. `M3-INTEG-001`: integrate M3 artifact path after review.

Only `M3-AUDIT-001` should be unblocked before review if a conservative start
is desired. `M3-CONTRACT-001`, `M3-STRAT-001`, `M3-FE-001`, and
`M3-INTEG-001` should wait for ChatGPT scope review.

## Review Questions For ChatGPT

1. Is M3 correctly scoped as v0.2 focused decision-chain quantization rather
   than broader score/EV optimization?
2. Should the next contract step be snapshot v2 or a manifest-referenced
   sidecar decision-intent artifact?
3. Should the first executable card be read-only audit only, or can contract
   design begin in parallel?
4. Are the proposed golden cases sufficient for the first v0.2 regression
   suite?
5. Is frontend reviewer mode necessary in M3, or should M3 stop at strategy
   artifacts plus manifest?

## Recommended Verdict Criteria

ChatGPT should return one of:

- `APPROVE_M3_SCOPE`: unblock M3 audit and contract design.
- `APPROVE_AUDIT_ONLY`: unblock only M3 audit; keep implementation blocked.
- `REQUEST_SCOPE_REPAIR`: identify blocking scope issues before any M3 card.

