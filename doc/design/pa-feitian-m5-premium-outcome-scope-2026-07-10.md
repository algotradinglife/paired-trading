# PA / Feitian M5 Premium-space Outcome Harness Scope

Date: 2026-07-10

Repository: `algotradinglife/paired-trading`

Branch: `coordination/pa-feitian-m5-scope`

Status: M5 scope baseline

## 1. Milestone Definition

M5 builds a reproducible, no-lookahead outcome harness for PA / Feitian
historical decisions using actual option-premium price paths.

In one sentence:

> Fix the decision time, selected option contract, and exit policy first; then
> follow only subsequent option prices to measure what happened in premium
> space, while keeping underlying-R context strictly separate.

M5 answers:

> If this historical PA / Feitian decision had followed its predeclared option
> contract and outcome policy, what happened on the observable premium path?

M5 does not answer which setup, parameter combination, or policy should be
selected for production. Comparative strategy evaluation and filtering belong
to M6.

## 2. Relationship To M4

M4b established the real artifact path:

```text
current data interfaces
  -> real score_today artifact
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1
  -> dashboard fixtures
```

M5 extends that path with a retrospective outcome lane:

```text
M4 score_today / snapshot v1 / decision intent
  + decision-time option contract selection
  + OptionStore premium OHLC after the decision
  + fixed outcome policy
  -> premium-space outcome harness
  -> pa_feitian_premium_outcome_v1 sidecar
  -> manifest hashes and provenance
  -> read-only dashboard outcome review
```

The outcome is a separate sidecar artifact. It must not add posterior fields to
`pa_feitian_snapshot_v1` or `pa_feitian_decision_intent_v1`.

## 3. Inputs

The harness may consume only explicit, versioned inputs:

- the M4 score_today artifact;
- `pa_feitian_snapshot_v1`;
- `pa_feitian_decision_intent_v1`;
- the run manifest tying those artifacts together;
- the option contract selected from information available at decision time;
- OptionStore premium OHLC observations after the decision timestamp;
- an explicit, versioned outcome policy and cost model.

Every input path, artifact hash, source commit, CLI argument, policy parameter,
and data-access classification must be recorded in the run manifest or outcome
artifact provenance.

## 4. Outcome Artifact

M5 should introduce a separate contract, provisionally named
`pa_feitian_premium_outcome_v1`.

Each outcome record must preserve traceability to the source decision and
include at least:

- source signal, decision-intent, and contract identifiers;
- decision timestamp and first eligible entry timestamp;
- call/put direction, exchange, product, contract, strike, expiry, and DTE;
- outcome policy identifier and complete policy parameters;
- entry and exit timestamps and premium fills;
- stop, target, time-exit, data-gap, or unresolved exit reason;
- premium return and premium multiple;
- `premium_r`, using declared premium risk after costs as its denominator;
- premium-space MFE and MAE;
- underlying return or `underlying_r` only as separately labelled context;
- transaction-cost and slippage assumptions;
- data quality, bar granularity, ambiguity, and evaluation status;
- input and output hashes.

Recommended evaluation statuses are:

- `observed`: sufficient real premium data and an unambiguous result;
- `ambiguous`: available bars cannot establish event ordering;
- `data_blocked`: required option data is unavailable;
- `not_evaluable`: the decision or contract does not meet declared harness
  preconditions.

The exact enum names may change during contract implementation, but missing or
ambiguous evidence must never be represented as an observed result.

## 5. Premium-space Semantics

`premium_r` and `underlying_r` represent different risk geometries and must not
share a denominator.

For a long option, the premium risk unit should be derived from the declared
entry premium, stop premium, and execution costs. The contract must preserve
the raw values needed to reproduce the calculation instead of storing only the
final R multiple.

At minimum, the harness must support deterministic policy fixtures for:

- premium stop;
- one or more premium profit targets;
- maximum holding period;
- explicit slippage in option ticks;
- missing bars or early contract data termination;
- a stop and target touched within the same OHLC bar.

Policy support does not imply policy optimization. M5 measures declared
policies; M6 compares and filters them.

## 6. No-lookahead Rules

The following invariants are mandatory:

1. The decision timestamp precedes every outcome observation.
2. Contract selection uses only information available at or before the
   decision timestamp.
3. Entry is the first eligible tradable observation defined by the policy; it
   cannot be chosen after inspecting later prices.
4. Contract, strike, expiry, stop, targets, holding period, and cost assumptions
   are fixed before traversing the outcome path.
5. Future MFE, MAE, exit reason, labels, or returns cannot affect the source
   decision intent.
6. Outcome artifacts are posterior observations and can never change
   `decision_state`, `execution_allowed`, direction, or original reason codes.

Tests must fail if a posterior field is used by decision-time selection logic.

## 7. Data Granularity And Evidence Levels

Daily option OHLC is sufficient for an observation-only M5 harness, but it is
not sufficient to claim exact validation of Xiao-style few-tick stops.

With daily bars:

- same-bar stop/target ordering is unknown unless a conservative policy is
  explicitly declared;
- fills are policy assumptions rather than bid/ask evidence;
- gaps through a stop or target must follow a declared fill rule;
- results must record daily granularity and its limitations.

Exact few-tick execution validation requires intraday or tick option data,
bid/ask observations, exchange tick size, and executable event ordering. That
hardening may be added later without blocking the first observation-only M5
artifact, but daily evidence must not be labelled as exact tick-stop evidence.

Real OptionStore prices are the primary M5 evidence. Black-76 or other modeled
premiums may be emitted only as explicitly labelled simulation or comparison
records; they cannot be classified as observed real outcomes.

## 8. Frontend Boundary

The dashboard remains artifact-only. It may render:

- per-decision premium outcome status;
- contract, entry, stop, target, and exit details;
- premium return, premium R, MFE, and MAE;
- separately labelled underlying-R context;
- ambiguity and data-quality warnings;
- manifest provenance and hash status.

The frontend must not scan OptionStore, select contracts, calculate outcomes
from raw market data, or modify decision intent.

## 9. Non-goals

M5 explicitly excludes:

- live trading or order execution;
- automatic trade approval;
- position sizing, portfolio allocation, or capital deployment;
- persistent reviewer override storage;
- shadow/live monitoring;
- strategy ranking, parameter optimization, setup filtering, or production EV
  claims;
- using sparse M5 evidence to promote a setup to production;
- retrospective contract or parameter selection after seeing the result;
- treating model-derived premiums as real observations;
- claiming exact tick-level execution from daily OHLC;
- snapshot v2 or posterior mutation of snapshot/decision-intent contracts;
- frontend access to raw market stores.

Strategy evaluation and filtering are M6. The semi-automated decision console,
shadow monitoring, and controlled execution candidacy remain M7, M8, and M9.

## 10. Proposed Workstreams

1. `M5-CONTRACT-001`: define the premium outcome sidecar, schema validation,
   manifest reference, and compatibility tests.
2. `M5-STRAT-001`: implement the deterministic no-lookahead premium outcome
   harness and explicit data-quality classification.
3. `M5-DATA-001`: establish real OptionStore path coverage and committed golden
   cases for observed, blocked, and ambiguous outcomes.
4. `M5-FE-001`: add artifact-only premium outcome review to the dashboard.
5. `M5-INTEG-001`: integrate contract, harness, real artifacts, manifest, and
   frontend smoke path.
6. `M5-FINAL-001`: prepare one final review packet for ChatGPT acceptance after
   integration is complete.

Intermediate contract, strategy, data, and frontend reviews are owned by the
Codex coordination process. ChatGPT participates only in final M5 acceptance.

## 11. Acceptance Criteria

M5 is complete when all of the following hold:

- a versioned premium outcome sidecar schema and model exist;
- existing snapshot v1 and decision-intent v1 contracts remain unchanged;
- the manifest references and hash-validates the outcome artifact;
- a deterministic harness reproduces identical artifacts from identical
  inputs and parameters;
- golden fixtures cover stop, target, time exit, data gap, same-bar ambiguity,
  costs, and no-lookahead failures;
- at least one M4b real historical decision is evaluated from real OptionStore
  premium observations, or is honestly classified as blocked with reproducible
  evidence;
- premium R and underlying R remain structurally and visibly separate;
- model-derived and observed outcomes cannot be confused;
- the dashboard renders outcome, provenance, and data-quality state from copied
  artifacts only;
- end-to-end smoke proves:

  ```text
  M4 decision artifacts
    -> premium outcome artifact
    -> manifest
    -> copied dashboard artifacts
    -> renderDashboard(...)
  ```

- tests, lint, schema validation, artifact hash verification, frontend smoke,
  and `git diff --check` pass;
- the integrated M5 packet receives final ChatGPT acceptance.

## 12. M5 / M6 Gate

M5 may report descriptive per-event outcomes and prove that the measurement
path is valid. It must not select winning parameter cells or make production
claims.

M6 begins only after M5 has established trustworthy outcome records. M6 will
then aggregate and compare trace nodes, IV gates, option legs, and exit policies
using EV, win rate, uncertainty, sample size, and failure modes.

