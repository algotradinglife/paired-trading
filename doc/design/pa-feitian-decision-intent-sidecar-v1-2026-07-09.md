# PA / Feitian Decision Intent Sidecar v1

Date: 2026-07-09

## Scope

`pa_feitian_decision_intent_v1` is a manifest-referenced sidecar artifact for
decision readiness. It does not change `pa_feitian_snapshot_v0` or
`pa_feitian_snapshot_v1`, and it does not require a snapshot v2 by default.

This contract only defines the shared artifact surface. Strategy adapters own
how the fields are computed, and frontend/integration work should consume the
artifact only after their separate tasks are unblocked.

## Artifact Shape

The sidecar has top-level provenance plus one `intents[]` record per snapshot
signal that needs readiness review.

Required intent fields:

- `decision_state`: one of `reject`, `watch`, `armed_watch`, `trade_ready`,
  `observation_runner`.
- `execution_allowed`: boolean gate derived from `decision_state`.
- `product_direction_tier`: product-direction readiness tier, including
  `observation_only` for non-executable product directions.
- `premium_stop`: premium-space stop status, source, entry/stop premium,
  stop distance, soft gate, timestamp, and evidence reference.
- `confirmation`: premium confirmation status, source, confirmation timestamp,
  and evidence reference.
- `liquidity`: liquidity status, quote count, quote age, recovery requirement,
  and evidence reference.
- `reason_codes`: uppercase snake-case downgrade or readiness codes.
- `no_lookahead_inputs`: whitelisted decision-time input references with
  `asof_ts_utc` not later than the decision timestamp.

## Manifest Reference

The run manifest may include an optional `decision_intent_artifact` with
`kind=decision_intent`, path, SHA-256, schema version, and content type. When
present, `output_hashes.decision_intent_artifact` must match the artifact hash.

The sidecar provenance points back to the source manifest path and the snapshot
artifact path/hash. It intentionally does not embed the source manifest hash, so
the manifest can hash the sidecar without creating a circular digest.

Existing manifests that omit `decision_intent_artifact` remain valid.

## Invariants

`execution_allowed` is true if and only if `decision_state` is `trade_ready`.
Execution also requires:

- `product_direction_tier=aligned_trade_candidate`
- `premium_stop.status=clear`
- `confirmation.status=confirmed`
- `liquidity.status=adequate`
- `liquidity.recovery_required=false`

`premium_stop.status=clear` cannot use `half_loss_fixed`, `unavailable`, or
`not_applicable` as the stop source. This keeps stop-clear proxy cases from
looking executable.

No-lookahead input references are restricted to decision-time kinds and reject
posterior/outcome/label/MFE/MAE/stop-first references.

## Versioning

This is a v1 sidecar contract. Future strategy changes can add a new sidecar
version or, only with explicit cross-task approval, a snapshot v2. Snapshot
v0/v1 fields and meanings remain stable under this contract.
