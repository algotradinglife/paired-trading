# PA / Feitian M4b score_today Root Wiring Repair - 2026-07-10

Hermes card: `t_bfa0cc40`

Branch: `strategy/pa-feitian-m4b-real-score-today`

## Repair

`src/scripts/score_today.py` now forwards `--quant-data-root` into the ag/au
option selector and IV enrichment paths used by all four CN metal bottom
emitters:

- divergence bottom
- BPull
- PA bottom
- Context-A bottom

The script also exposes legacy JSON fallback overrides:

- `--ag-options-data-dir`
- `--au-options-data-dir`

No scoring logic or PA / Feitian intake behavior was changed. No
`real_data_available` artifact was fabricated.

## Verification

Focused tests:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python -m pytest \
  src/tests/test_score_today_option_root_wiring.py \
  src/tests/test_selector_listed_alignment.py \
  src/tests/test_option_store.py::test_enrich_with_iv_uses_store_prices
```

Result: `13 passed`.

CLI help check:

```bash
PYTHONPATH=src /home/drwho1985/workspace/quant/strats/paired-trading/src/.venv/bin/python \
  src/scripts/score_today.py --help
```

Result: command succeeded and listed `--ag-options-data-dir` and
`--au-options-data-dir`.

## Remaining Blockers

Real `score_today` JSON remains blocked by data/environment availability.

1. `uv run --project src python src/scripts/score_today.py --help` still fails
   in this nested worktree:

   ```text
   error: Distribution not found at: file:///home/drwho1985/workspace/quant/strats/quant
   ```

2. Default CN_METAL scorecard production still exits `2` before option
   enrichment because zero of four underlyings are loadable:

   ```text
   ERROR: 0/4 symbols loadable from /home/drwho1985/workspace/quant/strats/paired-trading/.worktrees/strategy-m4b-real-score-today/src/data/quant. Run fetch_quant.py.
   ```

   Missing daily BarStore files include:

   - `src/data/quant/daily/SHFE.cu0.parquet`
   - `src/data/quant/daily/SHFE.au0.parquet`
   - `src/data/quant/daily/SHFE.ag0.parquet`
   - `src/data/quant/daily/INE.sc0.parquet`

3. The candidate external root
   `/home/drwho1985/workspace/quant/data/quant` also exits `2` with zero
   loadable CN_METAL symbols. That root contains `continuous/`, but no
   top-level `daily/`, `hour/`, `min15/`, `min5/`, or `weekly/` BarStore
   directories for this script path.

4. Because underlying loading stops first, real ag/au option premium and IV
   availability was not reached in this run. The code path is now able to use
   an external option store via `--quant-data-root` and explicit legacy JSON
   fallback directories via the new flags.

Current classification: `data_blocked`.
