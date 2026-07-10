# PA / Feitian M4b Final Review Packet - 2026-07-10

Hermes card: `t_1b15b3db`

Branch: `integration/pa-feitian-v02-m4b`

Base: `main`

## Review Ask

Please review M4b for final acceptance.

M4b objective:

```text
current data interfaces
  -> real score_today artifact
  -> M4a builder
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1 sidecar
  -> dashboard render
```

This milestone does not implement M5 premium-space outcome harness, live
trading, order execution, or automated execution.

## Merge Order

1. `coordination/pa-feitian-m4b-roadmap` (`24b803e`)
2. `data/pa-feitian-m4b-score-today-audit` (`36a0db8`)
3. `strategy/pa-feitian-m4b-real-score-today` (`d7a71db`)
4. `pipeline/pa-feitian-m4b-real-artifact-loop` (`9ffe596`)

## Scope Summary

M4b adds the real data path needed after M4a:

- Documents the roadmap reconciliation: M4a was the reproducible artifact
  loop; M4b is the real score_today production path.
- Audits `score_today` data interfaces and records the earlier blocked state.
- Repairs `score_today` option root wiring so `--quant-data-root` is forwarded
  into ag/au option selector and IV enrichment paths.
- Adds `--ag-options-data-dir` and `--au-options-data-dir` legacy JSON override
  flags.
- Commits a real historical CN_METAL score_today artifact and the downstream
  PA / Feitian snapshot, manifest, decision-intent sidecar, dashboard copies,
  and verifier under:

```text
doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/
```

## Real Data Evidence

The usable data root is:

```text
/mnt/c/Users/hhusl/quant_data
```

Data coverage check:

```text
PASS: 0 required item(s) missing
```

Important warnings:

- Required CN continuous series are stale relative to 2026-07-10:
  `SHFE.cu`, `SHFE.au`, and `SHFE.ag` end at `2026-06-08`; `INE.sc` ends at
  `2026-06-12`.
- ag options: `3167` contracts, history from `2023-12-29`.
- au options: `1768` contracts, history from `2023-11-22`.

Latest 7-day probe:

```text
No signals in last 7 days (4/4 symbols loaded).
```

The committed 120-day artifact is therefore a real historical demonstration
window, not a claim of a current 7-day setup.

## Committed Artifact Evidence

Command:

```bash
node doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/verify.mjs
```

Result:

```json
{
  "ok": true,
  "scorecard_rows": 13,
  "scorecard_rows_with_options": 4,
  "snapshot_signals": 4,
  "decision_intents": 4,
  "data_access": "real_data_available",
  "snapshot_mode": "generated",
  "sidecar_hash_status": "match",
  "html_length": 100831
}
```

The verifier checks scorecard counts, source/dashboard copy equality, manifest
hash links, frontend copy hashes, `buildDashboardModel`, and
`renderDashboard(snapshot, { manifest, decisionIntent })`.

## Integration Rebuild Evidence

The integration branch also reran the real data path into `/tmp` from the
current HEAD:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py \
  --pool CN_METAL \
  --quant-data-root /mnt/c/Users/hhusl/quant_data \
  --window-days 120 \
  -o /tmp/pa_feitian_m4b_integration_smoke_score_today.json
```

Result:

- 13 scored records
- 4 ag/au option suggestion groups
- option prices sourced from store data

Strict builder:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/build_pa_feitian_review_artifacts.py \
  --score-today-artifact /tmp/pa_feitian_m4b_integration_smoke_score_today.json \
  --no-fixture-fallback \
  --source-fixture-dir /tmp/pa_feitian_m4b_integration_smoke/source \
  --dashboard-fixture-dir /tmp/pa_feitian_m4b_integration_smoke/dashboard \
  --use-git-source-commit \
  --generated-at-utc 2026-07-10T00:00:00Z \
  --max-signals 20
```

Dashboard runtime smoke:

```json
{
  "signals": 4,
  "intents": 4,
  "snapshotMode": "generated",
  "dataAccess": "real_data_available",
  "decisionStatus": "loaded",
  "sidecarHashStatus": "match",
  "htmlLength": 100357
}
```

## Checks

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m ruff check \
  src/scripts/score_today.py src/tests/test_score_today_option_root_wiring.py
```

Result: `All checks passed!`

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest \
  src/tests/test_score_today_option_root_wiring.py \
  src/tests/test_pa_feitian_review_artifact_builder.py \
  src/tests/test_pa_feitian_e2e_smoke.py
```

Result: `6 passed`

```bash
cd frontend/pa-feitian-dashboard && npm run smoke
```

Result: `12 passed`

```bash
git diff --check
```

Result: clean

## Known Caveats

- `uv run --project src ...` remains blocked in nested worktrees by the local
  editable dependency path:

  ```text
  error: Distribution not found at: file:///home/drwho1985/workspace/quant/strats/quant
  ```

- The earlier M4b audit and repair docs record `data_blocked` before
  `/mnt/c/Users/hhusl/quant_data` was identified. The pipeline evidence packet
  supersedes that blocker for this M4b review.
- Fresh daily operation still depends on data extending beyond the current
  stale continuous-series end dates.

## Non-goals Preserved

- no live trading
- no order execution
- no frontend raw market scan
- no promotion of decision intent into snapshot v2
- no M5 premium-space outcome evaluation
