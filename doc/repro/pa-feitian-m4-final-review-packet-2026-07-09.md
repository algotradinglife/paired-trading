# PA/Feitian M4 Final Review Packet

Date: 2026-07-09

Repository: https://github.com/algotradinglife/paired-trading

Pull request: https://github.com/algotradinglife/paired-trading/pull/14

Base: `main`

Head: `integration/pa-feitian-v02-m4`

## Requested Review

Please review M4 as a milestone completion gate.

Expected verdict format:

- `APPROVE_M4_FINAL` if no blocking findings remain.
- Otherwise list blocking findings with exact file paths and required repairs.

## M4 Objective

Create a reproducible daily PA/Feitian review artifact loop:

```text
score_today artifact or deterministic fixture fallback
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1
  -> copied dashboard fixtures
  -> renderDashboard(snapshot, manifest, decisionIntent)
```

Non-goals:

- no live trading
- no order execution
- no raw market data scan from the frontend
- no promotion of decision-intent sidecar into snapshot v2

## Integrated Branches

Merge order followed:

1. `strategy/pa-feitian-m4-score-today-intake`
   - Commit: `89c98d6 Add deterministic score_today artifact intake`
2. `pipeline/pa-feitian-m4-review-build`
   - Commit: `d31b7d1 Build PA Feitian review artifacts in one command`
3. `frontend/pa-feitian-m4-review-ops`
   - Commit: `2162b21 Surface PA Feitian review operations metadata`

The integration branch is a fast-forward stack on top of `main` commit `83971a2`.

## Files To Review

Strategy intake:

- `src/engine/pa_feitian/score_today_intake.py`
- `src/scripts/emit_pa_feitian_snapshot.py`
- `src/tests/test_pa_feitian_score_today_intake.py`
- `src/tests/test_pa_feitian_scorecard_producer.py`

Pipeline builder and generated review artifacts:

- `src/scripts/build_pa_feitian_review_artifacts.py`
- `src/tests/test_pa_feitian_review_artifact_builder.py`
- `src/tests/fixtures/pa_feitian_scorecard_v1.json`
- `src/tests/fixtures/pa_feitian_snapshot_v1.json`
- `src/tests/fixtures/pa_feitian_run_manifest_v1.json`
- `src/tests/fixtures/pa_feitian_run_manifest_with_decision_intent_v1.json`
- `src/tests/fixtures/pa_feitian_decision_intent_v1.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_run_manifest_v1.json`
- `frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json`

Decision-intent adapter adjustment:

- `src/engine/pa_feitian/decision_intent_adapter.py`

Frontend review operations view:

- `frontend/pa-feitian-dashboard/app.mjs`
- `frontend/pa-feitian-dashboard/styles.css`
- `frontend/pa-feitian-dashboard/test/dashboard-smoke.test.mjs`
- `frontend/pa-feitian-dashboard/README.md`

This review packet:

- `doc/repro/pa-feitian-m4-final-review-packet-2026-07-09.md`

## Acceptance Evidence

Commands run from `/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/integration-m4`:

```bash
.pa-feitian-venv/bin/python -m pytest \
  src/tests/test_pa_feitian_contract.py \
  src/tests/test_pa_feitian_manifest.py \
  src/tests/test_pa_feitian_decision_intent.py \
  src/tests/test_pa_feitian_decision_intent_adapter.py \
  src/tests/test_pa_feitian_scorecard_producer.py \
  src/tests/test_pa_feitian_score_today_intake.py \
  src/tests/test_pa_feitian_review_artifact_builder.py \
  src/tests/test_pa_feitian_e2e_smoke.py \
  -q
```

Result: `42 passed in 2.65s`

```bash
cd frontend/pa-feitian-dashboard && npm run smoke
```

Result: `12 passed`

```bash
.pa-feitian-venv/bin/python -m ruff check \
  src/engine/pa_feitian \
  src/scripts/emit_pa_feitian_snapshot.py \
  src/scripts/build_pa_feitian_review_artifacts.py \
  src/tests/test_pa_feitian_contract.py \
  src/tests/test_pa_feitian_manifest.py \
  src/tests/test_pa_feitian_decision_intent.py \
  src/tests/test_pa_feitian_decision_intent_adapter.py \
  src/tests/test_pa_feitian_scorecard_producer.py \
  src/tests/test_pa_feitian_score_today_intake.py \
  src/tests/test_pa_feitian_review_artifact_builder.py \
  src/tests/test_pa_feitian_e2e_smoke.py
```

Result: passed

```bash
git diff --check
git diff --check origin/main...HEAD
diff -u src/tests/fixtures/pa_feitian_snapshot_v1.json \
  frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json
diff -u src/tests/fixtures/pa_feitian_decision_intent_v1.json \
  frontend/pa-feitian-dashboard/fixtures/pa_feitian_decision_intent_v1.json
```

Result: clean

Builder idempotency:

```bash
git diff > /tmp/pa_feitian_m4_integration_before.patch
.pa-feitian-venv/bin/python src/scripts/build_pa_feitian_review_artifacts.py \
  >/tmp/pa_feitian_m4_builder.out
git diff > /tmp/pa_feitian_m4_integration_after.patch
diff -u /tmp/pa_feitian_m4_integration_before.patch \
  /tmp/pa_feitian_m4_integration_after.patch
```

Result: clean

## Review Notes

- `pa_feitian_snapshot_v1` remains unchanged as the snapshot contract.
- Decision intent remains a manifest-referenced sidecar artifact.
- The frontend consumes only committed/copied JSON artifacts.
- `data_access.status` distinguishes `real_data_available`, `fixture_fallback`, `data_blocked`, and `unknown`.
- Synthetic or deterministic fixture paths use `fixture_fallback`; `real_data_available` is reserved for explicit score_today artifacts.
- The dashboard derives hash status and reviewer warnings from manifest and sidecar fields; it does not require backend mutation.
- The one-command builder is documented as:

```bash
python src/scripts/build_pa_feitian_review_artifacts.py
```

