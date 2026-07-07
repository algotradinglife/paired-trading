# PA / Feitian Review Packet

Date: 2026-07-08
Repo: `algotradinglife/paired-trading`
Coordination branch: `coordination/pa-feitian-design-review`

## Purpose

This packet asks for an external architecture and integration review before
merging the first PA / Feitian strategy and frontend work back toward main.

The current milestone quantifies the first subjective decision-chain boundary:

```text
strategy score_today output -> pa_feitian_snapshot_v0 -> read-only dashboard
```

The goal is not full automation yet. The goal is a reproducible, inspectable
baseline that preserves the distinction between:

- underlying PA signal evidence
- option premium timing evidence
- IV-regime gating
- missing-data / model-dominated defensive states
- future realized outcome fields

## Branches Under Review

| Branch | Commit | Role |
|---|---:|---|
| `shared/pa-feitian-contract-v0` | `24edae80331ef9788ecd2650a4ef40b0d9d9281b` | Shared snapshot contract, fixture, and baseline contract tests |
| `strategy/pa-feitian-v02` | `160fcf5da113a2cd50e390c1456358b7e2c4a01f` | Scorecard-backed PA / Feitian snapshot producer |
| `frontend/pa-feitian-dashboard` | `06d145953e786cbbbb26c2c88647f4da72caf1c1` | Read-only dashboard shell consuming the committed fixture |
| `coordination/pa-feitian-design-review` | `f8d0b796005250161fec3c3a60e699ea523b7aba` before this packet | Planning and orchestration docs only |

Base anchor:

```text
baseline/paired-trading-v01 @ 50b3cf92f4058f4fcaf521784600bbd5a55cf8ab
```

## Worktree / Session Model

Project root:

```text
/home/drwho1985/workspace/quant/strats/paired-trading
```

Implementation worktrees:

```text
.worktrees/strategy       -> strategy/pa-feitian-v02       -> strategy-session
.worktrees/frontend       -> frontend/pa-feitian-dashboard -> frontend-session
.worktrees/shared-contract -> shared/pa-feitian-contract-v0
.worktrees/coordination   -> coordination/pa-feitian-design-review
```

Hermes board:

```text
paired-trading
```

Completed cards for this packet:

- `CONTRACT-001` / `t_647424df`: shared contract v0
- `STRAT-001A` / `t_35e2082d`: scorecard-backed producer implementation
- `FE-001A` / `t_2c4dd564`: read-only dashboard shell
- `COORD-002` / `t_cf8e7615`: coordinator diff review before commit
- `STRAT-001B` / `t_3ccfccee`: strategy commit and push
- `FE-001B` / `t_fc239cc6`: frontend commit and push

## Shared Contract Summary

Contract files:

```text
doc/schemas/pa_feitian_snapshot_v0.schema.json
src/engine/pa_feitian/contract.py
src/scripts/emit_pa_feitian_snapshot.py
src/tests/fixtures/pa_feitian_snapshot_v0.json
src/tests/test_pa_feitian_contract.py
```

Contract principles:

- Top-level schema version is `pa_feitian_snapshot_v0`.
- Status enum is `keep`, `drop`, `advisory`, `data_blocked`, `model_dominated`.
- Underlying and option outcomes are not collapsed into one generic `r` field.
- Explicit outcome slots are used:
  - `underlying_r_outcome`
  - `premium_r_outcome`
  - `option_runner_outcome`
  - `proxy_outcome`
- The fixture intentionally contains advisory and data-blocked examples.

## Strategy Branch Summary

Branch:

```text
strategy/pa-feitian-v02 @ 160fcf5da113a2cd50e390c1456358b7e2c4a01f
```

Commit:

```text
160fcf5 feat(strategy): emit PA/Feitian snapshot from scorecard
```

Changed files relative to shared contract:

```text
M src/engine/pa_feitian/__init__.py
M src/engine/pa_feitian/contract.py
M src/scripts/emit_pa_feitian_snapshot.py
A src/tests/test_pa_feitian_scorecard_producer.py
```

What changed:

- Added `snapshot_from_scorecard()` and `snapshot_from_scorecard_file()`.
- Added `emit_pa_feitian_snapshot.py --scorecard <score_today.json>`.
- Producer consumes existing score_today JSON records with `options_calls`.
- Producer selects one option leg, annotates IV regime, and emits
  `pa_feitian_snapshot_v0`.
- Producer does not scan raw market data and does not mutate pipeline state.
- Added focused producer tests covering:
  - scorecard conversion
  - option leg selection
  - IV warmup / keep path
  - write/load validation
  - CLI conversion path

Verification recorded:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest src/tests/test_pa_feitian_contract.py src/tests/test_pa_feitian_scorecard_producer.py
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m ruff check src/engine/pa_feitian src/scripts/emit_pa_feitian_snapshot.py src/tests/test_pa_feitian_contract.py src/tests/test_pa_feitian_scorecard_producer.py
git diff --check
```

Observed result:

```text
8 passed
ruff passed
git diff --check clean
working tree clean after push
```

## Frontend Branch Summary

Branch:

```text
frontend/pa-feitian-dashboard @ 06d145953e786cbbbb26c2c88647f4da72caf1c1
```

Commit:

```text
06d1459 feat(frontend): add pa feitian dashboard shell
```

Changed files relative to shared contract:

```text
A frontend/pa-feitian-dashboard/README.md
A frontend/pa-feitian-dashboard/app.mjs
A frontend/pa-feitian-dashboard/dev-server.mjs
A frontend/pa-feitian-dashboard/index.html
A frontend/pa-feitian-dashboard/package.json
A frontend/pa-feitian-dashboard/styles.css
A frontend/pa-feitian-dashboard/test/dashboard-smoke.test.mjs
```

What changed:

- Added a static read-only dashboard shell.
- The dashboard fetches only:

```text
src/tests/fixtures/pa_feitian_snapshot_v0.json
```

- It renders:
  - summary metrics
  - status overview
  - warnings
  - data quality fields
  - signal table
  - signal drill-down
  - missing optional fields
  - empty-signal state
- Smoke tests check that frontend files do not reference raw data pipeline paths
  or strategy internals.

Verification recorded:

```bash
cd frontend/pa-feitian-dashboard && npm run smoke
git ls-remote origin refs/heads/frontend/pa-feitian-dashboard
git status --short
```

Observed result:

```text
4 passing Node tests
remote branch points to 06d145953e786cbbbb26c2c88647f4da72caf1c1
working tree clean after push
```

Local run:

```bash
cd frontend/pa-feitian-dashboard
npm run serve
```

Open:

```text
http://127.0.0.1:4173/frontend/pa-feitian-dashboard/
```

## Coordinator Review Findings

No blocking findings before commit/push.

Strategy:

- Scope is contained to PA / Feitian contract, producer CLI, and focused tests.
- The producer consumes score_today output and does not read raw data stores.
- Contract load/write path remains covered.
- Integration must run contract and producer tests together because
  `contract.py` now imports `engine.options.iv_regime`.

Frontend:

- Scope is contained to `frontend/pa-feitian-dashboard`.
- It consumes the snapshot fixture contract only.
- It does not touch strategy implementation files.
- Smoke tests cover defensive states and empty-signal rendering.

Non-blocking notes:

- Frontend labels still say "fixture" in a few places. This is acceptable for
  FE-001A, but should be generalized once the dashboard reads real producer
  output.
- The local repo had no Git identity configured. The strategy commit used the
  existing repo author identity from prior commits. The frontend commit used
  `frontend-session <frontend-session@local>`. Decide whether to standardize
  repo-local Git identity before final PR history is frozen.

## Review Questions

Please review the following before the integration branch is created:

1. Is `pa_feitian_snapshot_v0` still the right contract boundary, or has the
   strategy producer already pulled too much domain logic into
   `src/engine/pa_feitian/contract.py`?
2. Should scorecard-to-snapshot conversion remain in `contract.py`, or should it
   move to a producer module while `contract.py` stays pure validation/types?
3. Is the frontend correctly constrained to consume snapshot artifacts only?
4. Are `data_blocked` and `model_dominated` represented clearly enough for
   subjective trading decision review?
5. Before integration, should we require a real generated
   `pa_feitian_snapshot_v0.json` artifact from a committed score_today sample,
   or is the deterministic scorecard unit fixture enough for this milestone?
6. Should the integration branch target `baseline/paired-trading-v01` first, or
   should baseline be promoted to `main` before merging PA / Feitian work?

## Proposed Integration Order

If review does not find blockers:

```text
integration/pa-feitian-v02-m1
  base: baseline/paired-trading-v01 or promoted main
  merge 1: shared/pa-feitian-contract-v0
  merge 2: strategy/pa-feitian-v02
  merge 3: frontend/pa-feitian-dashboard
```

Integration checks:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest src/tests/test_pa_feitian_contract.py src/tests/test_pa_feitian_scorecard_producer.py
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m ruff check src/engine/pa_feitian src/scripts/emit_pa_feitian_snapshot.py src/tests/test_pa_feitian_contract.py src/tests/test_pa_feitian_scorecard_producer.py
cd frontend/pa-feitian-dashboard && npm run smoke
git diff --check
```

Expected integration risks:

- Git history is branched from `baseline/paired-trading-v01`, which is ahead of
  `main`. Main-target PRs may include baseline history unless baseline is
  promoted or explicitly treated as the PA / Feitian base.
- `uv run` from nested `.worktrees/.../src` currently mis-resolves the
  `quant-cli` path in `src/pyproject.toml`; use the project venv Python command
  above until pathing is fixed.
- Frontend currently reads the committed fixture, not a generated strategy
  artifact. That is intentional for FE-001A but should be upgraded in the next
  milestone.
