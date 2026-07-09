# PA / Feitian M3 v0.2 Implementation Audit

Date: 2026-07-09
Branch: `strategy/pa-feitian-m3-v02-audit`
Hermes card: `t_d7d10d5d`
Verdict scope: `APPROVE_AUDIT_ONLY`

## Scope

This is a read-only implementation map for PA / Feitian v0.2 planning. No
production files under `src/` or `frontend/` were edited.

Inputs read:

- `/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/m3-planning/doc/repro/pa-feitian-m3-scope-review-2026-07-09.md`
- `/home/drwho1985/workspace/quant/docs/pa-feitian-v0.2-codex-handoff.md`
- `/home/drwho1985/workspace/quant/docs/pa-feitian-decision-chain-v0.2-exploration-draft.md`
- `/home/drwho1985/workspace/quant/docs/pa-feitian-p10b-au-call-premium-space-adjudication.md`
- `/home/drwho1985/workspace/quant/docs/pa-feitian-decision-chain-v0.1-result.md`
- `/home/drwho1985/workspace/quant/runs/pa_feitian_swing_corpus_v0_1/decision_chain_v0_1/validation/validation_report.md`
- P10/P11 premium validation harnesses and tests under `/home/drwho1985/workspace/quant/runs/.../premium_space_validation/` and `/home/drwho1985/workspace/quant/tests/`
- Current paired-trading M2 snapshot/manifest implementation under `src/engine/pa_feitian/`

The scope-review packet is intentionally not present on this audit branch; it
is on the coordination worktree named above.

## Implementation Map

The v0.1 deterministic rule tree lives outside this paired-trading worktree in
`/home/drwho1985/workspace/quant/quant_data/pa_feitian_decision_chain.py`.
That module states the key guardrails directly: only `decision_context` and safe
identifiers may be used, `posterior_outcome` and labels are forbidden, option
validation is premium-space, and AU put is observation-only
(`pa_feitian_decision_chain.py:1-15`).

Feature extraction is centralized in `extract_features()`. It reads
`packet.decision_context`, `event`, `option_match`, and pre-decision bars, then
computes all derived decision-time features in `_compute_derived_features()`
(`pa_feitian_decision_chain.py:212-317`). The current decision-time stop source
is synthetic: the minimum close of the last 36 pre-decision premium bars,
recorded as `decision_recent_36bar_low` (`pa_feitian_decision_chain.py:305-317`).
It does not currently preserve a rich decision-time `stop_ref_source` such as
`swing_low_premium` or `half_loss_fixed`.

The output surface is `DecisionResult`: `decision`, `would_trade`,
`entry_style`, `stop_clarity`, `reason_codes`, `decision_trace`, `reject_risks`,
and node snapshots (`pa_feitian_decision_chain.py:186-206`). The final
assignment happens after the nodes run: AU put is forced to watch/reject only,
then `would_trade` is a pure mapping from `decision`
(`pa_feitian_decision_chain.py:1260-1278`). `reason_codes` are concatenated
from node outputs (`pa_feitian_decision_chain.py:1283-1298`), and
`decision_trace` is the textual pipe-delimited node summary
(`pa_feitian_decision_chain.py:1300-1311`).

Node ownership:

- Futures structure and MACD alert/trigger maturity:
  `node3_futures_pa_structure()` (`pa_feitian_decision_chain.py:505-585`).
- Product direction and AU-put observation marker:
  `node4_direction()` (`pa_feitian_decision_chain.py:588-647`).
- Entry style and late/expensive timing:
  `node5_entry_style()` (`pa_feitian_decision_chain.py:650-740`).
- Premium confirmation, liquidity, and stop geometry:
  `node6_option_premium_execution()` (`pa_feitian_decision_chain.py:743-871`).
- Hard reject/watch/trade gate:
  `node7_reject_gate()` (`pa_feitian_decision_chain.py:874-1036`).
- Runner/watch management:
  `node8_management_runner_plan()` (`pa_feitian_decision_chain.py:1040-1113`).

The main v0.2 watchpoint is the post-node6 MACD momentum override. It can
upgrade MACD divergence into moderate structure, set `pullback`, restore
`premium_stop_geometry` to `clear`, suppress MACD-alert-only rejection, and then
force only `watch_only` rather than trade (`pa_feitian_decision_chain.py:1166-1219`).
This is exactly where the v0.2 "MACD alert / pullback boundary" and
stop-clear-illusion rules should be tightened.

## Premium Harness

The P10a AU-call premium validation harness is
`runs/pa_feitian_swing_corpus_v0_1/decision_chain_v0_1/premium_space_validation/validate_premium_space.py`.
It reads v0.1 `predictions.jsonl`, packet files, and diagnostic IDs
(`validate_premium_space.py:23-40`). Its row extraction explicitly splits
decision-time inputs from posterior evaluation outputs
(`validate_premium_space.py:75-190`). Premium stop distance is computed as
`(entry_premium - stop_ref) / entry_premium * 100`
(`validate_premium_space.py:132-138`), and trade/watch aggregates are separated
(`validate_premium_space.py:195-260`).

P11a stress validation is split by product-direction and adds downgrade
triggers. The key trigger logic covers false_trade, trade stop quality,
trade/watch mixing, clear-stop watch stop-first concentration, stop-clear
illusions, and thin/stale right-tail observation
(`validate_premium_space_p11a.py:308-369`). P11c repeats the same safety shape
for `SHFE.au.put` with an observation-only caveat.

## Existing Guardrail Tests

Quant-side evaluator tests already cover:

- deterministic corpus output (`test_pa_feitian_decision_chain.py:220-240`);
- no posterior/label leakage in feature extraction, trace, reason codes, and
  serialized output (`test_pa_feitian_decision_chain.py:246-351`);
- decision-boundary timestamp enforcement
  (`test_pa_feitian_decision_chain.py:306-324`);
- AU put never emits trade (`test_pa_feitian_decision_chain.py:508-521`).

P10a premium-space tests cover no-lookahead framing, trade/watch separation,
premium stop math, no futures-R stop source, A-class trade preservation, and
boundary diagnostics (`test_p10a_premium_validation.py:38-230`).

P11a tests cover product-direction separation, zero CZCE trades, no trade/watch
mixing, premium-space stop math, and downgrade-trigger evidence
(`test_p11a_premium_validation.py:38-240` plus the trigger class below that
range). P11c tests enforce AU-put observation-only scope, zero trades,
premium-space stop math, no AU-call/CZCE contamination, and stop-first
concentration warnings (`test_p11c_premium_validation.py:32-240`).

Paired-trading current M2 files do not implement the v0.1 decision chain. They
own snapshot/manifest plumbing:

- `src/engine/pa_feitian/contract.py` defines snapshot v0/v1, the structured
  `DecisionTraceV1`, and validators tying trace status/action to the signal
  (`contract.py:18-202`).
- `src/engine/pa_feitian/scorecard_producer.py` builds structured trace nodes
  from scorecard records (`scorecard_producer.py:211-340`) and explicitly
  consumes already-emitted score records without reading raw stores
  (`scorecard_producer.py:529-533`).
- The current v1 trace is reviewer plumbing, not v0.2 execution readiness. It
  lacks `decision_state`, `execution_allowed`, product-direction tier,
  premium-stop source/distance object, confirmation state, and liquidity
  recovery status.

## Minimal v0.2 Edit Points

When implementation is unblocked, the smallest strategy edit surface is the
quant decision-chain evaluator, not the paired-trading frontend:

1. Extend the decision-time feature/output model in
   `quant_data/pa_feitian_decision_chain.py` with a conservative readiness
   state: `watch`, `armed_watch`, `trade_ready`, `observation_runner`, `reject`,
   plus `execution_allowed`.
2. Add a decision-time premium-stop object or fields. The current synthetic
   `decision_recent_36bar_low` is not enough to distinguish
   `swing_low_premium` from `half_loss_fixed`.
3. Tighten `node6_option_premium_execution()` around stop-clear illusion:
   downgrade `clear` when the source is `half_loss_fixed`, premium is not
   confirmed, liquidity is thin/stale, or AU-call stop distance falls outside
   the 4%-12% soft gate.
4. Rework the MACD momentum override so it can create `armed_watch`, but cannot
   restore `clear` or imply `trade_ready` without a second premium confirmation.
5. Keep final `decision`/`would_trade` backward-compatible where needed, but
   make `trade_ready` the only state with `execution_allowed=true`.
6. Add reason codes for every downgrade:
   `STOP_CLEAR_DOWNGRADE_ALERT_ONLY`,
   `STOP_CLEAR_DOWNGRADE_PREMIUM_NOT_CONFIRMED`,
   `STOP_CLEAR_DOWNGRADE_HALF_LOSS_PROXY`,
   `STOP_CLEAR_ILLUSION_RISK`,
   `POST_STOP_RIGHT_TAIL_DIAGNOSTIC`,
   `OBS_RIGHT_TAIL_THIN_STALE`,
   `LIQ_STALE_RIGHT_TAIL_NO_TRADE`, and `LIQ_RECOVERY_REQUIRED`.
7. Update P10/P11 harness reports to carry the new readiness fields and keep
   posterior fields evaluation-only.

Contract work should remain blocked under this audit card. If M3 later chooses
to surface these fields in paired-trading artifacts, the current contract
choice is either a new snapshot contract version or a manifest-referenced
sidecar. Do not mutate snapshot v0/v1 semantics casually.

## Tests To Add For v0.2

Focused tests should be golden-case first:

- `p7e_a04c62c53446_0080`: not `clear`, not `trade_ready`; must explain
  stop-clear illusion and post-stop right-tail diagnostic.
- `p7e_c0493d86aee2_0054`: `CZCE.ma.call` clear-stop illusion; not
  `trade_ready`.
- `p7e_f88d962c3fb8_0077`: `CZCE.ta.call` stop-first clear-stop case; not
  `trade_ready`.
- AU put `0097/0098/0099`: observation-only, never execution allowed.
- AU-call A-class trades `0012/0019/0057/0058`: not killed without explicit
  premium-stop/confirmation evidence.
- `p7e_365569db90e4_0081`: thin/stale 5x right-tail remains observation-only.

Add one poisoned-posterior no-lookahead test that changes `posterior_outcome`
MFE/MAE/hit markers/stop_first and proves v0.2 readiness does not change.

## Audit Conclusion

The current implementation already has strong no-lookahead, premium-space, and
trade/watch/product-direction guardrails. The v0.2 risk is not broad retuning;
it is the narrow boundary where pre-decision premium momentum/MACD pullback and
synthetic "clear" stop geometry let watch rows look more executable than they
are. Implementation should begin only after the contract/readiness surface is
approved, and it should preserve `false_trade = 0` as the primary safety gate.
