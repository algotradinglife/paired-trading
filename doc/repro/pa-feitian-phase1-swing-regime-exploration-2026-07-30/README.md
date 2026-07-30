# Phase 1 historical swing-regime exploration

Issue: #52

Research date: 2026-07-30

Decision: **advance SR-01 to #49 as the sole definition-mature candidate;
do not freeze or evaluate `P1-EXP-002` in this issue**

## Scope and evidence boundary

This note returns Phase 1 to exploratory research after `P1-EXP-001` stopped
as `data_blocked`. It asks which PA / Feitian-like descriptions are precise
enough to consider in a later registry revision. It does not select an
instrument, inspect strategy outcomes, mutate the hypothesis registry, or
authorize #51.

The observations below come only from committed, public-safe artifacts:

- the six-family capability and interface audit from #43 / PR #48;
- the accepted six-family exploratory swing views from #53 / PR #55;
- the causal AU/AG underlying corpus with completed D/W/60-minute/15-minute
  summaries;
- the outcome-free daily bare-K trace and causal swing-line atlases; and
- the negative M6-EXP-013 premium-K response gate.

The source artifacts contain current-vintage retrospective data. They do not
prove what a vendor exposed at each historical decision. This pass did not
refresh market data, read strategy outcomes, or inspect the caller-provided
runtime interface directly. Counts are structural coverage, not PnL, win rate,
EV, instrument ranking, or evidence of future value.

## What is actually observable

PR #48 established underlying and option-bar interface presence for the fixed
six-family universe at daily, hourly, 15-minute, and 5-minute cadence. All
interfaces are stale at the 2026-07-30 audit date. The historical research
status is `usable_with_limitations`, while causal operational use remains
blocked.

AU and AG have a committed, hash-bound causal historical corpus containing 333
AU and 337 AG decision records from 2025-01-02 through 2026-06-08 and four
completed-bar views per record. PR #55 adds a separate accepted daily
exploration packet for every family. It freezes anonymous contracts before
outcome access, partitions them into non-overlapping 20-observation windows,
and publishes normalized OHLC paths without stitching contracts or exposing
raw values.

### Accepted six-family exploration

The fixed-order table separates every complete underlying window from the
clean windows eligible for representative selection. `Overlay views` counts
the quiet, typical, and volatile representatives with a complete comparable
20-date premium-path distribution. Every overlay remains quality-invalid.

| Family | Complete windows | Clean windows | Representative eligible | Eligible share of clean | Overlay views available |
| --- | ---: | ---: | ---: | ---: | ---: |
| SHFE.au | 405 | 405 | 186 | 45.9259% | 3/3 |
| SHFE.ag | 651 | 651 | 319 | 49.0015% | 3/3 |
| CZCE.TA | 379 | 351 | 26 | 7.4074% | 2/3 |
| CZCE.MA | 379 | 345 | 30 | 8.6957% | 2/3 |
| SHFE.cu | 750 | 750 | 324 | 43.2000% | 3/3 |
| DCE.i | 662 | 662 | 109 | 16.4653% | 3/3 |

The artifact contains 3,226 complete underlying windows, 994
representative-eligible clean windows, and 18 inspectable normalized paths.
It improves the exploration in four ways:

1. Every family exhibits clean daily swing windows, so none may be discarded
   merely because the earlier AU/AG causal corpus omitted it.
2. `Quiet`, `typical`, and `volatile` are within-family excursion percentiles,
   not shared structural definitions. A TA quiet window can have more total
   excursion than an AU typical window.
3. Similar excursion can describe different shapes. The accepted typical
   views include both directional paths and choppy round trips; the volatile
   views likewise include directional moves and paths that finish near their
   starting level. Excursion alone is therefore not an event definition.
4. All 18 option overlays are quality-invalid, and TA-typical plus MA-quiet
   have no complete comparable path distribution. These paths are inspection
   aids, not premium evidence or a basis for family selection.

PR #55 is daily and contract-local. It deliberately does not construct the
roll-bound D/W/60-minute/15-minute event state required by SR-01. That is an
implementation and evidence gate for #49 and later work, not a reason to add
discretion to the SR-01 definition.

### AU/AG completed-bar regime sketches

The table is in fixed continuity-reference order. `Aligned breakout` means a
daily strict-prior-20 breakout whose direction agrees with the frozen causal
EMA condition on D, W, 60-minute, and 15-minute views: EMA5 > EMA20 for an
upward alignment and EMA5 < EMA20 for a downward alignment. `Mixed EMA` means
the four views do not all carry the same alignment. `Expanded daily range`
means the current daily high-low range is at least 1.5 times the mean
high-low range of the 20 completed daily bars strictly before it.

| Family | Records | Daily strict-prior-20 breakouts | Direction-aligned on all four views | Mixed EMA alignment | Expanded daily range |
| --- | ---: | ---: | ---: | ---: | ---: |
| SHFE.au | 333 | 56 (50 up, 6 down) | 50 (48 up, 2 down) | 198 | 61 |
| SHFE.ag | 337 | 48 (44 up, 4 down) | 40 (40 up, 0 down) | 213 | 60 |

These are regime descriptions, not performance comparisons. Three
observations matter:

1. Mixed multi-timeframe alignment is the ordinary case in this historical
   slice: 198/333 AU records and 213/337 AG records. A rule that says only
   "trend aligned" leaves a large discretionary middle.
2. Timeframe choice changes the event. Of records with any 60-minute or
   15-minute strict-prior-20 breakout, 21/29 AU and 27/33 AG records still
   have no daily breakout. An unspecified "breakout" is therefore not a
   reproducible definition.
3. The fully aligned downside cell is extremely thin in the continuity
   corpus: two AU records and zero AG records. That is a coverage warning,
   not evidence against downside structures and not permission to search a
   different family after seeing outcomes.

### Bare-K vocabulary and swing-line ambiguity

The outcome-free bare-K atlas produced 54 distinct training trace classes
from 122 windows and 132 distinct holdout classes from 449 windows. Only 13
training classes were shared between AU and AG. A bar-shape vocabulary can
describe many charts, but the growth in distinct classes shows why an
unbounded combination of direction, body location, range, turn, and
three-bar shape is not yet a hypothesis.

The causal two-anchor swing-line proxy is more precise, but ambiguity remains
material:

| Split | Total labels | Abstain | Conflict | Abstain or conflict |
| --- | ---: | ---: | ---: | ---: |
| Training | 434 | 194 | 46 | 240 (55.3%) |
| Holdout | 449 | 169 | 103 | 272 (60.6%) |

The conflict share rises from 10.6% to 22.9% in holdout structural coverage.
That is a direct counterexample to treating every projected touch or break as
one unambiguous side. It is not an outcome result.

M6-EXP-013 then tested its frozen six-label direction mapping and fixed 1, 3,
and 5-bar premium-K response horizons. No training cell passed every gate.
Its empty candidate set remains rejected. This exploration must not revive it
by changing mappings, thresholds, horizons, or corpus.

## Candidate definitions

No authentic Feitian definition is recoverable from the committed evidence.
The three descriptions below deliberately include non-candidates so #49 can
freeze, revise, or stop without pretending every chart idea is ready.

### SR-01 — completed daily breakout with four-view agreement

Status: **derived / proxy; definition-mature for #49, empirically unevaluated**

At the completed 15:00 Asia/Shanghai decision snapshot:

1. D, W, 60-minute, and 15-minute bars are built from timestamp-truncated
   source rows under a fixed causal roll policy.
2. The daily close is strictly above the highs, or strictly below the lows,
   of the 20 completed daily bars before the decision bar.
3. For an upward event, EMA5 is greater than EMA20 on all four views. For a
   downward event, EMA5 is less than EMA20 on all four views.
4. Missing scheduled closes, unavailable prior-20 history, roll ambiguity, or
   disagreement on any view produces `abstain`.
5. No option side, leg, expiry, performance claim, or execution meaning is
   attached during regime construction.

Why it is worth retaining: every clause is already represented in the causal
underlying corpus, the timeframe is explicit, and the definition does not
reuse M6-EXP-013 swing-line labels. The accepted #53 packet retains all six
families and supplies inspectable daily counterexamples without using outcomes
or profitability to select among them.

Counterexamples and failure modes:

- Intraday breakouts commonly occur while the daily view remains inside its
  prior range.
- Most historical records have mixed EMA alignment.
- The AU/AG slice has almost no fully aligned downside coverage.
- Contract rolls can create apparent range breaks unless the causal roll
  ledger and exact scheduled close are bound.
- Within-family excursion slices contain both directional and round-trip
  paths, so excursion percentile cannot substitute for the breakout and EMA
  clauses.
- The definition has not been applied to TA, MA, CU, or i in a roll-bound
  multi-cadence matrix. #49 must freeze the universe and fail closed on missing
  event inputs rather than select families from the descriptive views.
- Every accepted option overlay is quality-invalid and stale; SR-01 has no
  option-leg, premium-outcome, or execution evidence.

### SR-02 — causal two-anchor swing-line right break

Status: **proxy; mechanically defined but scientifically unavailable for
reuse**

Use strict three-bar pivots only after the right confirmation bar, select the
two most recent monotonic same-type anchors, project the line, and classify a
completed-bar close beyond the projection by more than 0.25 times the median
range of the 20 prior completed bars. Conflicting long and short projections
produce `conflict`; unavailable anchors produce `abstain`.

Counterexamples and failure modes:

- More than half of both training and holdout classifications are abstain or
  conflict.
- Pivot-pair choice and the 0.25-range tolerance are empirical conventions,
  not authenticated Feitian rules.
- M6-EXP-013 already tested the frozen directional mapping derived from this
  family and produced an empty candidate set.

Recommendation: preserve it only as a documented negative-control proxy. Do
not feed it to #49 as a renamed experiment.

### SR-03 — 1B/2B/3B plus DD-line chart interpretation

Status: **too-subjective; not authentic**

The source-oriented narrative says a divergence alert is interpreted through
1B/2B/3B structure and then a left-side DD-line touch or right-side trend-line
break. The repository does not contain authenticated rules for B boundaries,
anchor selection, chart level, tolerance, confirmation, side symmetry, or
invalidation.

Counterexamples and failure modes:

- Two reviewers can choose different B boundaries and still appear
  consistent with the prose.
- A daily bar cannot resolve a tick-scale option-line touch or stop.
- The option DD-line proxy requires contemporaneous bid/ask and contract tick
  size; current daily aggregates cannot establish either.
- Calling this authentic would turn an unresolved source question into an
  after-the-fact parameter surface.

Recommendation: do not preregister it. Revisit only after source extraction
fixes every discretionary field before any outcome access.

## Recommendation for #49

**Advance only SR-01 to #49 as the definition-mature candidate.** SR-02 remains
protected by the M6-EXP-013 negative gate, and SR-03 remains too subjective.
This recommendation is about preregistration readiness, not economic value.

The accepted six-family views remove the exploratory prerequisite: Strategy
can inspect balanced continuity, mainstream, and control lanes without raw
directory access or outcome-based ranking. They do not validate SR-01, choose
an instrument, or authorize `P1-EXP-002`. #49 must make the separate freeze,
revise, or stop decision before any event enrollment or outcome access.

## Constraints for #49

If #49 freezes SR-01, it must:

1. Preserve the fixed six-family order and the continuity/mainstream/control
   roles. Do not include or exclude a family because of observed excursion,
   direction, option-path change, activity, or overlay availability.
2. Bind causal, hash-bound D/W/60-minute/15-minute underlying views under an
   explicit roll policy, exact scheduled decision close, and strict timestamp
   truncation.
3. Freeze the prior-20 breakout, EMA5/EMA20 agreement, `abstain`, event
   deduplication, exclusions, minimum sample gate, and train/validation/holdout
   policy before reading any response.
4. Treat missing multi-cadence inputs, roll ambiguity, inadequate two-sided
   coverage, and every stale or quality-invalid option input as fail-closed
   conditions. Do not relax SR-01 or reselect a family.
5. Retain PR #55's future-row invariance, deterministic regeneration,
   field-allowlist, credential-prefix, and public-safety protections.
6. Bind exact filtered input content or an acquisition version for formal
   experiment evidence. PR #55's anonymous inventory hashes are sufficient
   for exploration only.

#51 remains blocked. No outcome, registry mutation, or execution work belongs
to #52.

## Reproduce

The verifier recomputes every count used above from the committed source
artifacts and checks their frozen SHA-256 bindings:

```sh
node doc/repro/pa-feitian-phase1-swing-regime-exploration-2026-07-30/verify.mjs
```
