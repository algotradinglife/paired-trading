# PA / Feitian M6 historical swing induction

This packet is an exploratory, empirical operationalization study. It does not
recover an authentic Feitian or DD-line rule and it does not evaluate trading
performance.

## Corpus

The committed atlas is built from read-only AU and AG daily option OHLC data.
The builder first inventories all direct daily option files, then selects the
first four public-file aliases per product that meet fixed non-outcome coverage
requirements: at least 60 valid completed training bars through 2025-12-31 and
at least 20 valid bars in the untouched 2026-01-01 through 2026-06-30 holdout.

Only positive-volume, positive-price OHLC rows with internally valid high/low
relationships enter a causal prefix. The committed public artifact contains no
file paths, contract names, raw OHLC values, charts, outcomes, or performance
metrics.

## Result

The initial corpus selected four series for each product. It produced 122
training and 449 holdout causal trace windows. Thirteen fixed trace classes
occurred in both AU and AG training coverage. The resulting
`empirical_bare_k_trace_family_v1` is limited to a vocabulary of completed-bar
descriptions: direction, body position, relative range, causal two-bar turn,
and three-bar shape.

Every induced clause is labelled `empirically_induced_not_authentic` and
`training_only`. It has no action, prediction, contract-selection, outcome, or
execution meaning. The holdout is used only to prove that the frozen trace
vocabulary can be replayed structurally.

## Verify

```sh
node doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12/verify.mjs
```

Optional byte-identical regeneration requires explicit local data and Python
inputs supplied by the caller:

```sh
PA_FEITIAN_REGENERATE=1 \
QUANT_DATA_ROOT=/path/to/quant_data \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12/verify.mjs
```
