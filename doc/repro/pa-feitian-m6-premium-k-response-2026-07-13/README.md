# PA / Feitian M6 causal premium-K response matrix

This packet evaluates a frozen, causal structural-label-to-premium-K response
matrix. It is empirical, exploratory, non-authentic, and non-executable. It
does not reconstruct Feitian, produce a trade signal, report PnL or premium R,
or provide execution evidence.

## Design

The committed protocol binds M6-EXP-011 and M6-EXP-012 by SHA-256, then reuses
their same deterministic eight-series daily AU/AG corpus. Causal label logic is
unchanged. Six structural labels have a predeclared upward or downward
close-to-close interpretation over one, three, and five completed daily bars.

A training mapping/horizon can enter the frozen candidate set only with at
least 20 observations, positive mean and median signed change, and a
non-negative lower bound of the fixed 95% series-clustered bootstrap interval.
The candidate set is frozen before any holdout application.

## Result

No training mapping/horizon passed every predeclared gate. The candidate set is
empty, so the 2026 H1 holdout was not applied. This is a negative or
inconclusive result for this particular empirical proxy; it is not evidence to
relax thresholds, alter the label mapping, inspect a different corpus, or make
an execution decision.

The public atlas contains aggregate counts and signed-change summaries only.
It excludes local paths, source filenames, contract text, raw K-bars,
per-event values, credentials, PnL, bid/ask, delta, Greeks, DTE, and execution
information.

## Verify

```sh
node doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/verify.mjs
```

Optional byte-identical regeneration accepts an explicit caller-provided data
root:

```sh
PA_FEITIAN_REGENERATE=1 \
QUANT_DATA_ROOT=/path/to/quant-data \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/verify.mjs
```
