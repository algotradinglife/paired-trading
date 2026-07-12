# Operationalized bare-K v0

This directory is a public-safe, synthetic-only formalization of a bare-K decision hypothesis. Its required label is `operationalized_hypothesis_not_authentic`; it does not claim to recover, reproduce, or validate an authentic Feitian or DD-line system.

The committed contract came before source reading. The source-and-assumption ledger separates supported decision-chain statements from every material v0 choice that was not exactly specified. In particular, pivot detection, line construction, candidate bar shape, invalidation threshold, the short mirror, quality gating, and full conflict ordering are provisional assumptions.

`bare_k_rule_v0.mjs` evaluates only completed synthetic OHLC bars. Its outputs are research classifications, never execution, option selection, pricing, risk sizing, or performance. `synthetic_bare_k_rule_fixtures_v0.json` contains invented values only. Run the standalone verifier with:

```sh
node verify.mjs
```

Authentic-rule recovery remains unresolved. The next fidelity gate is independently sourced definitions or annotations for 1B/2B, line anchors/tolerances, structural buffer semantics, chart context, and the bearish branch; only then may a later, separately versioned formalization be considered.
