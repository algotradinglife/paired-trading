# PA / Feitian M6 bare-K observation protocol

Hermes task: `t_49902c76`

The JSON protocol was frozen in commit `eb29562` before the permitted
read-only research repository or any external option data was inspected. It
binds the finalized underlying corpus and liquid-premium eligibility evidence
by SHA-256, preserves the `retrospective_finalized` label, and fixes the 15:00
Asia/Shanghai decision-time cutoff.

This packet defines observation mechanics only. It contains no premium path,
result, ranking, chosen contract, synthetic price, or downstream milestone
work.

## Deterministic boundary

- A PA alert must be explicit in the bound underlying input. Bar direction,
  breakout, EMA alignment, or any combination of descriptive diagnostics is
  not an alert.
- Bottom/bullish alerts map to calls and top/bearish alerts map to puts.
  Missing, flat, unknown, or conflicting directions abstain.
- Every eligible contract-date unit on the mapped side is observed in a stable
  total order. No strike or month wins a tie and no contract is ranked.
- Duplicate identities or timestamps invalidate an observation. Missing bars
  abstain; no fill, interpolation, resampling, cadence switch, or contract
  substitution is allowed.
- A PA alert remains `alert_only` unless an authentic, frozen Feitian bare-K or
  DD-line rule independently confirms it.

## Capability finding

The two pinned inputs pass their file-hash and research-label checks, but they
cannot execute the observation state machine:

| Required capability | State | Reason |
| --- | --- | --- |
| Explicit PA alert | `blocked_missing_explicit_pa_alert` | The underlying corpus contains descriptive diagnostics, not an alert identity/direction. |
| Eligible unit membership | `blocked_missing_unit_membership` | The eligibility evidence contains aggregate counts, not contract-date membership records. |
| Authentic Feitian rule | `blocked_authentic_rule_unrecovered` | Permitted source research marks the DD-line definition approximate or unresolved and does not provide complete machine-testable predicates. |

Generic PA candle rules, W-bottom/swing approximations, percent-distance rules,
and generic trend lines are explicitly rejected as substitutes. Consequently
`confirmed_bare_k` is unreachable in this version.

## Public-safe source record

Only aliases, revisions, hashes, and high-level capability findings are
published. The permitted research repository was read at revision
`5802d0ff5d99819ad01ba9f3550b6a2d504f1e81`; it was not modified. No absolute
external path, username, credential, raw row, or proprietary data byte appears
in the packet.

## Verify

Run the committed verifier:

```bash
node doc/repro/pa-feitian-m6-bare-k-protocol-2026-07-12/verify.mjs
```

Run the focused tests:

```bash
cd src
python3 -m pytest tests/test_pa_feitian_bare_k_protocol.py
```

The checks validate exact hashes and schemas, contract-before-evidence commit
ordering, state precedence, stable observation ordering, rejection of
post-cutoff rows, future-row invariance, missing-bar abstention, aggregate-only
membership rejection, and the unreachable-confirmation gate.

## Next gate

Supply hash-pinned explicit PA alerts and per-unit eligible membership, then
recover a complete authentic Feitian bare-K or DD-line definition. A versioned
successor contract must be frozen before any premium path is read.
