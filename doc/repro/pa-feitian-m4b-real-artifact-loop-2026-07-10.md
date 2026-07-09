# PA / Feitian M4b Real Artifact Loop - 2026-07-10

Hermes card: `t_f56119fc`

Branch: `pipeline/pa-feitian-m4b-real-artifact-loop`

Generated artifact directory:
`doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/`

## Verdict

M4b pipeline evidence is green for a real historical score_today artifact:

```text
score_today CN_METAL real data root
  -> score_today JSON artifact
  -> pa_feitian_snapshot_v1
  -> pa_feitian_run_manifest_v1
  -> pa_feitian_decision_intent_v1
  -> copied dashboard artifacts
  -> renderDashboard(snapshot, { manifest, decisionIntent })
```

This is not a live-trading or order-execution path. The builder consumes an
explicit score_today JSON artifact and does not scan raw market stores.

## Important Context

Earlier M4b audit and repair docs reported `data_blocked` before the usable
real data root was identified. That old blocker is superseded for this packet
by the explicit root below:

```text
/mnt/c/Users/hhusl/quant_data
```

The nested worktree `uv run --project src ...` issue is still real and remains
an environment problem:

```text
error: Distribution not found at: file:///home/drwho1985/workspace/quant/strats/quant
```

For this packet, commands used the already-working paired-trading interpreter:

```text
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python
```

## Commands

Data coverage:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/check_data_coverage.py --root /mnt/c/Users/hhusl/quant_data
```

Real score_today artifact:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py \
  --pool CN_METAL \
  --quant-data-root /mnt/c/Users/hhusl/quant_data \
  --window-days 120 \
  -o doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/score_today_cn_metal_120d_2026-07-10.json
```

Strict review artifact builder:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/build_pa_feitian_review_artifacts.py \
  --score-today-artifact doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/score_today_cn_metal_120d_2026-07-10.json \
  --no-fixture-fallback \
  --source-fixture-dir doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source \
  --dashboard-fixture-dir doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/dashboard \
  --use-git-source-commit \
  --generated-at-utc 2026-07-10T00:00:00Z \
  --max-signals 20
```

Current/latest-window probe:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py \
  --pool CN_METAL \
  --quant-data-root /mnt/c/Users/hhusl/quant_data \
  --window-days 7 \
  -o /tmp/score_today_cn_metal_7d_2026-07-10.json
```

Verifier:

```bash
node doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/verify.mjs
```

## Results

`score_today` 120-day output:

- Pool: `CN_METAL`
- Instrument class: `cn_metal_futures`
- Window days: `120`
- Scored records: `13`
- Scored records with `options_calls`: `4`
- PA / Feitian snapshot signals: `4`
- Decision-intent sidecar intents: `4`
- Manifest `data_access.status`: `real_data_available`
- Option suggestions in the console output used store prices for ag/au contracts.

The 7-day latest-window probe loaded all four CN_METAL symbols but produced no
signals:

```text
No signals in last 7 days (4/4 symbols loaded).
```

The committed 120-day artifact is therefore a real historical demonstration
window, not a claim that the latest 7-day window has a current setup.

## Data Coverage Notes

`check_data_coverage.py --root /mnt/c/Users/hhusl/quant_data` exits cleanly for
required items, with stale continuous-series warnings around the current
2026-07-10 date:

- `SHFE.cu`: stale end at `2026-06-08`
- `SHFE.au`: stale end at `2026-06-08`
- `SHFE.ag`: stale end at `2026-06-08`
- `INE.sc`: stale end at `2026-06-12`
- `ag` options: `3167` contracts, history from `2023-12-29`
- `au` options: `1768` contracts, history from `2023-11-22`
- Required coverage verdict: `PASS: 0 required item(s) missing`

## Verification Surface

`verify.mjs` checks:

- scorecard row counts and PA / Feitian candidate counts
- source snapshot / source sidecar contract versions and counts
- source-to-dashboard snapshot and sidecar copy equality
- source and dashboard manifest hash links
- frontend copy hash equality
- `buildDashboardModel` with manifest and decision-intent sidecar
- `renderDashboard(snapshot, { manifest, decisionIntent })`
- reviewer-facing sidecar hash status is `match`

Expected verifier summary:

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

Schema load check:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python - <<'PY'
from pathlib import Path
from engine.pa_feitian.contract import load_decision_intent, load_snapshot_v1
from engine.pa_feitian.manifest import load_run_manifest
root = Path('doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10')
load_snapshot_v1(root / 'source' / 'pa_feitian_snapshot_v1.json')
load_decision_intent(root / 'source' / 'pa_feitian_decision_intent_v1.json')
load_run_manifest(root / 'source' / 'pa_feitian_run_manifest_v1.json')
load_run_manifest(root / 'source' / 'pa_feitian_run_manifest_with_decision_intent_v1.json')
load_snapshot_v1(root / 'dashboard' / 'pa_feitian_snapshot_v1.json')
load_decision_intent(root / 'dashboard' / 'pa_feitian_decision_intent_v1.json')
load_run_manifest(root / 'dashboard' / 'pa_feitian_run_manifest_v1.json')
print('generated artifact schema load ok')
PY
```

Result: `generated artifact schema load ok`.

Focused checks:

```bash
/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m ruff check \
  src/scripts/score_today.py src/tests/test_score_today_option_root_wiring.py

/home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest \
  src/tests/test_score_today_option_root_wiring.py \
  src/tests/test_pa_feitian_review_artifact_builder.py \
  src/tests/test_pa_feitian_e2e_smoke.py

cd frontend/pa-feitian-dashboard && npm run smoke
```

Results:

- ruff: `All checks passed!`
- pytest: `6 passed`
- frontend smoke: `12 passed`

## Follow-ups

- The full roadmap M4 still needs continued real daily score_today operation
  once fresh data extends beyond the 2026-06-08/12 stale continuous-series end.
- M5 remains separate: premium-space outcome harness, including option premium
  R and exit-policy evaluation.
