# PA / Feitian M3 Strategy + Frontend Output Review Packet

Date: 2026-07-09

Repo: https://github.com/algotradinglife/paired-trading

This packet requests ChatGPT review of the M3 strategy adapter and frontend
reviewer view outputs after the decision-intent sidecar contract was approved.

## Review Scope

Review only the strategy/frontend implementation outputs on top of the already
approved sidecar contract.

Approved sidecar contract base:

- Branch: `shared/pa-feitian-m3-decision-intent`
- Commit: `1da86a532f0dd15a065cc66a42559f0aa9fe9655`
- Commit URL: https://github.com/algotradinglife/paired-trading/commit/1da86a532f0dd15a065cc66a42559f0aa9fe9655

Out of scope for this review:

- Re-reviewing the already approved sidecar contract shape, except where
  strategy/frontend usage violates it.
- Live trading or order execution.
- Global promotion of v0.2 decision output to a production trading default.

## Local Absolute Paths

Repo root:

`/home/drwho1985/workspace/quant/strats/paired-trading`

Strategy worktree:

`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/strategy-m3-v02-adapter`

Frontend worktree:

`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/frontend-m3-decision-review`

Review packet worktree:

`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/m3-output-review`

## Strategy Output

Branch:

`strategy/pa-feitian-m3-v02-adapter`

Commit:

`dfb739025adde4be54563956ef7f6aea9152e364`

Commit URL:

https://github.com/algotradinglife/paired-trading/commit/dfb739025adde4be54563956ef7f6aea9152e364

Delta from approved sidecar base:

https://github.com/algotradinglife/paired-trading/compare/1da86a532f0dd15a065cc66a42559f0aa9fe9655...dfb739025adde4be54563956ef7f6aea9152e364

Changed files:

- `src/engine/pa_feitian/__init__.py`
- `src/engine/pa_feitian/decision_intent_adapter.py`
- `src/scripts/emit_pa_feitian_snapshot.py`
- `src/tests/test_pa_feitian_decision_intent_adapter.py`

Summary:

- Adds a focused v0.2 strategy adapter that emits
  `pa_feitian_decision_intent_v1` sidecar artifacts.
- Wires the producer CLI with explicit `--decision-intent-out` support.
- Attaches the sidecar artifact to the run manifest through
  `decision_intent_artifact`.
- Keeps snapshot v0/v1 schemas and models unchanged.
- Covers stop-clear downgrade, armed_watch/trade_ready, AU-call 4%-12% premium
  stop-distance soft gate, half_loss_fixed downgrade, MACD alert-only guard,
  thin/stale right-tail observation, product-direction split, no-lookahead
  checks, and sidecar hash validation.

Verification:

From:

`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/strategy-m3-v02-adapter/src`

Commands:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/ruff check \
  engine/pa_feitian \
  scripts/emit_pa_feitian_snapshot.py \
  tests/test_pa_feitian_decision_intent_adapter.py \
  tests/test_pa_feitian_decision_intent.py \
  tests/test_pa_feitian_manifest.py
```

Result: passed.

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest \
  tests/test_pa_feitian_contract.py \
  tests/test_pa_feitian_scorecard_producer.py \
  tests/test_pa_feitian_decision_intent_adapter.py \
  tests/test_pa_feitian_decision_intent.py \
  tests/test_pa_feitian_manifest.py \
  -q
```

Result: 33 passed.

```bash
git diff --check
```

Result: clean.

Environment note:

Use the project venv at
`/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python`.
`uv run` inside nested worktrees can resolve the local `quant-cli` path
incorrectly in this repo layout.

## Frontend Output

Branch:

`frontend/pa-feitian-m3-decision-review`

Commit:

`2791a1c838c3ebf3dd08ebfcabf7e8a044b1bcd7`

Commit URL:

https://github.com/algotradinglife/paired-trading/commit/2791a1c838c3ebf3dd08ebfcabf7e8a044b1bcd7

Delta from approved sidecar base:

https://github.com/algotradinglife/paired-trading/compare/1da86a532f0dd15a065cc66a42559f0aa9fe9655...2791a1c838c3ebf3dd08ebfcabf7e8a044b1bcd7

Changed files:

- `frontend/pa-feitian-dashboard/README.md`
- `frontend/pa-feitian-dashboard/app.mjs`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_run_manifest_v1.json`
- `frontend/pa-feitian-dashboard/styles.css`
- `frontend/pa-feitian-dashboard/test/dashboard-smoke.test.mjs`

Summary:

- Adds a copied dashboard sidecar fixture.
- Updates the dashboard manifest fixture to reference
  `decision_intent_artifact`.
- Loads sidecar artifacts only through manifest paths.
- Renders decision_state, execution_allowed, reason codes, premium stop,
  confirmation, liquidity, product direction, and no-lookahead input refs.
- Adds defensive rendering for missing sidecars, missing per-signal intents,
  observation-only states, blocked states, and posterior-diagnostic warnings.
- Keeps existing v0/v1 snapshot fallback behavior.
- Does not read raw data pipelines or import strategy internals.

Verification:

From:

`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/frontend-m3-decision-review/frontend/pa-feitian-dashboard`

Commands:

```bash
npm run smoke
```

Result: 11 passed.

```bash
git diff --check
```

Result: clean.

## Review Questions

Please review for:

1. Whether the strategy adapter correctly uses the approved
   `pa_feitian_decision_intent_v1` sidecar without mutating snapshot v0/v1
   semantics.
2. Whether the v0.2 decision states and gating behavior are coherent:
   `trade_ready`, `armed_watch`, `observation_runner`, `reject`,
   `execution_allowed`, product-direction tier, premium-stop clarity,
   confirmation, liquidity, and reason codes.
3. Whether no-lookahead and digest coverage is sufficient for M3.
4. Whether the manifest linkage and output hash validation are sufficient for
   integration.
5. Whether the frontend remains artifact-only and provides enough reviewer
   surface for decision-chain inspection.
6. Whether M3-INTEG-001 may proceed, or whether repair cards are required first.

## Expected Verdict Format

Please respond with one of:

- `APPROVE_M3_INTEG`
- `APPROVE_M3_INTEG_WITH_NON_BLOCKING_FOLLOWUPS`
- `REQUEST_STRATEGY_REPAIR`
- `REQUEST_FRONTEND_REPAIR`
- `REQUEST_BOTH_REPAIR`

If requesting repair, include blocking findings with file/path/behavior and the
required repair scope.

## Current Integration Gate

`M3-INTEG-001` remains blocked until this review returns an approving verdict.

