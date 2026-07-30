# Phase 1 historical swing-regime exploration

Issue: #52  
Research date: 2026-07-30  
Decision: **stop before freezing `P1-EXP-002`; request a six-family causal
regime view first**

## Scope and evidence boundary

This note returns Phase 1 to exploratory research after `P1-EXP-001` stopped
as `data_blocked`. It asks which PA / Feitian-like descriptions are precise
enough to consider in a later registry revision. It does not select an
instrument, inspect strategy outcomes, mutate the hypothesis registry, or
authorize #51.

The observations below come only from committed, public-safe artifacts:

- the six-family capability and interface audit from #43 / PR #48;
- the causal AU/AG underlying corpus with completed D/W/60-minute/15-minute
  summaries;
- the outcome-free daily bare-K trace and causal swing-line atlases; and
- the negative M6-EXP-013 premium-K response gate.

The source artifacts contain current-vintage retrospective data. They do not
prove what a vendor exposed at each historical decision. This pass did not
refresh market data, read strategy outcomes, or inspect the uncommitted
runtime interface. Counts are structural coverage, not PnL, win rate, EV,
instrument ranking, or evidence of future value.

## What is actually observable

PR #48 established underlying and option-bar interface presence for the fixed
six-family universe at daily, hourly, 15-minute, and 5-minute cadence. All
interfaces are stale at the 2026-07-30 audit date. The historical research
status is `usable_with_limitations`, while causal operational use remains
blocked.

Only AU and AG currently have a committed, hash-bound causal historical
corpus suitable for regime inspection. That corpus contains 333 AU and 337 AG
decision records from 2025-01-02 through 2026-06-08 and four completed-bar
views per record. TA, MA, CU, and i have interface-level aggregates, but no
equivalent committed causal regime matrix. Absence of that matrix is not
evidence that a regime or structure is absent in those families.

### AU/AG completed-bar regime sketches

The table is in fixed continuity-reference order. `Aligned breakout` means a
daily strict-prior-20 breakout whose direction agrees with the causal EMA
alignment on D, W, 60-minute, and 15-minute views. `Mixed EMA` means the four
views do not all carry the same alignment.

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

Status: **derived / proxy; conditionally mature after the six-family view**

At the completed 15:00 Asia/Shanghai decision snapshot:

1. D, W, 60-minute, and 15-minute bars are built from timestamp-truncated
   source rows under a fixed causal roll policy.
2. The daily close is strictly above the highs, or strictly below the lows,
   of the 20 completed daily bars before the decision bar.
3. For an upward event, the close is above the causal fast/slow EMA relation
   on all four views. For a downward event, it is below on all four views.
4. Missing scheduled closes, unavailable prior-20 history, roll ambiguity, or
   disagreement on any view produces `abstain`.
5. No option side, leg, expiry, performance claim, or execution meaning is
   attached during regime construction.

Why it is worth retaining: every clause is already represented in the causal
underlying corpus, the timeframe is explicit, and the definition does not
reuse M6-EXP-013 swing-line labels.

Counterexamples and failure modes:

- Intraday breakouts commonly occur while the daily view remains inside its
  prior range.
- Most historical records have mixed EMA alignment.
- The AU/AG slice has almost no fully aligned downside coverage.
- Contract rolls can create apparent range breaks unless the causal roll
  ledger and exact scheduled close are bound.
- The definition has not been applied to TA, MA, CU, or i in a committed
  causal matrix, so it is not ready to determine the `P1-EXP-002` universe.

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

**Do not freeze `P1-EXP-002` yet. Keep #49 blocked and revise its prerequisite
to require one public-safe six-family causal regime matrix.**

SR-01 is the only definition clear enough to carry forward, but the current
committed evidence covers only AU/AG. Freezing a universe now would either
reuse the data-blocked continuity pair without resolving its gate or select
TA/MA/CU/i without the comparable historical regime view requested by #52.
SR-02 is protected by the earlier negative gate, and SR-03 remains
too subjective.

This is a valid stop decision for #52: the exploration improved the candidate
language and identified the smallest missing evidence needed to make #49
admissible. It is not a claim that SR-01 has economic value.

## Data views needed before #49

Ask Data for one deterministic, read-only artifact with:

1. The fixed six-family order from #48 and a frozen historical calendar shared
   across families.
2. Causal, hash-bound D/W/60-minute/15-minute underlying views using an
   explicit roll policy, exact scheduled decision close, and strict timestamp
   truncation.
3. For every family and view: availability, exclusion reasons, prior-20
   high/low breakout state, causal EMA alignment, bar direction, close
   location, and range divided by prior-20 mean range.
4. Aggregate counts for SR-01 admission, `abstain`, timeframe disagreement,
   roll sessions, missing closes, and OHLC-quality failures. No returns,
   outcomes, PnL, win rate, EV, or instrument ranking.
5. A future-row invariance test, deterministic regeneration, source inventory
   digest, and current-vintage / historical-visibility limitation.
6. Public output that omits local paths, usernames, filenames, raw contract
   identifiers, raw rows, and raw chart values. Optional normalized sketches
   must use hashed specimen identities only.

If the fixed view shows inadequate two-sided or cross-family coverage, #49
should stop rather than relax SR-01 or select a family by posterior behavior.

## Reproduce

The verifier recomputes every count used above from the committed source
artifacts and checks their frozen SHA-256 bindings:

```sh
node doc/repro/pa-feitian-phase1-swing-regime-exploration-2026-07-30/verify.mjs
```

