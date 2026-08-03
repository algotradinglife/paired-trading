# PA weight-learning and forward-feedback protocol v1

This is a protocol contract, not an optimization run. It defines what may be
learned after forward evidence exists and keeps the graph topology immutable.

## Frozen topology and versioning

- `graph_version` and the complete node/edge ID set are frozen for M7 and every
  M8 batch. A new node or edge is a new protocol version, never an update to an
  old one.
- `policy_version` binds graph version, lifecycle version, weight vector,
  shrinkage parameters, and objective definition.
- Only declared node, edge, and terminal weights may change between batches.
- Per-trade online updates, topology mutation, confirmation-set reuse, and
  outcome-conditioned path rewriting are forbidden.

## Weight meanings

For a context bucket `c` and element `j`:

- **Node weight** `w_node(j,c)` is the reliability of node `j`'s policy
  recommendation in context `c`, estimated only from completed
  `valid_policy_episode` rows.
- **Edge weight** `w_edge(e,c)` is the conditional value of traversing edge `e`
  after its source node in context `c`, using the declared outcome vector and
  calibration evidence.
- **Terminal weight** `w_terminal(t,c)` is the contribution of terminal `t`
  (trade, wait, or reject) to calibrated decision quality in context `c`; it is
  not a capital or order-size instruction.

Weights are interpretable signed scores with a declared range and context key;
they never replace the frozen guards.

## Sparse-path prior and shrinkage

Every element starts from a versioned prior `(mu_0, kappa_0)` and receives a
batch posterior-like score:

`w = (kappa_0 * mu_0 + n * mean_observed_score) / (kappa_0 + n)`.

`n` counts eligible policy episodes only. The prior is retained in the policy
record, and the shrinkage strength is fixed before seeing the confirmation set.
No sparse path may bypass its prior or borrow an outcome from another topology.

## Forward batches and update boundaries

1. M7 runs exactly 10 forward rehearsal episodes. They test protocol and
   interface usability and **never update weights**.
2. M8 seals at least 30 eligible forward `valid_policy_episode` rows as the
   learning batch. Invalid and human-override rows are counted but excluded.
3. Candidate weights are fitted once after the 30-row learning batch is sealed.
4. The next 20 episodes are sealed unseen confirmation data: exactly **20 sealed
   unseen confirmation episodes**. They are evaluated
   exactly once against the prior and candidate policy versions and never reused
   for fitting or threshold selection.

These are minimum operational gates, not statistical proof or capital readiness.

## Multi-metric objective

The objective is a declared vector, not binary win rate:

- policy-path calibration error (primary calibration term);
- realized-R calibration and Brier-style outcome calibration;
- MFE/MAE ordering and capture ratio;
- confirmation latency and holding-time calibration;
- terminal-class balance and invalid/quarantine rate;
- stability of node/edge contributions across contexts.

The candidate must improve the predeclared composite with no unacceptable
regression on any protected metric. A win/loss count alone cannot promote a
policy.

## Promotion, rollback, and comparison

- Compare candidate and prior policy on the same sealed confirmation set without
  refitting either version.
- Promote only if the candidate satisfies the frozen multi-metric gate,
  preserves all integrity guarantees, and has no topology or hindsight finding.
- Record prior digest, candidate digest, metric vector, confirmation-set digest,
  and decision-maker in a promotion record.
- Roll back by restoring the prior immutable policy digest; never edit a policy
  version in place.
- Any integrity failure, confirmation reuse, look-ahead, or topology mismatch
  forces rollback/quarantine regardless of market outcome.

## Explicit prohibitions

No neural network, reinforcement learning, graph-topology learning, automatic
policy generation, automatic order routing, capital authorization, or reserve
release is part of this protocol.
