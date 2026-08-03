# PA decision-graph management adjudication v1

Status: `accepted`

PI disposition: Issue #85 comment
[#5169587241](https://github.com/algotradinglife/paired-trading/issues/85#issuecomment-5169587241)
on 2026-08-04. Every rule below is a `pi_policy_extension` for the separate
non-authentic PA line. None is attributed to PA_Agent or authentic Feitian.
There are no implicit defaults: every previously silent management branch is
bound below to an explicit PI selection.

## 0. Event-time and integrity precedence

Closed bars are the only graph/state inputs, but the frozen structural stop is a
hard protective price order. Event ordering is:

1. hard stop touch or adverse gap;
2. same-bar stop/TP1/TP2 collision check;
3. TP1 or TP2 touch;
4. close-based confirmation, weakening, or trailing.

For OHLC-only replay, a long stop touches at `low <= stop` and a short stop at
`high >= stop`. A gap opening adversely beyond the stop fills at the bar open;
an ordinary touch fills at the stop price. The close never delays protection. A
same-bar stop and target collision is `invalid_data` /
`intrabar_order_ambiguous` unless finer event ordering resolves it.

## 1. Structural invalidation (`MA-01-invalidation`)

Selected A, amended to hard-touch execution: the first touch or breach of the
frozen structural stop emits `invalidated -> exited` immediately under the fill
convention. One close beyond the stop is not required; two closes are forbidden
as a protection delay. The bar close completes the audit record only.

## 2. Confirmation and weakening (`MA-02-confirmation-weakening`)

Selected B with PA-context guards:

- Confirmation requires the first two consecutive post-entry closed bars to show
  directional follow-through. Long bars close above their preceding close and
  entry; short bars close below their preceding close and entry. Neither bar may
  trigger the hard stop and the frozen PA direction trace must remain aligned.
- If the two-bar window does not confirm, emit
  `failed_follow_through -> condition_exit` at the second post-entry close.
- After confirmation, weakening requires two consecutive adverse closes and, on
  the second close, the frozen PA trace is neutral/opposite under §2.3 or fails
  the momentum-support predicate under §2.5. A single adverse bar is an ordinary
  pullback and does not weaken or exit.

## 3. TP1 / TP2 (`MA-03-tp1-partial`)

Selected B with a fixed declared fraction:

- The policy unit is normalized to `1.0`, independent of account size.
- The first valid TP1 touch exits exactly `0.5`.
- The remaining `0.5` is the runner for TP2 or another terminal guard.
- No discretionary fraction, scaling, or per-episode resizing is permitted.
- The original trader equation remains based on TP1 as the upstream source
  specifies.

## 4. Protective stop and trailing (`MA-04-trailing`)

Selected B with a fixed structural formula:
The three-bar pivot rule is the sole post-TP1 ratchet rule.

- Before TP1, retain the original frozen structural stop.
- After TP1, a long pivot low at bar `i` requires
  `low[i] < low[i-1]` and `low[i] < low[i+1]`; it becomes known only when
  `i+1` closes and proposes `low[i] - 1 tick`.
- A short pivot high is symmetric and proposes `high[i] + 1 tick`.
- Long stop is `max(previous_stop, candidate_stop)`; short stop is
  `min(previous_stop, candidate_stop)`. The stop never loosens and TP1 alone
  never moves it to breakeven.
- Every updated stop uses the hard-touch event-time convention in section 0.

## 5. Condition and time exit (`MA-05-time-exit`)

Selected B with operational censoring:

There is no arbitrary maximum-hold exit. A position terminates only by hard
structural/trailing stop, TP2, `failed_follow_through`, or confirmed weakening
under section 2. A study cutoff may record an open episode as `right_censored`,
but that is not a synthetic exit and cannot enter completed-outcome learning.

## Promotion and audit binding

The selected binding IDs are explicit and stable:

| branch | selected rule |
| --- | --- |
| `MA-01-invalidation` | `A_hard_touch_execution` |
| `MA-02-confirmation-weakening` | `B_two_bar_pa_context_guard` |
| `MA-03-tp1-partial` | `B_fixed_half` |
| `MA-04-trailing` | `B_three_bar_pivot_ratchet` |
| `MA-05-time-exit` | `B_no_time_exit_right_censor` |

The exact selected rules are bound in `trade_lifecycle_contract_v1.json`, and
fixtures exercise every event precedence and management branch. The verifier
requires the accepted comment ID, zero pending selections, hard-stop precedence,
collision quarantine, two-bar confirmation/weakening, fixed 0.5 runner, monotonic
pivot ratchet, no time exit, and right-censor exclusion. This adjudication does
not by itself authorize M7; only the packet's `protocol_ready_for_m7` terminal
authorizes creation of the M7 child issue graph.
