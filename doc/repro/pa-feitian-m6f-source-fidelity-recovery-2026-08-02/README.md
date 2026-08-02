# M6F source-fidelity recovery

Issue: [#77](https://github.com/algotradinglife/paired-trading/issues/77)

Evidence date: 2026-08-02

Execution baseline: `develop@7673394a9710036bf7ea9fb79d515b8a6beb0290`

Governance baseline: `main@4fa3dc4c3df59fa545a15fb48e01d42f95ff4d07`

Terminal: **`source_fidelity_unrecoverable_construct`**

Manifest SHA-256: `625025b3acb52d73f0cef5b45b99a6fa3fc2c76b2276bc9dea0bc5339f50ca11`

## Decision

The pinned source names the Feitian chain and pins completed option daily
candles, the roles of the two line families, left-path preference, structural
invalidation, and premium-space management at a narrative level. It does not
provide source-authorized deterministic semantics for the complete critical
chain. In particular, direction generation, contract selection, both anchor
protocols, 1B/2B, holistic quality, full conflict ordering, invalidation
evaluation, and exit/runner/roll mechanics cannot be recovered without adding
behavior.

No open external dependency was created. No newly versioned source
authorization was supplied by the original source author, and the admitted
method and proxy artifacts cannot originate that authorization. Under Issue
#77's precedence rule, unresolved critical semantics therefore require
`source_fidelity_unrecoverable_construct`; subordinate measurement and reserve
failures cannot replace that terminal.

This result neither validates nor falsifies authentic Feitian. PI may not open
a preregistration-design Issue from this packet. A future, separately reviewed
source-recovery version could reconsider the gate only from new source-author
authorization captured before outcome comparison.

## Exact admitted evidence

| Class | Immutable evidence | Raw-byte SHA-256 | Permitted use |
| --- | --- | --- | --- |
| Source narrative | `trade-philosopher@715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a`, `doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md` | `2ea78aa6e6addc24bbb132dc2d104d182ce24060e6a8be72ad120063fa4ed263` | Public-safe claim paraphrase and gap identification |
| Method constraint | `trade-philosopher@5802d0ff5d99819ad01ba9f3550b6a2d504f1e81`, `doc/self-evolving-trader-methodology-2026-06-28.md` | `2e36134eb763cfa4786ab6561a7ccb3704c5f3f88dfa28cc177ddaf44520b90d` | Fidelity and representation discipline only |
| Method constraint | `trade-philosopher@7691c31dceb0bb37a77d9fd8c98dc0746dc1361d`, `doc/pa-replication/high-quality-annotation-dataset-v2.md` | `2d883ab3c9b3d30e9dc7d0e6976f09e7cef7f98b96fc9d26ccb79556fdfcd543` | Plane separation and discovery/confirmation routing only |
| Gap inventory | `paired-trading@cb08cfb7f3f5d0082ff13343bcbb324f25a96733`, `doc/repro/pa-feitian-m6-operationalized-rule-v0/source_assumption_ledger_v0.json` | `44836421b78ee316f04492a25117e0332fe484c30916e1bfb5c16d6844838058` | Identify proxy inventions; never source authorization |
| Accepted method decision | `paired-trading@7673394a9710036bf7ea9fb79d515b8a6beb0290`, M6M `README.md` | `2be9a373b74fa6b0ebdc59cf179dbf29f8b7bbc9db185f65129f110b20b0f463` | Successor scope and terminal discipline |
| Accepted independent receipt | `paired-trading@7673394a9710036bf7ea9fb79d515b8a6beb0290`, M6M receipt | `686b392b3be95267355b9942f5836e47590285d90fadc4a34825139a1656a811` | Verify the accepted M6M interpretation |

`source_authorized` is unused: no admitted record contains explicit approval
of an exact semantic claim or annotation protocol by the original source
author. The 580 and 769 revisions are method constraints. The M6 ledger is a
proxy-gap inventory. Neither class can be promoted into source semantics.

## Ten-node recovery result

| Node | Status | Fail-closed reason |
| --- | --- | --- |
| `SF-01-UNDERLYING-DIRECTION` | `unresolved` | No causal direction protocol or required source fields |
| `SF-02-OPTION-CONTRACT` | `provisional_gap` | Indicative selection description lacks lifecycle and tie semantics |
| `SF-03-DAILY-CHART` | `source_pinned` | Completed daily cadence is pinned; session and bar-end measurement is not |
| `SF-04-DD-LOW-LINE` | `unresolved` | Anchor, tie, touch, projection, and tolerance protocol absent |
| `SF-05-DESCENDING-HIGH-LINE` | `unresolved` | Anchor and construction absent; chart plane left open |
| `SF-06-ONE-B-TWO-B` | `unresolved` | No deterministic classifier or source-authorized labels |
| `SF-07-HOLISTIC-QUALITY` | `unresolved` | No source-authorized holistic adjudication protocol |
| `SF-08-ENTRY-ORDERING` | `provisional_gap` | Left preference pinned; complete conflict/fill order absent |
| `SF-09-STRUCTURAL-INVALIDATION` | `provisional_gap` | Reference buffer and evaluation convention absent |
| `SF-10-PREMIUM-MANAGEMENT` | `provisional_gap` | Targets, runner line, roll mapping, and price convention absent |

Every unresolved or provisional node abstains. No historical outcome, M6
proxy rule, model consensus, or convenience threshold fills a gap.

## Measurement and confirmation route

`measurement_readiness_v1.json` defines the complete future interface for all
ten construct inputs and outputs, including source fields, exchange time and
session, candle completion, availability cutoff, lifecycle, premium basis,
expiry/roll mapping, accepted/rejected-row accounting, provenance, replay, and
fail-closed behavior. No field is marked pass because no admitted public-safe
Data-owner receipt binds all required elements. A Data dependency was not
opened because semantic unrecoverability is already terminal and takes
precedence.

`confirmation_reserve_contract_v1.json` fixes a non-overlap rule that excludes
all construct-recovery and discovery evidence, including all 72 M6R episodes
and derivatives. It reveals no identity or outcome. It also records that no
PI-approved non-Strategy custodian or sealed identity manifest exists, so the
route is not mechanically enforceable and readiness cannot pass.

The append-only contamination ledger records known P1, M6, M6R, and M6M
exposure; access to the pinned source and method evidence; governance review;
and the absence of new authorization or a sealed reserve. The M6R entry records
only the already known frozen conclusion and exclusion boundary. The 72
episodes were not inspected, relabeled, filtered, tuned against, or used as
confirmation.

## Package and verification

The manifest binds the five research payloads plus `schema_v1.json` and
`verify.mjs` by exact path, byte length, and raw-byte SHA-256. It excludes
itself, this README, and the independent receipt to avoid circular hashes.
All structured artifacts use the canonical serialization required by Issue
#77.

Evidence-head verification:

```sh
node doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/verify.mjs --evidence-head
node doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/verify.mjs --evidence-head --negative
head_sha=$(jj log -r @ --no-graph -T 'commit_id')
git diff --check 7673394a9710036bf7ea9fb79d515b8a6beb0290 "$head_sha"
```

After a fresh reviewer validates the fixed evidence head, the implementer adds
only `independent-evidence-validation-receipt.md` in a child commit. Final-head
verification drops `--evidence-head`; a fresh external EV comment must bind the
exact final PR head and confirm the evidence-head-to-final-head diff contains
only that receipt.

## Public-safety and scope attestation

This work inspected only the committed governance, source, method, and gap
evidence listed above. It did not inspect raw market or option rows, the M6R
episode payloads, provider implementation, credentials, or `quant_data/`, and
it did not execute a data CLI. The diff contains no data or provider change.
It introduces no experiment, backtest, outcome or EV computation, parameter,
candidate implementation, production policy, or M7 work.

## Final PI packet

- Terminal: **`source_fidelity_unrecoverable_construct`**.
- Exact blocking semantics: all critical gaps listed in the ten-node table.
- Attempted evidence routes: the pinned source narrative, existing M6 gap
  inventory, accepted M6M interpretation, and method constraints; none contains
  a new original-source authorization.
- Measurement state: complete interface, no passing capability receipt; not
  terminal because critical semantics fail first.
- Confirmation state: exclusion rule frozen, but no custodian or sealed route.
- Downstream decision: **PI may not open a separate preregistration-design
  Issue from this result**. Experiment and M7 remain unauthorized.
