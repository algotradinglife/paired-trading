# PA decision-graph protocol v1

Status: Strategy-owned M6P protocol packet

Terminal: `needs_revision`

This packet freezes a source-pinned, interpretable PA decision graph and a
forward-feedback contract. It is a separate non-authentic PA baseline; it does
not recover, validate, or continue the authentic Feitian method. The accepted
M6F terminal remains `source_fidelity_measurement_failure`.

## Scope and start revision

- Exact repository start: `develop@bbaef61c9fda1531ab9a7281b9ed544a5cbccb4b`.
- External PA baseline: `rosemarycox5334-debug/PA_Agent@d92ecd827fe671a589b7fdfdbba41e5e98081d87`.
- The packet imports byte-exact fixtures for only the three required PA source
  files and records their source paths, hashes, and selected branches in
  `source_manifest_v1.json`.
- Existing `decision_trace_v1` and evaluation contracts are reference-only;
  historical schemas and meanings are not rewritten.

## Why this method line exists

The M6F evidence cannot authorize an authentic Feitian experiment. The PA source
does provide an explicit entry-side decision tree, structural stop, targets, and
risk checks, while it explicitly omits post-entry position management. This
packet therefore separates upstream PA semantics from `pi_policy_extension`
rules and requires a complete causal lifecycle before M7 can be considered.

## Current terminal and PI gate

`pi_management_adjudication_v1.md` contains five upstream-silent management
branches with bounded alternatives and no implicit defaults. PI explicitly
selected and refined every rule in Issue #85 comment
[#5169587241](https://github.com/algotradinglife/paired-trading/issues/85#issuecomment-5169587241).
The lifecycle binds event-time hard-stop precedence, two-bar confirmation and
weakening, a fixed 0.5 TP1 fraction with a 0.5 runner, monotonic three-bar pivot
ratchets, no arbitrary time exit, and right-censor exclusion.

## Contract artifacts

1. `source_manifest_v1.json` — exact upstream commit, fixture hashes, provenance
   classes, selected branches, and excluded material.
2. `decision_graph_registry_v1.json` — stable nodes, edges, source references,
   and frozen topology declaration.
3. `trade_lifecycle_contract_v1.json` — closed-bar state machine, guards,
   actions, terminal reasons, and unresolved PI extensions.
4. `pi_management_adjudication_v1.md` — bounded alternatives and explicit
   no-default policy for every upstream-silent management branch.
5. `episode_semantics_v1.md` — independent recommendation/override/outcome
   streams, integrity statuses, eligibility truth table, and correct-error rule.
6. `weight_learning_protocol_v1.md` — frozen topology, interpretable weights,
   shrinkage, 10/30/20 forward gates, multi-metric review, promotion, and
   rollback.
7. `downstream_issue_graph_v1.md` — one-owner M7/M8 sequence and dependency
   routing without opening child issues here.
8. `fixtures/` — byte-exact upstream source snapshots plus deterministic replay
   fixtures.
9. `verify.mjs` — offline verifier; it never fetches live market data.

## Semantic repair controls

- `trade_lifecycle_contract_v1.json` publishes one action vocabulary and a
  total state × action allow/reject matrix. Its `transition_contract` is
  derived from the allow cells; the verifier rejects drift rather than
  accepting a hand-maintained replay switch.
- The registry must reach every node from `observe.readable`, keep a
  fail-closed complement for every decision, resolve every source fragment, and
  equal the lifecycle transition set for all lifecycle nodes. PA §2.5 is bound
  explicitly as `direction.momentum_support` / `BD-2.5-momentum-support`.
- Replay checks derive state, integrity, event-time stop precedence, collision
  quarantine, two-bar confirmation, and post-TP1 ratchets from that authority.
  Fixture `kind` and later outcome fields cannot repair an invalid path.
- Eligibility fixtures cover all 7 integrity statuses × 2 policy-stream
  origins × 2 override-stream origins × 2 completion states (56 cells), with
  profitable invalid rows required to remain quarantined.

## Authorization boundary

Only the packet terminal `protocol_ready_for_m7` authorizes creation of the M7
child issue graph. It does not authorize M8 observation, automatic order routing,
capital, reserve release, execution, neural networks, reinforcement learning,
topology mutation, or authentic Feitian claims. `needs_revision` and
`reject_pa_baseline` authorize none of those actions.
There is no automatic order routing or execution in this packet.

## Verification

From the repository root:

```text
node doc/repro/pa-decision-graph-protocol-v1/verify.mjs
node doc/repro/pa-decision-graph-protocol-v1/verify.mjs --negative
```

The verifier checks source bytes and hashes, branch coverage, graph references,
state/action dispositions, accepted PI adjudication, event precedence,
future-input rejection, truth-table eligibility, fixture replay determinism, and
documentation completeness. `protocol_ready_for_m7` authorizes creation of the
M7 child issue graph only; it does not authorize M8 observation, routing, capital,
or execution.
