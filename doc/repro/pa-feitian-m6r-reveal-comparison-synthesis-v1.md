# M6R reveal comparison and hypothesis decision

## Scope and bindings

This comparison joins the 72 frozen blind annotations to the authorized reveal
exactly once. It is descriptive discovery only; it does not validate a strategy,
recover an authentic Feitian rule, or authorize M7.

- blind annotations: `sha256:ec999de7ff0d51a9cd4c8d883ab51c694899cb82c75328149fe19e7b04f283ff`
- blind pack: `sha256:cebfffa44871d23e9cc8883af5f5d8fa3a28fdc2e783f0776b8f62fde16d6565`
- sealed reveal artifact: `sha256:95b6762bba2c6e12f8ec366b589f261f903657013b3d93cf9dc7ae45e6c06f95`
- sealed reveal payload: `sha256:493e0bf04887c8ca5a0ed416da464a1360615c51ca6a5f26b7852aee9169ec6d`

## Direct blind observation

The frozen descriptors are context, local-turn count, candle-range behavior,
and bar-0 boundary/third shape. The comparison does not relabel them. Context/range
combinations are: falling+comparable 20; rising+comparable 19; rising+expanding
11; rising+narrowing 6; mixed+comparable 6; falling+narrowing 5;
mixed+expanding 2; falling+expanding 2; mixed+narrowing 1.

## Revealed descriptive comparison

The public-safe artifact reports sampling role, instrument family, frozen era,
close change at horizons 1, 5, 10, and 20, and future-high/future-low extreme
changes through horizon 20. It contains no raw future bars. All 72 IDs
reconcile exactly once, with 36 candidate-activity and 36 ordinary-control
rows; role, family, era, descriptor distributions, and role-by-descriptor
response distributions (counts, family/era coverage, and positive/negative/zero
counts with median/min/max at every horizon) are materialized in deterministic
aggregates. The candidate-floor audit enumerates 27 categories; 15 pass the
structural support floor, and all 15 have both negative and positive horizon-20
close changes. The separately selected candidate list is empty by Strategy
judgment, not by omitting the structural audit.

Across these fixed views, descriptor strata are heterogeneous: no descriptor
family supplies a stable response across roles, families, and eras. For a
concrete contradiction, the rising-context candidate episode
M6R-02e7c1ce140fcb878451 has a -5.738476% close change at horizon 20, while
rising-context ordinary-control episode M6R-0af74e9252af3c6efca3 has +2.505219%.
The artifact retains distributions and counterexamples rather than ranking
families.

## Hypothesis induction and verdict

**Verdict: `no_candidate`. Candidate count: 0.**

The candidate floor examined was at least 8 episodes, 3 instrument families,
and 3 frozen eras, plus a decision-time-computable condition and explicit
counterexamples. The support floor passes for 15 categories, but directional
response is mixed in all 15. Selecting a direction, horizon, or threshold from
this discovery sample would be post-hoc, so Strategy freezes zero candidates.
This is an inconclusive discovery result, not a claim that no relationship
exists. `no_candidate` is the frozen Strategy judgment supported by this
complete audit.

## Unresolved ambiguity

The fixed descriptive surface cannot distinguish persistent structure from
transient movement, and the selected 72 episodes are not independent proof.
Any later hypothesis must be separately preregistered and independently
validated.
