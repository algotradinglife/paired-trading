# PA / Feitian M2 Review Packet

Date: 2026-07-08

This packet is for ChatGPT review before `M2-INTEG-001`. Do not start integration until the review verdict explicitly approves or records no blockers.

## Objective

M2 creates a reproducible artifact path:

```text
score_today JSON artifact
-> pa_feitian_snapshot_v1
-> pa_feitian_run_manifest_v1
-> copied dashboard snapshot
-> reviewer-facing trace/provenance drill-down
```

M2 remains non-trading:

- no live trading
- no order execution
- no persistent reviewer override database
- no producer default switch to v1
- no raw market data pipeline mutation

## PR Stack

Review in this order.

| PR | Branch | Base | Commit | Purpose |
| --- | --- | --- | --- | --- |
| #8 | `shared/pa-feitian-m2-manifest` | `main` | `cb96cb4` | Run manifest schema/model/helpers and schema validation |
| #9 | `strategy/pa-feitian-m2-real-scorecard-artifact` | `shared/pa-feitian-m2-manifest` | `e51fbcb` | Explicit scorecard -> v1 snapshot -> manifest producer path |
| #10 | `frontend/pa-feitian-m2-generated-review-mode` | `strategy/pa-feitian-m2-real-scorecard-artifact` | `d938382` | Dashboard generated/review labels, manifest panel, trace input refs |

PR links:

- https://github.com/algotradinglife/paired-trading/pull/8
- https://github.com/algotradinglife/paired-trading/pull/9
- https://github.com/algotradinglife/paired-trading/pull/10

## Changed Files

Shared / PR #8:

- `doc/schemas/pa_feitian_run_manifest_v1.schema.json`
- `src/engine/pa_feitian/manifest.py`
- `src/engine/pa_feitian/schema_validation.py`
- `src/engine/pa_feitian/__init__.py`
- `src/tests/fixtures/pa_feitian_scorecard_v1.json`
- `src/tests/fixtures/pa_feitian_run_manifest_v1.json`
- `src/tests/test_pa_feitian_manifest.py`

Strategy / PR #9:

- `src/scripts/emit_pa_feitian_snapshot.py`
- `src/tests/test_pa_feitian_scorecard_producer.py`

Frontend / PR #10:

- `frontend/pa-feitian-dashboard/app.mjs`
- `frontend/pa-feitian-dashboard/styles.css`
- `frontend/pa-feitian-dashboard/test/dashboard-smoke.test.mjs`

## Artifact Contract

Primary deterministic fixtures:

- Scorecard fixture: `src/tests/fixtures/pa_feitian_scorecard_v1.json`
- Snapshot fixture: `src/tests/fixtures/pa_feitian_snapshot_v1.json`
- Run manifest fixture: `src/tests/fixtures/pa_feitian_run_manifest_v1.json`
- Dashboard copied snapshot fixture: `frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json`

Manifest v1 records:

- `scorecard_artifact`: kind/path/sha256/schema/content type
- `snapshot_artifact`: kind/path/sha256/schema/content type
- `cli_args`
- `run_config`
- top-level `data_access`
- `input_hashes`
- `output_hashes`
- `frontend_copy_path`
- `review_state`

`data_access.status` values:

- `real_data_available`
- `fixture_fallback`
- `data_blocked`
- `unknown`

## Producer Path

The producer remains `src/scripts/emit_pa_feitian_snapshot.py`.

Existing behavior remains:

- No `--manifest-out`: default snapshot contract remains `pa_feitian_snapshot_v0`.
- Existing `--scorecard` conversion still works for v0 and explicit v1.

M2 behavior is opt-in:

```bash
python src/scripts/emit_pa_feitian_snapshot.py \
  --out /tmp/pa_feitian_snapshot_v1.json \
  --scorecard src/tests/fixtures/pa_feitian_scorecard_v1.json \
  --source-commit cccccccccccccccccccccccccccccccccccccccc \
  --generated-at-utc 2026-07-07T00:00:00Z \
  --contract-version pa_feitian_snapshot_v1 \
  --manifest-out /tmp/pa_feitian_run_manifest_v1.json \
  --frontend-copy /tmp/dashboard/pa_feitian_snapshot_v1.json \
  --data-access-status fixture_fallback
```

`--manifest-out` requires explicit `--contract-version pa_feitian_snapshot_v1`.

If `--manifest-out` is provided without `--scorecard`, the producer uses the committed deterministic scorecard fixture and records `data_access.status=fixture_fallback`.

If a scorecard artifact is provided and no explicit status is passed, `data_access.status` defaults to `real_data_available`; this classifies the artifact availability, not a raw-data scan by the PA/Feitian producer.

## Frontend Path

The dashboard still consumes copied snapshot artifacts only.

New rendering behavior:

- fixture/generated/review snapshot labels
- defensive run-manifest empty state when manifest is absent
- run-manifest provenance panel when manifest is supplied
- scorecard/snapshot artifact refs and hashes
- source commit
- CLI args and run config summaries
- input/output hashes
- data access state
- frontend copy path
- review state
- decision_trace_v1 `input_refs` and digests in drill-down

No frontend source reads raw data pipeline files.

## Verification

Shared / PR #8:

```bash
PYTHONPATH=/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/shared-m2-manifest/src \
  /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  -m pytest \
  src/tests/test_pa_feitian_contract.py \
  src/tests/test_pa_feitian_scorecard_producer.py \
  src/tests/test_pa_feitian_manifest.py \
  src/tests/test_pa_feitian_e2e_smoke.py -q
```

Result: `19 passed`.

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  -m ruff check \
  src/engine/pa_feitian/__init__.py \
  src/engine/pa_feitian/manifest.py \
  src/engine/pa_feitian/schema_validation.py \
  src/tests/test_pa_feitian_manifest.py
```

Result: passed.

Strategy / PR #9:

```bash
PYTHONPATH=/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/strategy-m2-scorecard/src \
  /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  -m pytest \
  src/tests/test_pa_feitian_contract.py \
  src/tests/test_pa_feitian_scorecard_producer.py \
  src/tests/test_pa_feitian_manifest.py \
  src/tests/test_pa_feitian_e2e_smoke.py -q
```

Result: `21 passed`.

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  -m ruff check \
  src/scripts/emit_pa_feitian_snapshot.py \
  src/tests/test_pa_feitian_scorecard_producer.py
```

Result: passed.

Frontend / PR #10:

```bash
cd frontend/pa-feitian-dashboard && npm run smoke
```

Result: `8 passed`.

All branches:

```bash
git diff --check
```

Result: clean on each branch.

## Known Risks

- PRs are intentionally stacked draft PRs; integration has not started.
- `schema_validation.py` is a deterministic local JSON Schema subset validator with external ref resolution by schema filename. It is not a general-purpose replacement for the `jsonschema` package.
- Manifest paths for temporary CLI runs may be absolute when artifacts live outside the repo. Committed fixture paths remain deterministic.
- The scorecard fixture is deterministic and score_today-shaped, but M2 does not require a real live market score_today artifact.
- `decision_trace_v1` remains a shadow representation; it is not a final reviewer override/adjudication ledger.

## Review Questions For ChatGPT

Please review PRs #8, #9, and #10 plus this packet.

Return one of:

- `APPROVE / unblock M2-INTEG-001`
- `APPROVE WITH NON-BLOCKING FOLLOW-UPS`
- `BLOCK`

Focus areas:

- Does `pa_feitian_run_manifest_v1` tie scorecard, snapshot, source commit, CLI/config, hashes, frontend copy, data access, and review state coherently?
- Is the local JSON Schema validation boundary acceptable for M2, including external ref validation from snapshot v1 to decision trace v1?
- Does strategy preserve v0 default behavior and require explicit v1 for manifest emission?
- Is `data_access` classification clear enough for fixture fallback vs existing score_today artifact?
- Does frontend clearly distinguish fixture, generated, and review modes?
- Does frontend render manifest provenance and trace input refs/digests without depending on raw data pipeline files?
- Are there any blockers before creating `integration/pa-feitian-v02-m2`?

## Gate State

`M2-INTEG-001` must remain parked until ChatGPT returns an approving verdict.

If approved, integration order should be:

1. `shared/pa-feitian-m2-manifest`
2. `strategy/pa-feitian-m2-real-scorecard-artifact`
3. `frontend/pa-feitian-m2-generated-review-mode`

If blocked, create repair cards against the owning workstream before integration.
