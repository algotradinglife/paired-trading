# P1-EXP-002 native-source decision

Issue: #60
Decision time: `2026-07-30T17:01:53Z`
Verdict: **`stop_p1_exp_002`**

This is a pre-outcome Strategy decision bound to the accepted #59 native-source
audit, the frozen #49 registry/lock, and the completed #50 historical gate.

## Decision

Stop the P1-EXP-002 lane. The evidence cannot support a defensible source
contract revision:

- all 12 intraday cells lack independently approved provider/bar-end semantics;
- 521,090 unexplained intraday timestamp rows occur across training,
  validation, and holdout;
- 169 daily non-positive/non-finite OHLC price findings remain in CZCE.TA (76)
  and CZCE.MA (93), violating the accepted zero-finding gate.

The audit cannot distinguish corrupt rows from provider no-trade placeholders,
and it cannot justify a delayed availability mapping without source-specific
semantics. Inventing those rules, shifting timestamps, repairing rows, dropping
clock grids, or silently excluding observations would be post hoc contract
changes, not a causal revision.

## Required boundary

Only the public-safe, pre-outcome source-quality aggregates from #59 were
consumed. No strategy events, outcomes, returns, holdout strategy evidence,
options, or execution inputs were accessed. #51 must close without
implementation because its frozen experiment has stopped. #50 remains complete
and is not weakened. A future attempt would require a new immutable source
version with provider and bar-end semantics, lossless accounting for every row,
a new reviewed Strategy decision, and a new implementation issue; this memo
does not authorize Data implementation work.

## Reproduce

```sh
node doc/repro/pa-feitian-phase1-p1-exp-002-decision-2026-07-31/verify.mjs
```
