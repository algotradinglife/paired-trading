# PA / Feitian Phase 1 hypothesis registry v2 freeze

Issue: #49

Freeze time: `2026-07-30T13:37:34Z`

Decision: **freeze SR-01 as `P1-EXP-002`, an underlying-only six-family
historical experiment; keep outcome access and #51 blocked**

## Selected hypothesis

`P1-EXP-002` tests one derived, non-authentic definition:

> A completed daily strict-prior-20 breakout whose direction agrees with
> causal EMA5 versus EMA20 alignment on D, W, 60-minute, and 15-minute views
> has positive five-completed-daily-bar signal-signed underlying close return.

The registry selects no family. It preserves the audited order and roles:

| Family | Role | Primary weight |
| --- | --- | ---: |
| SHFE.au | continuity candidate | 1/6 |
| SHFE.ag | continuity candidate | 1/6 |
| CZCE.TA | mainstream candidate | 1/6 |
| CZCE.MA | mainstream candidate | 1/6 |
| SHFE.cu | non-CZCE control | 1/6 |
| DCE.i | non-CZCE control | 1/6 |

The within-family primary mean gives equal weight to up and down events.
Therefore all 12 family-direction cells must pass the frozen sample gate.
Thin downside coverage produces `insufficient_sample`; it does not authorize
dropping a direction, choosing another family, or weakening SR-01.

## Why this candidate

The #48 audit establishes underlying OHLCV/OI interface presence at every
required cadence for all six families. The accepted #53 packet supplies
balanced outcome-free swing views and confirms that excursion percentiles are
not interchangeable with a structural event definition. The #52 review then
identified SR-01 as the only definition-mature candidate.

SR-02 is not reused: its swing-line directional family remains protected by
the negative M6-EXP-013 gate. SR-03 remains excluded because its B boundaries,
DD-line anchors, tolerances, confirmation, and invalidation are discretionary.

The choice is based on data capability and strategy definition, not historical
profitability. No outcome, option path, activity rate, or family comparison was
used to select it.

## Frozen event

At each exact 15:00 Asia/Shanghai decision close:

1. Start history at `2021-06-01T00:00:00+08:00` with no incumbent contract.
   Rows before that boundary are forbidden. Initialize EMA5 and EMA20, per
   selected contract and level, to the first finite completed close, then use
   the frozen `adjust=false`, `alpha=2/(span+1)` recurrence.
2. Enumerate only the six frozen family universes. A candidate is eligible
   when its unique prior-session row is causally available, timestamp-valid,
   duplicate-free, OHLC-coherent, and has finite nonnegative OI and volume.
   If every eligible candidate has strictly positive OI, choose maximum OI;
   otherwise choose maximum strictly positive volume. Missing/zero OI removes
   a candidate from OI leadership but does not disable the volume fallback.
   Resolve ties by bytewise contract id. Require three consecutive wins;
   changes, invalid rows, or missing sessions reset the streak. An incumbent
   expires on an invalid or missing next causal row; no forced roll is used.
   Make a roll effective on the next session after the third confirmation.
3. Truncate source rows to the decision timestamp before session mapping or
   aggregation.
4. Build D, W, 60-minute, and 15-minute views using the frozen M6 aggregation
   rules. W is the ISO year/week of causal D bars and includes the partial
   week visible at decision time.
   Each level uses all causally valid contract-local completed bars from the
   history boundary, whether or not that contract is selected at the bar time.
   Each contract retains its own state while rolled away and resumes it when
   selected again; bars are never spliced across contracts.
5. Emit `up` only when the completed D close is strictly above the highs of
   the 20 prior completed D bars and EMA5 is above EMA20 on all four views.
6. Emit `down` only for the symmetric strict-prior-20 low break and EMA5 below
   EMA20 on all four views.
7. Emit `abstain` for every other case, including exact-close absence,
   inadequate history, OHLC failure, roll ambiguity, missing binding, or
   disagreement on any view.

The selected contract remains fixed through the fifth subsequent completed
daily close. The estimand is conditional on a finite strictly positive
decision close and same-contract T+5 close. A missing, nonfinite, or
non-positive close excludes the event; the evaluator may not roll, shorten,
fill, or substitute the horizon.

## Frozen evaluation

| Stage | Decision dates | Outcome cutoff |
| --- | --- | --- |
| Training | 2021-11-01 through 2023-06-30 | 2023-07-07 |
| Validation | 2023-07-08 through 2024-12-31 | 2025-01-10 |
| Single-use holdout | 2025-01-11 through 2026-04-30 | 2026-05-15 |

Each stage requires at least 60 events, 20 distinct decision dates, and five
events in every family-direction cell. One decision date may contribute at
most 20% of the effective events: sealed causal events remaining after the
currently unlocked stage applies the same-contract fifth-close availability
rule. That availability rule does not change causal event membership.
EX-03 attrition is measured against all causal membership rows by stage and
family-direction cell. More than 50% attrition at either stage or cell gate
is `insufficient_sample`, not a reason to reweight surviving events.

The primary estimand is the arithmetic mean of six equal-weight family means;
each family mean gives 0.5 weight to its up cell and 0.5 to its down cell. A
fixed five-date moving-block percentile bootstrap uses 2,000 valid replicates,
at most 20,000 attempts, and seed `49002`. It uses the frozen SplitMix64 v1
transition with 64-bit modular arithmetic, rejection sampling for unbiased
block-start indices, and one continuous stream across attempted blocks and
discarded replicates. For `N=10`, the first 12 indices must be
`8,1,0,3,9,3,2,6,9,2,9,4`.

Training, then validation, advances only when the sample and replicate gates
pass and the 95% interval lower bound is strictly positive. A non-positive
upper bound falsifies the hypothesis. A failed gate or an interval that
has lower bound less than or equal to zero and upper bound greater than zero
is inconclusive. Later stages remain sealed. The holdout is evaluated once
only after immutable training and validation manifests both record
advancement.

## Difference from P1-EXP-001

`P1-EXP-001` remains immutable and terminal `data_blocked`. It is a prospective
AU/AG option-IV-rank experiment requiring selected option legs, exact expiry,
causal IV history, and a 17-bar premium outcome.

`P1-EXP-002` is a new historical, six-family, underlying-only experiment. It
forbids option premium, expiry, delta, IV, bid/ask, PnL, and execution inputs
and uses one same-contract five-bar underlying outcome. The new experiment has
its own registry version, experiment id, canonical design hash, and freeze
lock.

## Data and implementation gate

This freeze does not authorize event materialization or outcome access.
Issue #50 must first deliver a reviewed and merged historical-replay allow or
deny surface. A formal run must bind exact filtered input content or an
immutable acquisition version plus a filtered-row digest; an anonymous
included-file-set hash is insufficient.

The run must also bind causal timestamp and session semantics, pass future-row
invariance and OHLC/duplicate checks, and record unavailable option fields
without synthesis. Before any event materialization or forward-outcome read,
the first-access attestation must bind the protected merged commit containing
this exact registry and lock, prove that it is an ancestor of the builder
source commit, and bind the immutable all-stage causal-membership manifest.
The fifth-close availability exclusion is applied only after its stage
unlocks; later decision construction may read only rows truncated to its own
decision timestamp, and membership is never recomputed. Until both #49 and #50 are accepted
and merged, #51 remains blocked.

## Immutable bindings

| Binding | SHA-256 |
| --- | --- |
| Registry v2 bytes | `sha256:f2b77c11317c1f98fe6d4c95f47b2213243322f2f3d4ed6dd1ccbf92d972afa0` |
| Canonical P1-EXP-002 design | `sha256:4d3026e5eb398752c3c8f207cb5e21d1b2706e7fb68d40ddf31b99132486cb65` |
| Lock v2 bytes | `sha256:d7e36900efb91807a0960922c5cdbc5241ec4ca1988eb477ac6bc5a32c940718` |

The validator also verifies all ten source files named by the registry. A
coordinated rewrite of the registry and lock still fails because both anchors
are compiled into the version-specific validator.

## Reproduce

```sh
PYTHONPATH=src python3 \
  src/scripts/validate_pa_feitian_hypothesis_registry_v2.py

PYTHONPATH=src python3 -m pytest \
  src/tests/test_pa_feitian_hypothesis_registry.py \
  src/tests/test_pa_feitian_hypothesis_registry_v2.py -q
```
