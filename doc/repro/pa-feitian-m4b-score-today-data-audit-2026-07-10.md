# PA / Feitian M4b score_today Data Interface Audit - 2026-07-10

Hermes card: `t_5d6d2477`

Worktree:
`/home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/data-m4b-score-today-audit`

Branch: `data/pa-feitian-m4b-score-today-audit`

## Verdict

`data_access.status`: `data_blocked` for real PA / Feitian M4b artifact
production in this worktree.

A real M4b artifact requires a real `score_today` JSON scorecard first. The
current worktree cannot emit that scorecard because no CN_METAL underlying bars
are loadable from the default BarStore root or legacy JSON fallback. The normal
`uv run` command is also blocked in this nested worktree by a broken local
`quant-cli` path dependency.

The PA / Feitian producer path itself works, but only via deterministic fixture
fallback unless an existing real `score_today` JSON artifact is supplied.

## Entry Points

### score_today producer

Main file: `src/scripts/score_today.py`

Supported pool entry point:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py --pool CN_METAL --window-days 7 \
  -o runs/pa-feitian/m4b/2026-07-10/score_today_cn_metal.json
```

Normal intended repo command after the worktree `uv` dependency is repaired:

```bash
uv run --project src python src/scripts/score_today.py --pool CN_METAL --window-days 7 \
  -o runs/pa-feitian/m4b/2026-07-10/score_today_cn_metal.json
```

CLI flags audited:

- `--pool {CN,CN_BOND,CN_COMMODITY,CN_METAL,US}` or `--symbols ...`
- `--instrument-class {us_equity,cn_futures,cn_index_futures,czce,cn_metal_futures,cn_bond}`
- `--bars-dir`, default `src/data/raw`
- `--quant-data-root`, default `src/data/quant`
- `--window-days`
- `-o/--output`
- `--include-dif-detectors`

Relevant code references:

- Pools and classes: `src/scripts/score_today.py:96`
- Data roots: `src/scripts/score_today.py:59`
- CLI flags: `src/scripts/score_today.py:827`
- JSON output write: `src/scripts/score_today.py:1742`

`CN_METAL` symbols are:

- `kq_m_shfe_cu`
- `kq_m_shfe_au`
- `kq_m_shfe_ag`
- `kq_m_ine_sc`

PA / Feitian M4b relevance is narrower than the full scorecard: only ag/au
bottom signals with non-empty `options_calls` become PA / Feitian candidates.
The producer ignores scorecard records without `options_calls`.

### PA / Feitian snapshot producer

Main file: `src/scripts/emit_pa_feitian_snapshot.py`

Real artifact command intended after a real score_today JSON exists:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/emit_pa_feitian_snapshot.py \
  --score-today-artifact runs/pa-feitian/m4b/2026-07-10/score_today_cn_metal.json \
  --contract-version pa_feitian_snapshot_v1 \
  --out runs/pa-feitian/m4b/2026-07-10/pa_feitian_snapshot_v1.json \
  --manifest-out runs/pa-feitian/m4b/2026-07-10/pa_feitian_run_manifest_v1.json \
  --decision-intent-out runs/pa-feitian/m4b/2026-07-10/pa_feitian_decision_intent_v1.json \
  --data-access-status real_data_available \
  --data-access-source runs/pa-feitian/m4b/2026-07-10/score_today_cn_metal.json
```

Relevant code references:

- Existing scorecard artifact flags: `src/scripts/emit_pa_feitian_snapshot.py:106`
- Manifest data-access flags: `src/scripts/emit_pa_feitian_snapshot.py:175`
- Fixture fallback is allowed only for manifest runs without artifact selectors:
  `src/scripts/emit_pa_feitian_snapshot.py:214`
- Manifest data-access write: `src/scripts/emit_pa_feitian_snapshot.py:268`

### PA / Feitian review artifact builder

Main file: `src/scripts/build_pa_feitian_review_artifacts.py`

Use this for dashboard fixture handoff once a real scorecard exists:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/build_pa_feitian_review_artifacts.py \
  --score-today-artifact runs/pa-feitian/m4b/2026-07-10/score_today_cn_metal.json \
  --no-fixture-fallback \
  --use-git-source-commit
```

With `--no-fixture-fallback`, this is a strict real-artifact path.

## score_today JSON Shape

The PA / Feitian intake validator requires this object shape:

```json
{
  "pool": "CN_METAL",
  "instrument_class": "cn_metal_futures",
  "window_days": 7,
  "active_rules": [],
  "scored": []
}
```

Required top-level keys are enforced in
`src/engine/pa_feitian/score_today_intake.py:48`.

`score_today` writes these top-level keys at
`src/scripts/score_today.py:1742`.

PA / Feitian then filters:

```python
candidates = [r for r in records if r.get("options_calls")]
```

Reference: `src/engine/pa_feitian/scorecard_producer.py:543`.

Important scored-record fields for PA / Feitian:

- `symbol`, `date`, `direction`, `level`, `subtype`
- `confidence`, `score`, `policy_rule`, `policy_weight`
- `underlying_price`, `invalidation_level`, `position_size`
- `options_calls`
- optional PA fields such as `pa_phase`, `pa_15m_confirmed`,
  `signal_bar_quality`, `direction_verdict`

Important option-leg fields:

- `rank`, `strike`, `otm_pct`, `expiry_month`, `expiry_date`
- `contract_sym`, `days_to_expiry`
- `option_price`, `price_source`, `iv`
- optional `iv_rank`, `model_dominated`, `is_mm_strike`, `mm_target_pct`

## Data Interfaces

Underlying bar data:

- Primary: `--quant-data-root`, default `src/data/quant`
- BarStore layout expected by `src/data/store.py`:
  `{root}/{daily,hour,min15,min5,weekly}/{FILENAME}.parquet`
- Legacy fallback: `--bars-dir`, default `src/data/raw`
- CN_METAL daily paths attempted by the probe:
  - `src/data/quant/daily/SHFE.cu0.parquet`
  - `src/data/quant/daily/SHFE.au0.parquet`
  - `src/data/quant/daily/SHFE.ag0.parquet`
  - `src/data/quant/daily/INE.sc0.parquet`

Option premium / IV data:

- TqSdk live quote fallback uses `TQ_USERNAME` and `TQ_PASSWORD`
- OptionStore parquet default is `src/data/quant`
- Legacy JSON fallbacks are fixed in `score_today.py`:
  - `src/data/options/cn/ag`
  - `src/data/options/cn/au`
- `score_today` does not pass `--quant-data-root` into ag/au option selector
  enrichment, so a non-default underlying root does not repair option pricing.

References:

- Fixed option JSON roots: `src/scripts/score_today.py:60`
- ag price source order: `src/engine/options/cn_ag_selector.py:401`
- au price source order: `src/engine/options/cn_au_selector.py:371`

Environment:

- `.env.example` documents `QUANT_ROOT`, but `score_today.py` does not read it.
- TqSdk live option quotes require `TQ_USERNAME` and `TQ_PASSWORD`.

## Probes Run

### Hermes claim

```bash
hermes kanban --board paired-trading claim t_5d6d2477
```

Result:

```text
Claimed t_5d6d2477
```

### uv command probe

```bash
uv run --project src python src/scripts/score_today.py --help
```

Result:

```text
error: Distribution not found at: file:///home/drwho1985/workspace/quant/strats/quant
```

Cause: `src/pyproject.toml:23` sets
`quant-cli = { path = "../../../../quant" }`. From this nested worktree that
resolves to `/home/drwho1985/workspace/quant/strats/quant`, which does not
exist. From the main checkout it would resolve to `/home/drwho1985/workspace/quant`.

### External existing venv help probe

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py --help
```

Result: command succeeded and printed the CLI flags listed above.

### Worktree default score_today probe

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py --pool CN_METAL --window-days 7 \
  -o /tmp/score_today_cn_metal_default.json
```

Result: exit code `2`.

Key stderr:

```text
quant load kq_m_shfe_cu/daily: No data found for cu0/XSHF/D: .../src/data/quant/daily/SHFE.cu0.parquet - falling back to JSON
  kq_m_shfe_cu: missing data, skipped
quant load kq_m_shfe_au/daily: No data found for au0/XSHF/D: .../src/data/quant/daily/SHFE.au0.parquet - falling back to JSON
  kq_m_shfe_au: missing data, skipped
quant load kq_m_shfe_ag/daily: No data found for ag0/XSHF/D: .../src/data/quant/daily/SHFE.ag0.parquet - falling back to JSON
  kq_m_shfe_ag: missing data, skipped
quant load kq_m_ine_sc/daily: No data found for sc0/XINE/D: .../src/data/quant/daily/INE.sc0.parquet - falling back to JSON
  kq_m_ine_sc: missing data, skipped
ERROR: 0/4 symbols loadable from .../src/data/quant. Run fetch_quant.py.
```

### Candidate external quant root probe

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py --pool CN_METAL \
  --quant-data-root /home/drwho1985/workspace/quant/data/quant \
  --window-days 7 \
  -o /tmp/score_today_cn_metal_quantroot.json
```

Result: exit code `2`.

Key stderr:

```text
ERROR: 0/4 symbols loadable from /home/drwho1985/workspace/quant/data/quant. Run fetch_quant.py.
```

Path check:

```bash
find /home/drwho1985/workspace/quant/data/quant -maxdepth 5 -type d -print
```

Result:

```text
/home/drwho1985/workspace/quant/data/quant
/home/drwho1985/workspace/quant/data/quant/continuous
```

No top-level `daily`, `hour`, `min15`, `min5`, or `weekly` directories were
present under that root.

### PA / Feitian fixture fallback probe

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/emit_pa_feitian_snapshot.py \
  --out /tmp/pa_feitian_m4b_fixture_snapshot.json \
  --contract-version pa_feitian_snapshot_v1 \
  --manifest-out /tmp/pa_feitian_m4b_fixture_manifest.json \
  --decision-intent-out /tmp/pa_feitian_m4b_fixture_decision_intent.json
```

Result: exit code `0`.

Manifest data access:

```json
{
  "status": "fixture_fallback",
  "source": "src/tests/fixtures/pa_feitian_scorecard_v1.json",
  "notes": [
    "deterministic scorecard fixture fallback; no live score_today run was invoked"
  ]
}
```

This proves the contract producer path is wired, but it is not a real M4b
artifact.

### Strict review-builder probe

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/build_pa_feitian_review_artifacts.py \
  --score-today-artifact-dir /tmp/pa_feitian_empty_artifacts \
  --no-fixture-fallback \
  --source-fixture-dir /tmp/pa_feitian_review_source \
  --dashboard-fixture-dir /tmp/pa_feitian_review_dashboard
```

Result: exit code `2`.

Key error:

```text
no valid score_today JSON artifact found in configured artifact directories; searched: /tmp/pa_feitian_empty_artifacts
```

## Blockers

1. Worktree `uv` environment is not reproducible as-is.

   `uv run --project src ...` fails because `src/pyproject.toml` resolves the
   local `quant-cli` path to the wrong location from this nested worktree.

2. No loadable CN_METAL underlying bars are present.

   The default score_today run loads zero of four CN_METAL symbols from
   `src/data/quant` and then from legacy `src/data/raw`.

3. No verified option premium / IV store is present for ag/au.

   Even if an external underlying BarStore were supplied with
   `--quant-data-root`, score_today's option enrichment still defaults to
   `src/data/quant` and fixed legacy dirs `src/data/options/cn/{ag,au}`.

4. `score_today` can emit an empty scorecard only when symbols load but no
   recent signals fire. In the current worktree it cannot reach that state
   because the symbol load stage fails first.

## Smallest Repair Path

Minimum no-code path:

1. Make the Python environment runnable from this worktree.
   - Repair the `quant-cli` local path for nested worktrees, or run with a
     known populated venv such as the main checkout venv used in these probes.
2. Populate `src/data/quant` with a BarStore layout containing at least:
   - daily bars for `SHFE.cu0`, `SHFE.au0`, `SHFE.ag0`, `INE.sc0`
   - hourly bars for the same symbols where detector blocks require `60min`
   - min15 / weekly data if using the multi-timeframe direction annotations,
     otherwise allow current fallback behavior where supported
3. Populate option data for real ag/au premium and IV:
   - preferred: `src/data/quant/daily/SHFE.ag*.parquet` and
     `src/data/quant/daily/SHFE.au*.parquet` option contracts, plus greeks if
     available
   - acceptable fallback: legacy JSON under `src/data/options/cn/ag` and
     `src/data/options/cn/au`
   - live-only fallback: set `TQ_USERNAME` and `TQ_PASSWORD`, but this only
     covers today/yesterday signals and does not solve historical IV warmup
4. Run the `score_today` command above and verify it writes a JSON object with
   `pool=CN_METAL`, `instrument_class=cn_metal_futures`, and at least one
   `scored[]` record with non-empty `options_calls`.
5. Run `emit_pa_feitian_snapshot.py` with `--score-today-artifact` and
   `--data-access-status real_data_available`.

Minimum code repair if external BarStore roots must stay outside the repo:

1. Pass `args.quant_data_root` through the ag/au selector and enrichment calls
   in `score_today.py`.
2. Add CLI flags for legacy ag/au option JSON directories, or make them derive
   from the same root.
3. Keep `score_today` artifact intake strict: no raw market store scanning in
   PA / Feitian producer scripts.

## Current Classification

Real score_today JSON: blocked.

Real PA / Feitian M4b snapshot / manifest / decision intent: blocked because
the real scorecard is blocked.

Fixture PA / Feitian snapshot / manifest / decision intent: available and
validated by the `/tmp` probe, classified as `fixture_fallback`.
