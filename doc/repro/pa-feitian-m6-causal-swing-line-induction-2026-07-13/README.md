# PA / Feitian M6 causal swing-line induction

This packet is an exploratory structural-proxy study. It does not reconstruct
an authentic Feitian or DD-line rule, and it does not evaluate outcomes or
performance.

## Corpus And Labels

The protocol binds the preceding M6-EXP-011 protocol and atlas by SHA-256. It
reuses the same deterministic, non-outcome selection: four AU and four AG
daily option series with enough valid bars in both frozen time partitions.

The proxy uses only completed K-bars. A strict three-bar pivot is visible only
after its immediate right confirmation bar. The two most recent monotonic pivot
anchors project a structural line. Touches, breaks, and invalidations use a
fixed unit-free tolerance equal to one quarter of the median range of the 20
bars before the decision bar. A previous causal same-side touch within 20 bars
is recorded as a second-touch proxy.

All labels are structural only: `abstain`, `conflict`, long-side and short-side
touch/break/invalidation classifications. They are not trade signals or
directions. Every proxy clause is labelled
`empirically_induced_not_authentic` and `training_only`.

## Result

The committed atlas contains 434 training and 449 holdout structural labels.
Six global labels appeared in both AU and AG training coverage: abstain,
conflict, long invalidation, long left touch, long right break, and short right
break. The holdout applies this frozen proxy only to structural coverage and
reproducibility; it has no outcome or performance fields.

## Verify

```sh
node doc/repro/pa-feitian-m6-causal-swing-line-induction-2026-07-13/verify.mjs
```

Optional byte-identical regeneration accepts explicit caller-provided local
inputs:

```sh
PA_FEITIAN_REGENERATE=1 \
QUANT_DATA_ROOT=/path/to/quant_data \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-causal-swing-line-induction-2026-07-13/verify.mjs
```
