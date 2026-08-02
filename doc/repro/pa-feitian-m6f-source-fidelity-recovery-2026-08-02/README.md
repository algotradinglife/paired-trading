# M6F source-fidelity recovery

Issue: [#77](https://github.com/algotradinglife/paired-trading/issues/77)

Evidence date: 2026-08-02

Execution baseline: `develop@5da299892514c7ca2d7bf1c77baba32f9df9753b`

Governance baseline: `main@4fa3dc4c3df59fa545a15fb48e01d42f95ff4d07`

Current terminal state: **`source_fidelity_measurement_failure`**

Manifest SHA-256: `6a4b9e330caff23491a81319bcaf344e23b1cedd0565c8816c16e78d837c0606`

## Decision

The pinned source names the Feitian chain and pins completed option daily
candles, the roles of the two line families, left-path preference, structural
invalidation, and premium-space management at a narrative level. It does not
provide deterministic semantics for the complete critical chain. The original
source author has now explicitly approved the exact prospective blinded
annotation and adjudication protocol in
[Issue #77 comment 5156155428](https://github.com/algotradinglife/paired-trading/issues/77#issuecomment-5156155428)
without amendment. That approval covers nine previously unresolved semantic
nodes; `SF-03-DAILY-CHART` remains independently `source_pinned`.

The canonical public-safe provenance receipt is
`source_author_provenance_receipt_v1.json`: 1,653 bytes with raw-byte SHA-256
`28ffe0ac718eebb5453f60daf862bdd9961c7d74c2abba2ca987f9ec02f9cbb5`.
It binds the exact 2,874-byte approved protocol body at SHA-256
`dfd44c8eb6127a9dfaf6a872811144acd74e011add4e88d29bc002b5db635d83`.
PI accepted provenance only and did not originate, complete, reinterpret, or
silently fill source semantics.

Source authorization alone is not measurement or outcome evidence. The
accepted Data-owned capability Issue
[#79](https://github.com/algotradinglife/paired-trading/issues/79) receipt is a
closed-negative result: all ten measurement fields fail. Confirmation-reserve
custody Issue [#80](https://github.com/algotradinglife/paired-trading/issues/80)
is closed and accepted with a sealed, mechanically enforceable, unseen and
non-overlapping reserve. No named dependency remains open. Under Issue #77's
precedence rule the accepted #79 failure therefore freezes the terminal as
`source_fidelity_measurement_failure`. PI may not open a
preregistration-design Issue from this packet.

## Exact admitted evidence

| Class | Immutable evidence | Raw-byte SHA-256 | Permitted use |
| --- | --- | --- | --- |
| Source narrative | `trade-philosopher@715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a`, `doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md` | `2ea78aa6e6addc24bbb132dc2d104d182ce24060e6a8be72ad120063fa4ed263` | Public-safe claim paraphrase and gap identification |
| Method constraint | `trade-philosopher@5802d0ff5d99819ad01ba9f3550b6a2d504f1e81`, `doc/self-evolving-trader-methodology-2026-06-28.md` | `2e36134eb763cfa4786ab6561a7ccb3704c5f3f88dfa28cc177ddaf44520b90d` | Fidelity and representation discipline only |
| Method constraint | `trade-philosopher@7691c31dceb0bb37a77d9fd8c98dc0746dc1361d`, `doc/pa-replication/high-quality-annotation-dataset-v2.md` | `2d883ab3c9b3d30e9dc7d0e6976f09e7cef7f98b96fc9d26ccb79556fdfcd543` | Plane separation and discovery/confirmation routing only |
| Gap inventory | `paired-trading@cb08cfb7f3f5d0082ff13343bcbb324f25a96733`, `doc/repro/pa-feitian-m6-operationalized-rule-v0/source_assumption_ledger_v0.json` | `44836421b78ee316f04492a25117e0332fe484c30916e1bfb5c16d6844838058` | Identify proxy inventions; never source authorization |
| Accepted method decision | `paired-trading@7673394a9710036bf7ea9fb79d515b8a6beb0290`, M6M `README.md` | `2be9a373b74fa6b0ebdc59cf179dbf29f8b7bbc9db185f65129f110b20b0f463` | Successor scope and terminal discipline |
| Accepted independent receipt | `paired-trading@7673394a9710036bf7ea9fb79d515b8a6beb0290`, M6M receipt | `686b392b3be95267355b9942f5836e47590285d90fadc4a34825139a1656a811` | Verify the accepted M6M interpretation |
| Source-authorization request | Issue #77 comment `5156135931`, opened `2026-08-02T07:13:41Z` | `18eff5f6dbe6d90e8e36e261782ae8c784152d130dee95438acef9f6167f225f` | Route exact public-safe claims to the original source author; no semantics supplied by the request |
| Approved prospective protocol | Issue #77 comment `5156155428`, created `2026-08-02T07:17:40Z` | `dfd44c8eb6127a9dfaf6a872811144acd74e011add4e88d29bc002b5db635d83` | Exact blinded annotation/adjudication protocol for the nine approved nodes; no measurement or outcome claim |
| Source-author provenance receipt | `source_author_provenance_receipt_v1.json`, authorization received `2026-08-02T07:23:23Z` | `28ffe0ac718eebb5453f60daf862bdd9961c7d74c2abba2ca987f9ec02f9cbb5` | Explicit original-source authorization and public-safe provenance only |
| Accepted Data capability receipt | `paired-trading@8f2c5fb54160a1c61ef6db13d6048e690eb560b1`, `causal_measurement_capability_receipt_v1.json`, accepted in Issue #79 comment `5156979858` | `3b706bd7e5d2c5a488d1f580c947c3676f9762ea7c44b7ea65082b5c9929568f` | Exact closed-negative capability result: 0 pass and 10 fail; no raw rows or provider internals |
| Accepted confirmation-reserve receipt | `paired-trading@5da299892514c7ca2d7bf1c77baba32f9df9753b`, accepted Data head `81ef05de9a71dfb332fa28f86e2702c5a5252a66`, `confirmation_reserve_custody_receipt_v2.json`, accepted in Issue #80 comment `5157958443` | `1a4baa1a72d5c7090397f2619429308679d9efa0d25c38dc50207c01da072610` | Public-safe sealed custody and rule commitments only; no identity, membership, row, outcome, or release |
| Independent reserve attestation | `independent_non_overlap_verification_attestation_v1.json` in the accepted #80 package | `d1929acdea17db8c7dc25458b179959fe0044d7e1e7d51dd95630aff4cb4e062` | Independent non-overlap PASS, all 10 public assertions true and blinded reserve nonempty; no identity or outcome disclosure |

`source_authorized` means only that the original source author approved the
exact prospective protocol for the listed node. It does not mean a label set,
capability receipt, replay trace, strategy outcome, or profitability claim
exists. The 580 and 769 revisions remain method constraints, and the M6 ledger
remains a proxy-gap inventory.

## Ten-node recovery result

| Node | Status | Fail-closed reason |
| --- | --- | --- |
| `SF-01-UNDERLYING-DIRECTION` | `source_authorized` | Approved prospective protocol; causal inputs and replay evidence still absent |
| `SF-02-OPTION-CONTRACT` | `source_authorized` | Approved prospective protocol; lifecycle, tie, and as-of evidence still absent |
| `SF-03-DAILY-CHART` | `source_pinned` | Completed daily cadence is pinned; session and bar-end measurement is not |
| `SF-04-DD-LOW-LINE` | `source_authorized` | Approved prospective protocol; labels, adjudication, and causal trace absent |
| `SF-05-DESCENDING-HIGH-LINE` | `source_authorized` | Approved prospective protocol; labels, chart-plane evidence, and trace absent |
| `SF-06-ONE-B-TWO-B` | `source_authorized` | Approved prospective protocol; blinded labels and adjudication trace absent |
| `SF-07-HOLISTIC-QUALITY` | `source_authorized` | Approved prospective protocol; blinded labels and adjudication trace absent |
| `SF-08-ENTRY-ORDERING` | `source_authorized` | Approved prospective protocol; complete causal ordering and fill evidence absent |
| `SF-09-STRUCTURAL-INVALIDATION` | `source_authorized` | Approved prospective protocol; causal evaluation evidence absent |
| `SF-10-PREMIUM-MANAGEMENT` | `source_authorized` | Approved prospective protocol; premium, lifecycle, and replay evidence absent |

Every node retains a documented fail-closed abstention rule until the approved
protocol and causal measurement evidence are implemented. No historical
outcome, M6 proxy rule, model consensus, or convenience threshold fills a gap.
In the staged DAG, `DAG-10-MANAGEMENT` alone carries the SF-10
`source_authorized_protocol` decision authority. The distinct
`DAG-11-OUTCOME-OBSERVATION` outcome plane remains explicitly `fail_closed`:
the approved protocol does not authorize future bars or outcomes.

## Measurement and confirmation route

`measurement_readiness_v1.json` defines the complete future interface for all
ten construct inputs and outputs, including source fields, exchange time and
session, candle completion, availability cutoff, lifecycle, premium basis,
expiry/roll mapping, accepted/rejected-row accounting, provenance, replay, and
fail-closed behavior. Data-owned Issue #79 is closed with an accepted,
public-safe capability receipt bound by exact bytes and merge revision. Its
result is `fail` for all ten fields, so `measurement_result` is `fail`, not
`blocked`. Strategy has not inspected raw rows, provider implementation,
credentials, or a data CLI.

`confirmation_reserve_contract_v1.json` fixes a non-overlap rule that excludes
all construct-recovery and discovery evidence, including all 72 M6R episodes
and derivatives. It reveals no identity or outcome. It also binds the accepted
Data-owned #80 receipt and independent attestation. The reserve is
sealed, mechanically enforceable, nonempty, non-overlapping, unreleased, and
unseen by Strategy. Those public-safe bindings do not disclose any identity,
membership, count, row, or outcome and do not authorize release.

The accepted custody access-log route is exactly
`custody://data-owner/M6F-CONFIRMATION-RESERVE-V1/append-only-access-log-v1.jsonl`
with public chain-head commitment
`1a31f1b29fa4a234a68808da1e8a3bfc0ac18991566a31cc90b77fc18f0eef00`.
It is distinct from the Strategy contamination ledger: the custody log proves
reserve access control, while the contamination ledger records admitted
research-evidence interactions. The exact Strategy-visible #80 projection is
the receipt's 14 public keys: access-log locator and chain head, custodian,
eligibility and exclusion-set hashes, exclusion-registry plaintext/envelope
commitments, identity-manifest plaintext/envelope commitments, release fields,
reserve ID, receipt schema version, and seal time. These are commitments only;
their private payloads remain unavailable to Strategy.

That 14-key projection is conditional on `closed_accepted`. The `open` and
`closed_failed` reserve branches retain only the original eight-field
pre-acceptance visibility allowlist and require the custody URI, chain head,
accepted receipt schema, identity-manifest commitments, and exclusion-registry
commitments to be `null`. Thus an unavailable closure remains an honest
terminal route without inheriting contradictory positive sealed-custody proof.

The append-only contamination ledger records known P1, M6, M6R, and M6M
exposure; identifies pre-Issue source, method, and governance access as prior
scoping only; records pre-gate boundary planning separately; and binds the
post-gate evidence audit, exact source-authorization request, approved protocol,
source-author provenance, the two Data-owned dependency Issues, the accepted
closed-negative #79 receipt, and the accepted sealed-reserve #80 closure. The
M6R entry records only the already known frozen conclusion and exclusion
boundary. The 72 episodes were not inspected, relabeled, filtered, tuned
against, or used as confirmation.

## Package and verification

The manifest binds the evidence payloads plus `schema_v1.json` and
`verify.mjs` by exact path, byte length, and raw-byte SHA-256. It excludes
itself, this README, and the independent receipt to avoid circular hashes.
All structured artifacts use the canonical serialization required by Issue
#77.

Evidence-head verification:

```sh
node doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/verify.mjs --evidence-head
node doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/verify.mjs --evidence-head --negative
head_sha=$(jj log -r @ --no-graph -T 'commit_id')
git diff --check 5da299892514c7ca2d7bf1c77baba32f9df9753b "$head_sha"
```

Both named dependencies are closed and this terminal evidence head is now
frozen for a fresh independent review. No independent receipt belongs in this
evidence head. After a fresh reviewer validates the exact fixed head, the
implementer adds only
`independent-evidence-validation-receipt.md` in a child commit. Final-head
verification drops `--evidence-head`; a separate fresh external EV comment
must bind the exact final PR head and confirm the evidence-head-to-final-head
diff contains only that receipt. The receipt must bind the immutable external
review comment locator and body SHA-256, attest a fresh non-implementer reviewer,
list the exact verification suite, and contain no contradictory or extra prose.

## Public-safety and scope attestation

This work inspected only the committed governance, source, method, and gap
evidence listed above. It did not inspect raw market or option rows, the M6R
episode payloads, provider implementation, credentials, or `quant_data/`, and
it did not execute a data CLI. The diff contains no data or provider change.
It introduces no experiment, backtest, outcome or EV computation, parameter,
candidate implementation, production policy, or M7 work.

The public-boundary scan rejects established private/local roots, generic
structural absolute POSIX file and directory paths with arbitrary legal
filename characters at ordinary public-text boundaries,
path-line and Markdown-delimited locators, Windows drive paths, forward-slash
and backslash UNC paths, local file-URI locators, common tabular data-file
suffixes, and raw contract identifiers across the complete package, including
this README and verifier.
For the generic path-value rule only, an auditable JavaScript lexer masks actual
regex-literal tokens in verifier source. It leaves strings, template literals,
and comments unmasked. Every other raw-source guard continues scanning the
unmodified verifier bytes.
It preserves public web URLs and the accepted custody URI. Its negative suite
mutates the full README/package view for every boundary class, including the
independent review's exact synthetic private licensed-data locator, ordinary
prose and start-of-line generic POSIX paths, flag-like basenames, trailing
directories, path-line and Markdown forms, and both UNC separators. It requires
rejection through the same scan used by normal verification. The five latest
review paths are also injected into verifier strings, templates, and comments;
the two forward-slash UNC probes are additionally injected into block comments;
real regex literals remain accepted.

## Current PI packet

- Terminal state: **`source_fidelity_measurement_failure`**.
- Closed source dependency: `M6F-SOURCE-AUTH-01`, bound to the exact request,
  approved protocol body, canonical provenance receipt, and UTC timestamps.
- Source state: nine nodes `source_authorized`; daily chart `source_pinned`.
- Closed-negative dependency: `M6F-DATA-CAPABILITY-01` / Issue #79; its accepted
  Data-owner receipt returns 0 pass and 10 fail, so all ten measurement fields
  and the aggregate are `fail`.
- Closed-accepted dependency: `M6F-CONFIRMATION-RESERVE-01` / Issue #80; the
  exact merged receipt, manifest, independent attestation and verifier are
  hash-bound, and the reserve is sealed and mechanically enforceable.
- Open dependency set: empty.
- Terminal precedence: all named dependencies are closed; accepted #79
  measurement failure takes precedence over the accepted #80 reserve route and
  freezes `source_fidelity_measurement_failure`.
- Downstream decision: **PI may not open a separate preregistration-design
  Issue from this state**. Experiment and M7 remain unauthorized.
