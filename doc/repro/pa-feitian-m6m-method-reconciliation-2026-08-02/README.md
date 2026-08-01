# Post-M6R PA/Feitian method reconciliation

Issue: [#73](https://github.com/algotradinglife/paired-trading/issues/73)
Decision date: 2026-08-02
Terminal handoff: **`method_reconciled_recommend_path`**

## Decision in one paragraph

Preserve every frozen P1, M6, and M6R result, but do not treat those results as
a test of the source-defined Feitian decision chain. The next permitted
research order is: (1) a source-fidelity evidence-recovery path, ending before
experiment design; then, only if PI explicitly declines or cannot satisfy that
path, (2) a separately named bare-K exhaustion/discovery path. Neither path is
authorized by this memo. Any experiment requires a new Issue, preregistration,
and confirmation evidence independent of the 72 M6R episodes. M7 remains
`not_authorized`.

## Exact evidence base and citation discipline

All historical claims below are pinned to immutable revisions. This memo does
not reinterpret an old artifact in place or change its wording.

| Repository / revision | File and exact location | Fact used here |
| --- | --- | --- |
| paired-trading `cb08cfb7f3f5d0082ff13343bcbb324f25a96733` | [`STATUS.md` lines 9–16](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/STATUS.md#L9-L16), [lines 30–49](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/STATUS.md#L30-L49) | P1 stopped before outcome access; M6R ended `no_candidate`; its 72 episodes remain discovery-only; M7 is not authorized. |
| paired-trading `cb08cfb7f3f5d0082ff13343bcbb324f25a96733` | [P1 decision lines 1–36](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/doc/repro/pa-feitian-phase1-p1-exp-002-decision-2026-07-31/README.md#L1-L36) | `stop_p1_exp_002` was a pre-outcome source-quality decision; it did not consume strategy outcomes. |
| paired-trading `cb08cfb7f3f5d0082ff13343bcbb324f25a96733` | [source ledger lines 1–12](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/doc/repro/pa-feitian-m6-operationalized-rule-v0/source_assumption_ledger_v0.json#L1-L12), [lines 69–140](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/doc/repro/pa-feitian-m6-operationalized-rule-v0/source_assumption_ledger_v0.json#L69-L140) | M6 is `operationalized_hypothesis_not_authentic`: generic OHLC, invented finite pivots/lines, omitted 1B/2B quality, and no market/option/premium claim. |
| paired-trading `cb08cfb7f3f5d0082ff13343bcbb324f25a96733` | [M6R synthesis lines 3–12](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/doc/repro/pa-feitian-m6r-reveal-comparison-synthesis-v1.md#L3-L12), [lines 44–62](https://github.com/algotradinglife/paired-trading/blob/cb08cfb7f3f5d0082ff13343bcbb324f25a96733/doc/repro/pa-feitian-m6r-reveal-comparison-synthesis-v1.md#L44-L62) | M6R is descriptive discovery, verdict `no_candidate`, and cannot distinguish persistent structure from transient movement. |
| trade-philosopher `715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a` | [decision-tree design lines 1–24](https://github.com/algotradinglife/trade-philosopher/blob/715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a/doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md#L1-L24), [lines 28–62](https://github.com/algotradinglife/trade-philosopher/blob/715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a/doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md#L28-L62), [lines 78–87](https://github.com/algotradinglife/trade-philosopher/blob/715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a/doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md#L78-L87), [lines 144–160](https://github.com/algotradinglife/trade-philosopher/blob/715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a/doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md#L144-L160) | The 2026-06-17 state is a first deterministic fidelity implementation of an oral, revisable option-chain account. Its phase-0 result is explicitly underpowered and ungated and cannot falsify the source-defined idea. |
| trade-philosopher `5802d0ff5d99819ad01ba9f3550b6a2d504f1e81` | [methodology lines 17–34](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L17-L34), [lines 46–76](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L46-L76), [lines 82–116](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L82-L116), [lines 120–139](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L120-L139), [lines 151–163](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L151-L163) | The method moves from tree/output imitation toward an auditable DAG, treats poor results first as possible fidelity/representation defects, requires true OOS/generalization pressure, and separates backtest-as-falsifier/microscope from optimizer. |
| trade-philosopher `7691c31dceb0bb37a77d9fd8c98dc0746dc1361d` | [annotation v2 lines 12–23](https://github.com/algotradinglife/trade-philosopher/blob/7691c31dceb0bb37a77d9fd8c98dc0746dc1361d/doc/pa-replication/high-quality-annotation-dataset-v2.md#L12-L23), [lines 25–70](https://github.com/algotradinglife/trade-philosopher/blob/7691c31dceb0bb37a77d9fd8c98dc0746dc1361d/doc/pa-replication/high-quality-annotation-dataset-v2.md#L25-L70), [lines 72–106](https://github.com/algotradinglife/trade-philosopher/blob/7691c31dceb0bb37a77d9fd8c98dc0746dc1361d/doc/pa-replication/high-quality-annotation-dataset-v2.md#L72-L106), [lines 136–161](https://github.com/algotradinglife/trade-philosopher/blob/7691c31dceb0bb37a77d9fd8c98dc0746dc1361d/doc/pa-replication/high-quality-annotation-dataset-v2.md#L136-L161) | The later data method makes event indexing non-normative, separates discovery from confirmation and event/perception/decision/outcome planes, and requires new unseen evidence after hypothesis induction. |

## Epistemic change map

The changes below are prospective method changes, not retroactive corrections
to paired-trading history.

### Required source transitions

- **Transition A — phase-0 scope:** At `trade-philosopher@715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a`,
  [lines 144–160](https://github.com/algotradinglife/trade-philosopher/blob/715ffec5b6549c5cc9ff1d0d39dc2224a62bbe4a/doc/pa-replication/feitian-option-decision-tree-design-2026-06-17.md#L144-L160)
  label phase 0 inconclusive, underpowered, and ungated. It omits direction,
  2B-over-1B, and holistic exhaustion quality, so it cannot falsify the
  source-defined idea.
- **Transition B — representation and claim:** At
  `trade-philosopher@5802d0ff5d99819ad01ba9f3550b6a2d504f1e81`,
  [lines 17–34](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L17-L34)
  separate fidelity, Xiao-plus, and essence, while
  [lines 82–91](https://github.com/algotradinglife/trade-philosopher/blob/5802d0ff5d99819ad01ba9f3550b6a2d504f1e81/doc/self-evolving-trader-methodology-2026-06-28.md#L82-L91)
  require poor results to trigger fidelity/representation diagnosis before
  attributing them to the trader or source idea.
- **Transition C — evidence routing:** At
  `trade-philosopher@7691c31dceb0bb37a77d9fd8c98dc0746dc1361d`,
  [lines 25–70](https://github.com/algotradinglife/trade-philosopher/blob/7691c31dceb0bb37a77d9fd8c98dc0746dc1361d/doc/pa-replication/high-quality-annotation-dataset-v2.md#L25-L70)
  separate discovery from confirmation and event, perception, decision, and
  outcome planes. Evidence used to induce a hypothesis cannot confirm it.

| Method dimension | `715ffec` state | Change at `5802d0f` | Further constraint at `7691c31` | Consequence now |
| --- | --- | --- | --- | --- |
| Research object | A first deterministic tree intended to reproduce an oral Feitian option process; fidelity is the stated north star. | The object becomes a causal, inspectable DAG with hard gates and holistic soft judgments; “Xiao plus” is explicitly distinct from authentic replication. | Event, perception, decision, outcome, and postmortem are separate planes. | Name the construct before testing it; proxy output cannot inherit source authenticity. |
| Meaning of poor results | Gate results are used to calibrate fidelity and locate over-filtering. | Poor win-rate/result is first a possible representation or fidelity alarm, not permission to attribute failure to the trader. | A posterior event is not a decision-time setup; measurement and availability must be auditable. | A negative proxy result cuts the proxy claim unless source fidelity and measurement validity were already established. |
| Optimization role | Calibration and gate diagnostics are embedded in the first implementation. | Fixed-history EV optimization is rejected; walk-forward, causal readability, parsimony, and honest costs protect generalization. | Thresholds, offsets, splits, and availability are frozen before evaluation. | No threshold or protocol may be selected in this memo; a future Issue must preregister them. |
| Discovery versus proof | Not yet a formal two-channel data protocol. | Backtest may act as falsifier or microscope, but not as an optimizer. | Discovery may induce hypotheses; confirmation mechanically tests a frozen hypothesis on unseen validation/test/OOS/audit evidence. Reuse of inducing data as confirmation is forbidden. | The 72 M6R episodes remain discovery-only forever for any hypothesis they helped induce. |
| Fidelity evidence | Oral/revisable source and deterministic approximations coexist. | Consensus establishes reproducibility, not truth; true fidelity needs stronger external anchoring and OOS behavior. | Only original trader labels are Trader GT; model consensus remains Silver absent expert adjudication. | A source-fidelity path must recover source-authorized semantics or explicitly terminate as unrecoverable. |

## Three constructs that must not be collapsed

| Construct | Inputs | Decision plane | Omitted source semantics | Intended claim | Known validity limit |
| --- | --- | --- | --- | --- | --- |
| Source-defined Feitian decision chain | Underlying/regime direction; option daily K; option selection context; DD low-line and descending-high-line geometry; 1B/2B and holistic quality; structural invalidation; premium-space exits/runner/roll | A staged option decision: direction → option timing/quality → entry path → invalidation → management | The source itself leaves exact holistic scoring, anchors, tolerances, and some chart conventions unresolved. | A source-fidelity model of the described Feitian process, if those semantics are independently recovered | The `715ffec` document is an oral, revisable first implementation, not Trader GT and not proof of profitability. |
| M6 operationalized bare-K proxy | Generic completed OHLC bars with deterministic local pivots, straight-line projections, bar-shape gate, and provisional mirror | Instrument-free structural classification | Option/contract selection, premium space, underlying direction, 1B/2B, holistic quality, original anchors/tolerances, execution and roll | An auditable operationalized hypothesis for a narrow bare-K surface | Explicitly `operationalized_hypothesis_not_authentic`; failure cannot falsify the authentic chain. |
| M6R discovery/induction object | 72 anonymous 40-bar bare-K windows; frozen blind context, turn, range, and bar-0 descriptors; later descriptive responses after reveal | Blind structural description followed by fixed descriptive comparison and candidate induction | Source identity, option plane, direction chain, quality semantics, entry/exit/roll, and any confirmation sample | Discover whether the frozen descriptor surface justifies a candidate for later independent validation | Frozen `no_candidate` under this surface; 72 episodes are selected discovery data and cannot confirm a derived claim. |

## Claim-status ledger

| Claim key | Frozen fact | Present interpretation | Inference allowed now | Open question |
| --- | --- | --- | --- | --- |
| `p1` | `stop_p1_exp_002` | The existing native-source snapshot cannot support its registered contract; stop occurred before outcome access. | A new source version would require a new reviewed lane. | Can provider/bar-end semantics and lossless row accounting ever be independently established? |
| `m6_proxy_status` | `operationalized_hypothesis_not_authentic` | M6 tested a deliberately incomplete generic bare-K proxy. | M6 evidence applies to that operationalization. | How much of its result is representation error versus absent relationship? |
| `m6r_frozen_artifact_verdict` | `no_candidate` | The frozen artifact and wording remain unchanged. | No candidate was selected under the declared descriptor/induction surface. | Would a different, independently justified measurement surface expose a reproducible construct? |
| `m6r_active_interpretation` | `no_candidate_under_current_measurement` | “No candidate” is not “no relationship exists” and not “authentic Feitian failed.” | The current bare-K descriptor surface is exhausted for candidate selection without post-hoc search. | Is another surface defensible before seeing new outcomes? |
| `method_state` | `method_revision_required` | Construct identity, measurement validity, and discovery/confirmation routing must precede another experiment. | PI may choose a successor research path after this memo and receipt are accepted. | Which target construct can satisfy its evidence-readiness gate? |
| `M7` | `not_authorized` | Neither this memo nor acceptance of Issue #73 opens M7. | None. | Only a later PI decision after separate preregistered evidence can revisit the gate. |

## Claim-level outcome vocabulary and decision rules

These outcomes are mutually distinguishable. “Pass” below means the label is
permitted at the stated claim level, not that a strategy is profitable.

| Outcome | Permitted meaning | Pass rule | Fail / non-pass rule | Prohibited inference |
| --- | --- | --- | --- | --- |
| Discovery | A reproducible observation, ambiguity, or candidate hypothesis generated from declared discovery evidence | Inputs and availability are causal; selection and transformations are recorded; result is labeled descriptive or induced; provenance permits replay | If inputs leak future data or selection cannot be reconstructed, it is measurement failure, not discovery | “Supported,” “validated,” “falsified,” or deployable |
| Confirmation | A frozen claim received a mechanical preregistered test on evidence untouched by induction | Target construct, rule, sample, metrics, and decision rule were frozen before outcome access; validation/test/OOS/audit evidence is independent; all gates pass | A valid test meeting its rejection rule is falsification; an underpowered or unavailable test is insufficient data; a broken representation is measurement failure | Reusing M6R’s 72 episodes, tuning after outcomes, or promoting discovery evidence |
| Falsification | An exact, previously frozen claim conflicts with adequate independent evidence under a valid measurement | Confirmation protocol is valid and its preregistered rejection condition is met | If the tested representation is not the target construct, only that representation may be rejected; broken measurement cannot falsify the target | “M6 proxy failed, therefore authentic Feitian failed” |
| Measurement failure | The pipeline cannot validly identify or observe its stated construct | A provenance, availability, representation, label-plane, or outcome-measurement gate fails before the target claim can be evaluated | Repair requires a new version and, where outcome knowledge could influence it, a fresh confirmation sample | Treating invalid measurement as negative strategy evidence |
| Insufficient data | Measurement is valid, but declared coverage, precision, sample, or power gates are unmet | Valid rows are accounted for and the preregistered sufficiency gate fails without selective removal | If measurement itself is invalid, use measurement failure; if an adequate valid test rejects, use falsification | Treating “not enough evidence” as support or rejection |

## Gate diagnosis: which layer did current evidence cut?

| Statement | Epistemic class | Assessment |
| --- | --- | --- |
| P1 stopped before outcome access because source semantics and row-quality gates failed. | Frozen evidence | This is a source-contract measurement failure for P1-EXP-002, not an outcome result. |
| M6 intentionally removed option, premium, 1B/2B, holistic-quality, and original-anchor semantics. | Frozen evidence | The tested representation is materially narrower than the source-defined chain. |
| M6R selected no candidate from its declared bare-K descriptors, and all support-floor categories had mixed horizon-20 signs. | Frozen evidence | The declared induction surface did not justify freezing a candidate. |
| Therefore authentic Feitian has failed. | Invalid inference | The antecedents never measured the full source-defined decision chain and provide no confirmation sample. |
| The current gate may be cutting the representation/measurement layer rather than the source idea. | Supported inference | This follows from the documented proxy omissions and later method’s rule that construct and measurement validity precede attribution. It is not evidence that authentic Feitian works. |
| A faithful source chain can be recovered and will work. | Open question | No Trader GT, complete source semantics, or independent confirmation currently establishes either clause. |

The corrective action is not to weaken the frozen gate. It is to move the next
decision upstream: first decide which construct is sufficiently specified to
deserve a preregistered test.

## Successor-path comparison

The criteria are identical for both paths so that path choice is not an
outcome-driven preference.

| Criterion | Path A — source-fidelity Feitian decision chain | Path B — bare-K exhaustion/discovery |
| --- | --- | --- |
| Target construct | The option-based direction/timing/quality/management chain described at `715ffec`, explicitly versioned as source-fidelity rather than authentic until stronger ground truth exists | A generic, non-authentic bare-K perception/structure research object |
| Evidence required before preregistration | Source-authorized chart and option-contract definition; causal underlying-direction inputs; recoverable DD/descending-line anchor conventions; 1B/2B and holistic-quality labels or authorized specification; premium/roll measurement semantics; provenance and availability audit; explicit unresolved fields and abstention rules | A distinct causal descriptor/perception schema justified without mining outcomes; natural-distribution and negative coverage; reproducible annotations; a new discovery corpus or source that does not convert the original 72 episodes into confirmation; explicit non-authentic naming |
| Contamination / leakage risk | Retrofitting source semantics to explain known M6/M6R outcomes; treating LLM consensus as Trader GT; choosing only recoverable nodes that look favorable | Re-mining the 72 episodes, outcome-derived descriptor/threshold search, episode overlap across discovery and later confirmation, or silently renaming an M6R pattern |
| Principal failure mode | “Fidelity” remains an invented proxy because source semantics or premium data cannot be independently recovered | Endless descriptive search produces post-hoc stories with no low-free-degree causal candidate or independent sample |
| Stop condition | Stop/hold this path if PI cannot obtain source-authorized semantics sufficient to distinguish perception and decision planes, or causal option/premium measurement cannot pass provenance gates | Stop/hold this path if no pre-outcome rationale supports a new measurement surface, no fresh discovery evidence can be isolated, or no independent future confirmation pool can be reserved |
| What success before experiment means | A reviewable construct/measurement contract exists; it does **not** mean the chain works | A reviewable discovery contract and uncontaminated future confirmation route exist; it does **not** mean a candidate exists |

## Recommended order and PI decision packet

### Recommendation

1. **Attempt Path A, source-fidelity evidence recovery, first.** The method
   revision specifically warns against attributing proxy failure to the source
   idea. Construct identity and measurement validity are therefore the first
   unresolved gates.
2. **If Path A’s evidence floor cannot be met, record that terminally.** Do not
   fill source gaps with calibrated thresholds.
3. **Only then consider Path B as a separately named non-authentic research
   line.** It must use a new discovery surface and reserve independent evidence;
   M6R’s 72 episodes may inform provenance and counterexamples but may never
   become confirmation.

Path A would require a new versioned source-fidelity ledger; revisions 580 and
769 are method inputs and do not retroactively add source-supported behavior to
the frozen M6 ledger. Path B is generic non-authentic bare-K discovery, not
authentic Feitian or “Xiao plus.” If PI chooses a Xiao-plus lineage instead,
that construct requires its own causal claim and evidence contract in a
separate Issue.

### Minimum five-part PI decision packet

| PI decision | Recommendation from this memo |
| --- | --- |
| Recommended target construct | Choose the **source-fidelity Feitian decision chain** for an evidence-recovery lane. It remains a source-fidelity construct, not an authenticity or performance claim. |
| Claim level permitted for the next Issue | Permit **measurement/construct readiness and discovery only**. Confirmation, falsification of the source idea, strategy support, and M7 remain out of scope. |
| Admissible evidence source and contamination boundary | Admit newly sourced or source-authorized definitions/labels plus causally available underlying, option, premium, and provenance evidence. Maintain an append-only contamination ledger. Exclude the 72 M6R episodes from confirmation of any induced claim and do not tune source semantics to known M6/M6R outcomes. |
| Stopping/falsification meaning at that claim level | Stop the evidence-recovery path as **measurement failure / unrecoverable construct** if source semantics or causal premium measurement cannot pass their gates. That does not falsify authentic Feitian. A later exact operationalization may be falsified only by its own independent preregistered confirmation rule. |
| Whether to open a separate preregistered experiment Issue | **No experiment Issue yet.** If PI accepts this memo, first open a separate source-fidelity evidence-recovery contract. Open a preregistered experiment Issue only after that contract establishes a reviewable construct, uncontaminated evidence source, and independent confirmation reserve. |

If PI rejects the recommended construct or its evidence source is infeasible,
PI may instead authorize a separate non-authentic bare-K discovery contract
using the same five decisions. This memo freezes no parameters, thresholds,
instruments, samples, horizons, or experiment protocol, and M7 remains not
authorized.

## Independent evidence validation

The independent receipt is attached as
[`independent-evidence-validation-receipt.md`](independent-evidence-validation-receipt.md).
Any material disagreement must be resolved in that receipt or escalated to PI
before this memo can be accepted.

## Final boundary and handoff

**`method_reconciled_recommend_path`**

Rationale: at least one defensible research route exists at the method level,
but source-fidelity evidence recovery should precede any new proxy experiment.
This memo authorizes neither route, no experiment, no backtest, no parameter or
protocol, no M7 work, and no closure of the PA/Feitian line. PI can use the
decision packet above to decide whether to open a separate evidence-recovery or
preregistration Issue.
