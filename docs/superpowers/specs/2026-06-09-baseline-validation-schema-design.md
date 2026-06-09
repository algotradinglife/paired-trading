# Baseline validation `--full` real-parse + schema v2 — design

**Date:** 2026-06-09
**Status:** Draft (pending Codex review + user approval)
**Scope:** Merge of NEXT_SESSION roadmap Item 1 (`validate_baselines.py --full`
real output parsing) and Item 2 (baseline schema v2 governance fields). The two
are coupled: Item 1's comparison logic consumes Item 2's `tolerance_policy`.

## Problem

`validate_baselines.py --full` currently only checks the repro command's exit
code (`_run_repro`, line 180-208). A backtest can run successfully while its
output numbers have drifted away from the baseline — the validator can't see it.
This is the exact blind spot behind the 2026-06-09 vflush false-alarm DRIFT.

We want `--full` to parse real backtest output and diff it against the stored
baseline samples, flagging DRIFT when numbers move beyond tolerance.

## Decisions (locked with user)

1. **Drift anchor:** `samples_full_stack_5y` is the PRIMARY comparison anchor
   (it's the live production form, present/reproducible for nearly all lanes).
   K=3 folds (`samples.is/f1/f2/f3`) are a SECONDARY check, compared only when
   both sides are non-null.
2. **Tolerance model:** global defaults + optional per-baseline `tolerance_policy`
   override. Parser uses the override if present, else the global default.
3. **Schema v2 fields added:** `tolerance_policy`, `fold_date_ranges`,
   `production_binding`, `data_snapshot_hash`. (`owner` / `slippage_bp` dropped.)
4. **Scope this pass:** wire `--out-json` into the 4 K=3 backtests
   (`backtest_bpull`, `backtest_vflush`, `backtest_pa_cn_phasefilter`,
   `backtest_pa_standalone`) PLUS `backtest_full_stack` (the source of the
   primary anchor — covers all lanes in one run). The remaining 7 baselines stay
   exit-code-only (WARN, not a failure).

### Key reconciliation (revised per Codex review)

The 4 K=3 scripts emit FOLDS only. The primary anchor (`full_stack_5y`) is
produced by `backtest_full_stack.py`. Its current `by_lane` aggregate is **too
coarse** to key to baselines (which are lane+pool+scope), and its lane labels
don't 1:1 match baseline `lane` values (e.g. CN bond is `pa_cn_bond` in
full_stack but `pa_h2` in the baseline; `context_a` merges US + CN metal;
`vflush` baseline is the cu/sc sub-scope). Resolution:

- `backtest_full_stack.py --out-json` emits **per-`(lane, symbol)`** cells,
  not lane totals.
- Each baseline declares `full_stack_lane` (its label as it appears in
  full_stack) and already has `symbols_included`.
- The validator computes a baseline's anchor by selecting
  `full_stack[full_stack_lane]`, filtering to `symbols_included`, and taking the
  **n-weighted aggregate** (`Σ nᵢ·ev_rᵢ / Σ nᵢ`; win_pct weighted likewise —
  exact because EV is a per-trade mean of R).
- ONE full_stack run is still shared across all baselines in a pass.
- Secondary folds → the 4 K=3 scripts, run per-lane only when
  `repro_emits_json: true`.

## Section 1 — Backtest output contract (`--out-json`)

New shared module `src/scripts/_baseline_output.py` defines format
`backtest_output_v1` with two `kind`s. All existing human-readable stdout is
preserved; `--out-json` is additive.

**Kind `folds`** (K=3 scripts):
```jsonc
{
  "schema": "backtest_output_v1",
  "kind": "folds",
  "lane": "pa_h2", "pool": "cn_bond",
  "samples": {
    "is": {"n": null, "ev_r": null, "win_pct": null},
    "f1": {"n": 16, "ev_r": 0.219, "win_pct": null},
    "f2": {"n": 6,  "ev_r": 1.500, "win_pct": null},
    "f3": {"n": 9,  "ev_r": 0.500, "win_pct": null}
  },
  "data_hash": "sha256:9f3a…",
  "params_echo": {"h_filter": "opposing", "stop_mult": 1.5}
}
```

**Kind `full_stack`** (`backtest_full_stack.py`, one file, **per-(lane, symbol)**).
Field names normalized to `ev_r` / `win_pct` (full_stack internally uses
`ev_R` / `win_rate` — the helper maps them):
```jsonc
{
  "schema": "backtest_output_v1",
  "kind": "full_stack",
  "lanes": {
    "pa_cn_bond": {                                   // full_stack lane label
      "kq_m_cffex_tf": {"n": 30, "ev_r": 0.110, "win_pct": 63.0},
      "kq_m_cffex_t":  {"n": 25, "ev_r": 0.140, "win_pct": 68.0},
      "kq_m_cffex_ts": {"n": 18, "ev_r": 0.120, "win_pct": 67.0}
    },
    "vflush": {
      "kq_m_shfe_cu": {"n": 17, "ev_r": 0.131, "win_pct": 64.0},
      "kq_m_ine_sc":  {"n": 14, "ev_r": 0.110, "win_pct": 67.0},
      "kq_m_shfe_ag": {"n":  9, "ev_r": -0.20, "win_pct": 40.0}  // excluded by baseline's symbols_included
    }
    // … all lanes, each as {symbol: {n, ev_r, win_pct}}
  },
  "data_hash": "sha256:9f3a…"
}
```
The validator reconstructs each baseline's anchor by filtering its
`full_stack_lane` block to `symbols_included` and n-weighted aggregating.

Helper API:
- `write_baseline_output(path, *, kind, **payload)` — serialize + write;
  normalizes `ev_R→ev_r`, `win_rate→win_pct`.
- `compute_data_hash(bars_used)` — `sha256` over a **content digest of each
  loaded symbol's OHLCV rows** (sorted by symbol, then timestamp; includes
  first_ts so truncation/insertion is caught). Faithful to what fed the EV;
  not just a 3-tuple (per Codex P1 — the tuple form has false-negative risk on
  middle-row edits / OHLC revisions / adjusted-data changes).

## Section 2 — Baseline schema v2

Bump `schema_version: 1 → 2`. All new fields are OPTIONAL; v1 files still pass
validation (gradual backfill).

```jsonc
{
  "schema_version": 2,
  // existing fields unchanged …
  "tolerance_policy": {        // optional; omit → global defaults
    "ev_r_abs": 0.10,          // |Δev_r| exceeds → DRIFT
    "sign_flip": true,         // ev_r sign flip → DRIFT
    "n_pct": 0.25,             // |Δn|/n exceeds → DRIFT (sample-base inflation)
    "win_pct_pp": 10,          // |Δwin_pct| exceeds → WARN; null = skip
    "min_n": 10                // cells with baseline n < min_n → WARN not DRIFT (tiny-n noise)
  },
  "full_stack_lane": "pa_cn_bond",  // this baseline's lane label as emitted by backtest_full_stack
  "fold_date_ranges": {
    "is": ["2019-01-01", "2023-12-31"],
    "f1": ["2024-01-01", "2024-06-30"],
    "f2": ["2024-07-01", "2024-12-31"],
    "f3": ["2025-01-01", "2025-12-31"]
  },
  "production_binding": [
    "src/scripts/score_today.py::_PA_US_60MIN_SUPPRESS",
    "src/engine/divergence/pa_detector.py::policy_weight"
  ],
  "data_snapshot_hash": "sha256:9f3a…",  // aligns with the --out-json data_hash at last_verified
  "repro_emits_json": true               // only the 4 wired K=3 lanes
}
```

**Global tolerance defaults** (in validator, used when `tolerance_policy` absent):
`ev_r_abs=0.10` / `sign_flip=true` / `n_pct=0.25` (DRIFT) / `win_pct_pp=10`
(WARN) / `min_n=10` (cells below → WARN not DRIFT).

`full_stack_lane` is required for any baseline that wants a primary-anchor check
(it maps the baseline to the right block in the full_stack output). Baselines
whose lane has no clean full_stack representation (e.g. `us_regime_gate`) omit it
and rely on folds / exit-code-only.

**Backfill:** all 11 → `schema_version: 2`; 4 K=3 lanes →
`repro_emits_json: true` + `fold_date_ranges` + `production_binding`; other 7 →
`production_binding` where derivable, stay exit-code-only; `data_snapshot_hash`
filled on first successful `--full` run (null until then); `tolerance_policy`
only where global default is wrong (e.g. pa_h2_cn_bond F2 n=6 noise).

## Section 3 — Validator comparison logic

Replace `_run_repro` (exit-code-only) with `_run_and_compare`. Never rewrites the
baseline JSON; computes a RUNTIME drift status decoupled from the stored
`verdict`.

Flow (`--full` mode):
```
1. Once per pass: run backtest_full_stack.py --out-json <tmp> (cached),
   timeout 600s. → per-(lane, symbol) map.
   Fail → all primary-anchor checks = [WARN] full_stack unavailable
   (NOT a false DRIFT).
2. Per baseline:
   a. Primary: if full_stack_lane present →
        cells = full_stack_map[full_stack_lane] filtered to symbols_included
        anchor_now = n-weighted aggregate(cells)   # n, ev_r, win_pct
        compare anchor_now vs baseline.samples_full_stack_5y
        (ev_r_abs / n_pct → DRIFT; win_pct_pp → WARN)
      else → skip primary.
   b. If repro_emits_json: run the lane's K=3 script --out-json → folds
      secondary check (each fold present on BOTH sides: ev_r_abs + sign_flip
      + n_pct).
   c. Else: skip (b); primary still checked if full_stack_lane present.
3. data_hash attribution:
   emitted.data_hash != baseline.data_snapshot_hash → "data changed"
   → DRIFT (data changed → re-baseline) vs DRIFT (data same → code regression).
```

Comparison edge-case rules (per Codex P2):
- **null/zero baseline `n`** → skip `n_pct` (no divide); the cell still
  compares ev_r if both ev_r present.
- **min_n** → if baseline cell `n < min_n`, any trigger downgrades DRIFT→WARN
  (tiny-n folds like vflush F2 n=4, pa_h2 cn_bond F2 n=6 are noisy).
- **null cells** → compare only fields present on BOTH sides; a fold null on
  either side is skipped, never DRIFT.
- **win_pct** → null on either side = skip; win_pct is WARN-only and never
  escalates to DRIFT.

Runtime status (decoupled from stored `verdict`; JSON never auto-edited):

| Case | repro_status | `--strict` exit |
|------|--------------|-----------------|
| Within tolerance | `OK` | 0 |
| Drift triggered | `DRIFT_DETECTED` + detail (cell, baseline vs new, data changed?) | non-0 |
| Only win_pct over | `WARN` | 0 |
| No parseable output (7 lanes) | `OK (exit-code only)` | 0 |
| Crash / timeout | `BROKEN` | non-0 |

`STRICT_FAIL_STATUSES` gains `DRIFT_DETECTED`. **Propagation (per Codex P2):**
the current `--strict` exit path keys off the row `status` field, so a detected
drift must set the row `status` to `DRIFT_DETECTED` (or surface via the same
`fail_strict` accounting) — it must NOT live only inside a separate
`repro_status` key, or `--strict` would miss it. Each drift prints a suggested
action (re-baseline / investigate code).

## Section 4 — Rollout

Script changes (each adds `--out-json PATH`, calls helper after computing
numbers, keeps all stdout):

| Script | Emits | Feeds |
|--------|-------|-------|
| `backtest_full_stack.py` | `kind:full_stack`, per-(lane, symbol) map | primary anchor (all lanes) |
| `backtest_bpull.py` | `kind:folds` | bpull secondary |
| `backtest_vflush.py` | `kind:folds` | vflush secondary |
| `backtest_pa_cn_phasefilter.py` | `kind:folds` (per `--pool`) | pa_h2 cn_bond/cn_futures/cn_metal |
| `backtest_pa_standalone.py` | `kind:folds` | pa_h2_climax secondary |

Baseline backfill: 11 → schema_version 2; 4 K=3 lanes →
`repro_emits_json` + `full_stack_lane` + `fold_date_ranges` +
`production_binding`; any baseline wanting a primary check also needs
`full_stack_lane` (determined by reading full_stack's lane labels); other
fields (`production_binding`) on the easy ones; `data_snapshot_hash` filled
after first `--full`.

New file: `src/scripts/_baseline_output.py`.

## Section 5 — Testing

| Layer | What |
|-------|------|
| Unit: `_baseline_output` | `compute_data_hash` determinism (same bars→same hash, one changed bar→differs); both `write_*` shapes correct |
| Unit: validator compare | constructed emitted JSON + baseline: within tol→OK; ev>0.10R→DRIFT; sign flip→DRIFT; n +30%→DRIFT; win >10pp→WARN; data_hash mismatch→correct attribution; `tolerance_policy` override applies |
| Unit: fallback | no-`--out-json` baseline → `OK (exit-code only)`; full_stack run fails → primary WARN, not false DRIFT |
| Integration (light) | mock backtest emitting fixed JSON → validator end-to-end table + `--strict` exit code |
| Regression | default metadata mode unchanged; v1 files still validate |

End-to-end re-run of real (slow) backtests is an implementation-phase manual
step, not a unit test.

## Out of scope (this pass)

- Wiring the other 7 baselines' scripts (context_a, pa_us_60min, us_regime_gate,
  pa_h2_us_equity) for parseable output.
- `params_echo` drift comparison (recorded, not compared yet).
- `owner` / `slippage_bp` schema fields.
- Auto-rewriting baseline `verdict` from runtime drift (deliberately never done).
