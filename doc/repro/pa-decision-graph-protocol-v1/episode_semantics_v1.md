# PA episode semantics v1

## Contract boundary

An episode is a causal record of one graph decision and its later market
observation. Decisions and management transitions may read only closed bars with
timestamps at or before the transition. Market outcomes are appended after the
decision lifecycle; they are never inputs to the earlier policy path.

The hard structural stop is the exception to close-only timing: it is a frozen
protective price order whose event-time touch or adverse gap precedes all
close-based confirmation, weakening, and trailing. An unresolved same-bar stop /
target collision is `invalid_data` / `intrabar_order_ambiguous`, not a guessed
outcome.

Every episode binds:

- `episode_id`, `policy_id`, `graph_version`, and `lifecycle_version`;
- a decision timestamp and a monotonically ordered closed-bar input digest;
- one policy recommendation stream;
- zero or more declared human-override events;
- one market-outcome stream after exit or a declared data terminal;
- exactly one integrity status.

## Three independent streams

| Stream | Meaning | Required fields | Baseline eligibility |
|---|---|---|---|
| `policy_recommendation` | What the frozen graph and lifecycle prescribed at the causal decision time | `recommendation_id`, node/edge path, action, decision timestamp, policy/lifecycle versions, input digests | Eligible only when the completed episode is `valid_policy_episode` |
| `human_override` | A declared manual departure, with rationale and timestamp | `override_id`, `episode_id`, `overridden_action`, rationale, actor class, timestamp, input digest | Never enters baseline learning; query separately |
| `market_outcome` | What happened after the decision | exit reason, outcome timestamp, realized R, MFE, MAE, trend/confirmation observations, target/stop ordering, capture ratio, holding time | Joined only after integrity pass and completed outcome |

The streams are joined by `episode_id`, never by nearest timestamp or outcome
similarity. A missing stream is an integrity failure when the lifecycle requires
it; a human override is not a substitute for a policy recommendation.

## Integrity status vocabulary

Each episode has exactly one of:

1. `valid_policy_episode`
2. `valid_human_override_episode`
3. `invalid_causality`
4. `invalid_state_transition`
5. `invalid_version_binding`
6. `invalid_data`
7. `invalid_replay`

`valid_human_override_episode` is retained for separate analysis but is never a
baseline-learning row. Any invalid status is quarantined before outcome
aggregation, even when its market outcome is positive.

## Eligibility truth table

| Policy stream | Override stream | Outcome complete | Integrity checks | Baseline set | Outcome aggregation | Quarantine |
|---|---|---:|---|---|---|---|
| present | absent | yes | all pass | admit | admit | no |
| present | absent | no | otherwise pass | reject | hold/unresolved | no |
| present | present | yes | all pass | reject | separate override analysis | no |
| present | present | no | any | reject | hold/unresolved | yes if integrity fails |
| absent | absent | any | any | reject | reject | yes: missing recommendation |
| any | any | any | causality/version/state/data/replay failure | reject | reject | yes |

The verifier evaluates every row of this table. It does not infer eligibility
from P&L, win/loss, or a human assertion.

The committed fixture matrix is exhaustive: 7 integrity statuses × 2 policy
stream origins × 2 override-stream origins × 2 completion states = 56 cells.
An invalid status, missing policy shape, or origin/stream mismatch fails closed
even when an outcome is profitable.

## Correct-error treatment

- A policy-conformant structural stop is an eligible negative-return observation
  when all integrity checks pass. It is a **correct error**, not a chain defect.
- A policy-conformant trend capture is an eligible positive-return observation.
- A human override is evaluated in its own stream and cannot silently replace the
  recommendation.
- A profitable invalid episode remains quarantined; positive P&L never repairs
  causality, state, version, data, or replay failure.
- A study cutoff may mark an open lifecycle `right_censored`; censoring is not an
  exit and is excluded from completed-outcome weight learning.

## Causality and replay rules

- Every input reference has `observed_at_utc <= decision_or_transition_ts_utc`.
- Outcome fields are forbidden in policy and management input payloads.
- A policy path is replay-valid only when the same closed-bar inputs, graph
  version, lifecycle version, and policy weights reproduce the same node/edge
  path and actions byte-for-byte.
- A future input, missing digest, duplicate transition, changed topology, or
  mismatched version produces the corresponding invalid status before any
  outcome metric is calculated.
