# M6F causal measurement capability receipt

This package is the public-safe Data-owner receipt for Issue #79 and dependency
`M6F-DATA-CAPABILITY-01`. It audits the ten exact measurement interfaces frozen
by Issue #77 / PR #78 at revision
`c10d4ccd462e7fb6369d6e1a25aeb7a5a622b2c2` and artifact
`doc/repro/pa-feitian-m6f-source-fidelity-recovery-2026-08-02/measurement_readiness_v1.json`.
The frozen input is 18,581 UTF-8 bytes with raw-byte SHA-256
`2ab764f77c90bf8ac979be7dde58a8d7352552d146d117cda3a8850c0b66e480`.
The exact public-safe bytes are carried locally as
`upstream_measurement_readiness_v2.json`, so verification does not require the
unmerged Strategy commit, a Strategy branch, or network access. It does not
inspect or publish
licensed rows, provider implementation, credentials, reserve identities,
outcomes, M6R episode payloads, or private inventory identities.

## Result

`capability_result: fail` — 0 pass, 10 fail.

The underlying and option interfaces contain substantial historical OHLC
material, but presence is not causal readiness. The bound evidence does not
provide all required row-level `available_at` values, exact exchange session
and trading-date assignments, provider bar-finalization and revision semantics,
an immutable as-of option contract master, exact expiry/lifecycle/roll state,
a single causal premium basis, or complete requested/missing/late accounting.
The source-authorized annotation protocol resolves semantics; it does not create
the missing measurement rows or provenance.

MEAS-05 remains explicitly conditional because its frozen chart source is
unresolved between option and underlying planes. The receipt evaluates both
branches fail-closed and does not silently select the option plane.

The receipt records every requested accounting category for every binding
profile. Where the committed evidence has no valid denominator, the value is
explicitly `null` and the profile fails; zero is never substituted for unknown.
The two observed row surfaces reconcile under their own frozen OHLC and
timestamp-null quality predicates. Here, `accepted` means only that a row
passes that exact surface-quality predicate; it does not mean causal readiness
or acceptance by a different measurement interface:

- daily underlying: 66,720 observed, 66,625 accepted, 95 rejected, 0 duplicate;
- daily option premium: 798,548 observed, 416,764 accepted, 381,784 rejected,
  0 duplicate.

Requested, missing and late denominators are unavailable for both surfaces, so
neither accounting set is lossless. The daily option counts are retained only
as an explicitly named support surface for premium management; they are not
accepted management-action or lifecycle-transition records, whose exact
interface-level dispositions remain `null`. No admitted immutable public-safe
evidence bound at this cutoff materializes the derived perception or decision
traces, so those interfaces fail closed.

## Artifacts

- `upstream_measurement_readiness_v2.json` is the exact 18,581-byte public-safe
  Strategy input snapshot; its original revision, path and raw hash remain
  bound in the requirements and receipt.
- `measurement_interface_requirements_v1.json` freezes the exact ten field IDs,
  nodes, source classes, required fields and current source-authorized semantic
  requirements from the bound Strategy artifact.
- `causal_measurement_capability_receipt_v1.json` provides the per-field
  semantic bindings, public evidence hashes, accounting and fail-closed result.
- `artifact_manifest_v1.json` binds the upstream snapshot, requirement
  projection, receipt and verifier by byte length and raw-byte SHA-256.
- `verify.mjs` reads supporting evidence from its claimed immutable Jujutsu
  revision, recomputes evidence predicates, enforces the exact field/profile and
  applicability/status/prose/accounting bindings, hard-binds every profile's
  deterministic replay and fail-closed semantics, validates strict UTC calendar
  timestamps, canonical package bytes, README handoff fields, manifest hashes,
  and public-safety constraints.

artifact_manifest_sha256: 504f488d2168d537cc21a68812252fb94d87288a818357a04cfa9545774e7faa

Receipt raw-byte SHA-256:
`3b706bd7e5d2c5a488d1f580c947c3676f9762ea7c44b7ea65082b5c9929568f`.

## Verify

From a clean checkout:

```sh
node doc/repro/pa-feitian-m6f-causal-measurement-capability-2026-08-02/verify.mjs
node doc/repro/pa-feitian-m6f-causal-measurement-capability-2026-08-02/verify.mjs --negative
```

The verifier uses only committed public-safe evidence. It performs no network
request, raw-data access, source refresh or mutation.

## Handoff boundary

After merge and PI provenance acceptance, Strategy may consume only the public
receipt at
`doc/repro/pa-feitian-m6f-causal-measurement-capability-2026-08-02/causal_measurement_capability_receipt_v1.json`
and its exact merged revision. The receipt supplies only the Data
capability result; Strategy must independently recompute its frozen outputs.
This package authorizes no experiment, backtest, parameter choice,
preregistration design, M7, production policy or execution.
