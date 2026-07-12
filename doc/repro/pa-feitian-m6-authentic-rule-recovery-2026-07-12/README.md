# PA / Feitian M6 authentic-rule recovery

This packet records a fail-closed recovery decision for an authentic Feitian
bare-K rule. It is not a backtest, a performance result, or an execution
proposal.

## Result

`authentic_rule_recovery_status` is `blocked`. The accessible local material
supports the intended daily-chart setting and a left/right structural narrative,
but it does not supply a complete machine-testable rule. In particular, it does
not fix anchors, line construction and tolerance, 1B/2B and K-line quality, a
complete bearish branch, or full conflict precedence.

`operationalized_bare_k_v0` remains a separately labelled research hypothesis;
this packet does not promote it to an authentic rule.

## Artifacts

- `research/authentic_rule_recovery_contract_v1.json`: contract committed
  before source review.
- `research/authentic_rule_recovery_evidence_matrix_v1.json`: public-safe
  source inventory, dimension-by-dimension status, and minimum evidence needed
  to unblock recovery.
- `research/verify_authentic_rule_recovery_v1.mjs`: standalone fail-closed
  verifier and synthetic promotion tests.

## Verify

```sh
node research/verify_authentic_rule_recovery_v1.mjs
```

No market or option data, outcome, performance, fitting, execution, order-book,
or Greeks input is read or emitted by this packet.
