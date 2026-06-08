# paired-trading — project status

Snapshot at 2026-06-08.  Read this first to know where the project
stands; consult linked docs / commits for the details.

> **Audit pass 2026-06-08** — policy table + active-levels enumeration
> below reconciled against `scripts/score_today.py` per
> `doc/repro/score_audit_2026-06-08.md` (P1 finding S5).  Previous
> revision advertised level `pa_us_daily` / weight `0.80*` for the US
> daily lane and omitted `bpull` / `vflush` / `context_a` /
> `pa_h2_climax` / `pa_cn_bond` from the active set.

## What this is

A multi-period analysis + paired-trading engine for the joint analysis
of underlyings and options, grounded in three pillars:

- 宋建毅《K 线动能理论》— heap / cycle / segment momentum structure
- Al Brooks 《Price Action》— H2-style swing-bottom detection
- 肖淳心《飞天期权择时》— options timing on validated entries

The repo holds engine code (`src/engine/`), backtest + analysis
scripts (`src/scripts/`, `src/tools/`), engineering docs (`doc/`),
reproduction notes (`doc/repro/`), and the historical 2026-05-31
report HTMLs (`doc/legacy/`).

## Signal lanes — what's active, what's retired

### Active (production)

PA (Price Action) detectors own live signal generation as of
2026-06-08.  Policy weights live in `src/engine/divergence/pa_detector.py::policy_weight()`
(and per-detector siblings: `bpull_detector.py`, `vflush_detector.py`,
`context_a_detector.py`), validated K=3 walk-forward (see
`doc/repro/pa_baseline_2026-06-08.md` and
`pa_policy_validation_2026-06-08.md`):

| instrument_class       | path                                | weight                         | validation                                  |
|------------------------|-------------------------------------|--------------------------------|---------------------------------------------|
| `us_equity`            | uptrend + h=opp (60min)             | 0.80                           | EV +0.384R, n=56, F1+0.625 F2+0.708         |
| `us_equity`            | uptrend + h=opp + legs=1 (60min)    | 0.90                           | EV +0.595R, n=21, hit 62%                   |
| `us_equity`            | DIF>0 + h=opp + BULL phase (daily)  | 0.65                           | dominant emit path; score=3                 |
| `us_equity`            | DIF>0 + h=opp + at_tr_bottom (daily)| 0.40                           | TR/TR_FORMING sub-cell; score=2 (half size) |
| `us_equity` (long-bond)| tlt/tlh/iei/ief/shy                 | 0.00                           | suppressed (4/4 folds negative)             |
| `cn_metal_futures`     | h=opp                               | 0.75                           | EV +0.524R, n=46, 3 OOS folds all +         |
| `cn_metal_futures`     | TR phase × h=opp                    | (sub)                          | EV +0.666R, n=38                            |
| `cn_bond`              | h=opp                               | 0.70                           | EV +0.548R, n=31, 3 OOS folds all +         |
| `cn_futures`           | h=opp                               | 0.55                           | monitoring only (EV ≈ 0)                    |
| `czce` / `cn_agri`     | (any)                               | 0.00                           | OOS EV ≈ 0 with fold degradation            |

Daily-lane caveat: the audit found `pa_us_dif_pos` emits 5 records vs
the 60min lane's 30 over 365 days — the `at_tr_bottom` gate (close in
bottom 25% of the recent 8-pivot range) kills almost every TR setup.
The 0.80 EV+0.173R/n=68 figure quoted in earlier STATUS revisions came
from a pre-gate backtest and is **not** what the current code emits.
See `doc/repro/score_audit_2026-06-08.md` finding S2 for the triage
options.

`score_today.py` is the live scorecard runner.  It currently emits
**10 distinct level identifiers** across the pools (PA + a few small
ancillary detectors; the 9 DIF-divergence levels are gated off by
default):

| Level            | Pool / instrument_class               | Emit-path policy_weight                                                | Score range            |
|------------------|---------------------------------------|------------------------------------------------------------------------|------------------------|
| `pa_us_60min`    | US 60min (us_equity, non-long-bond)   | 0.80 (uptrend + h=opp, legs=0) / 0.90 (legs=1)                         | 3 / 4                  |
| `pa_us_dif_pos`  | US daily (us_equity, non-long-bond)   | 0.65 (BULL phase) / 0.40 (TR or TR_FORMING + at_tr_bottom)             | 3 (BULL) / 2 (TR)      |
| `context_a`      | US + CN_METAL (us_equity, cn_metal)   | 0.60 (h=opp only; other h_rel = 0.0)                                   | 3 (Conditional PASS)   |
| `pa_h2`          | CN_METAL (cn_metal_futures)           | 0.75 (h=opp) / 0.45 (supporting) / 0.60 (neutral)                      | 2-4 (iso + phase)      |
| `bpull`          | CN_METAL ex-rb (cn_metal_futures)     | 0.75 (h=opp only; non-opp gated to 0.0 so only score=4 emits)          | 4                      |
| `vflush`         | CN_METAL cu/sc only (cn_metal_futures)| 0.65 (h=opp; ag+au suppressed at 0.0)                                  | 3 (h=opp) / 2 (other)  |
| `pa_cn_bond`     | CN_BOND (cn_bond)                     | 0.70 (h=opp) / 0.40 (neutral)                                          | 3 (fixed)              |
| `pa_h2_climax`   | CN_COMMODITY agri subset              | 0.65 hardcoded in script (m/p/ta/ma/sr + require_climax + h=opp)       | 3 (fixed)              |
| `intra_cycle`, `inter_cycle`, `inter_segment` | all classes (via `detect_all_divergences`) | apply_policy() per signal; **filtered out by default** under DIF retirement | n/a |
| `intra_cycle_{hist,slope,dea,bull_hist,bull_slope,bull_dea}` | all classes | apply_policy() per signal; **filtered out by default** under DIF retirement | n/a |

### Retired (DIF lane)

The DIF-based MACD-divergence detector lane was retired in production
2026-06-08 ("DIF 全退役" — user decision).  9 levels affected:

- Classical 3: `intra_cycle`, `inter_cycle`, `inter_segment`
- intra_cycle_* (6 variants, source-level DEPRECATED banner):
  `intra_cycle_hist`, `intra_cycle_slope`, `intra_cycle_dea`,
  `intra_cycle_bull_hist`, `intra_cycle_bull_slope`, `intra_cycle_bull_dea`

These detectors still run when invoked but `score_today` filters
their records by default.  Pass `--include-dif-detectors` to opt in
(historical CSV regeneration / A-B comparison only).

The intra_cycle_* (6 variants) carry DEPRECATED banners in their
source files (`engine/divergence/{hicd,dif_slope,dea_div}{,_bull}.py`).
The classical 3 emit from `engine/divergence/detector.py` which does
not carry a banner — production behaviour is gated by score_today.

## Data layout

External drive `/Volumes/Data Drive/`:

```
data/futures/paired-trading/quant/{SHFE,DCE,CZCE,CFFEX,INE}/      ← Parquet bars
data/futures/paired-trading/options/cn/                            ← CN option JSON
data/futures/paired-trading/raw/                                   ← legacy JSON snapshots
data/stock/paired-trading/quant/NYSE/                              ← US Parquet
data/stock/paired-trading/options/{spy,qqq,dia,...}/               ← US option JSON
derived/paired-trading/src-data-review/                            ← rr_b_*.csv, signals_*.csv
derived/paired-trading/data-review/                                ← swing/missed-swing CSVs
```

Local symlink farms under `src/data/`:

```
src/data/quant/{SHFE,DCE,CZCE,CFFEX,INE,NYSE,_contracts}     → external Parquet
src/data/options/{cn,spy,qqq,dia,gld,gdx,iwm,nvda,tlt,xlf,xlk} → external options
src/data/raw                                                   → external raw JSON
```

Env vars (see `.env.example`):

- `MARKET_DATA` — base for bars data (currently informational, scripts
  prefer Parquet via the `data.bar_loader.DEFAULT_QUANT_ROOT` constant)
- `DERIVED_ROOT` — base for review CSVs.  Used by 14+ scripts under
  `src/scripts/`, `src/tools/`, and `src/engine/divergence/exhaustion.py`
  via `_default_review_dir()` helpers
- `WIKI_ROOT`, `SAMPLES_ROOT` — unused by production code

## Reproduction matrix (8 historical 2026-05-31 reports)

See `doc/repro/` for one markdown per report.  Headline outcomes:

| Report                       | Verdict                                                    |
|------------------------------|------------------------------------------------------------|
| cn_b_topology                | ✅ 96.5% bit-exact (Parquet route)                         |
| confidence_reversal          | ✅ TOP×mid weakness reproduces ~exactly (+0.157→+0.145R)   |
| options_crossmarket          | ◻ partial — pooled option EV +29% vs report +32.5%        |
| hopp_stability               | ❌ "4/6 PASS" fails; "CN_METAL 2024 / US_MACRO" holds      |
| crosspool_walkforward        | ❌ "STRONG PASS" → basic PASS; 5/5 pools positive fails F2 |
| crosspool_merge              | ❌ correlation structure collapses; US_MACRO anchor gone   |
| multitf_structure            | ❌ 21 per-symbol claims: 10 fail / 5 flip / 2 hold         |
| strategy_report (05-30)      | ❌ §5 strategy recommendations no longer actionable        |
| options_simulation           | ❌ unreproducible — Black-model pricer missing             |

Root cause: detector grew 6 new `intra_cycle_*` level variants after
2026-05-31; sample-base inflated 2.4–10× and the high-EV / small-n
subsets that powered the narratives got diluted.  The surviving
findings are the ones not dependent on small-n EV: confidence_reversal's
TOP × mid pattern and hopp_stability's CN_METAL-2024 vs US_MACRO-2024
split.

## Commit timeline (2026-06-07 → 2026-06-08)

```
24a295b  Initial commit (rebuilt from macd-momentum)
7d1f4ce  wire quant-data path dep + symlink farm
1f20490  rename project to paired-trading
c186144  cn_b_topology --source quant + first repro
1983829  reproduce 8 historical 2026-05-31 reports
101c186  first PA-system baseline (cn_structural Parquet)
ae2a1e2  surface src/data/* python package + PA Parquet helper
88eca10  policy table update from Phase A (czce/cn_agri/tlt/cn_bond)
0f6c1a0  score_today wires symbol kwarg
08727f2  cn_bond production wiring + 77 unit tests
d6f95b3  us_equity 60min "fast lane"
6936170  score_today default-skip 6 deprecated DIF levels
b683663  extend DIF retirement to classical 3
e2f8704  archive legacy DIF reports + env-var review paths + options symlinks
```

## Running things

Setup:

```bash
cd src
uv sync                            # installs deps + quant-data editable
export DERIVED_ROOT=/Volumes/Data\ Drive/derived
```

Common runs:

```bash
# Live scoring (PA-only by default)
.venv/bin/python scripts/score_today.py --pool US --window-days 7
.venv/bin/python scripts/score_today.py --pool CN_METAL
.venv/bin/python scripts/score_today.py --pool CN_BOND

# PA backtests
.venv/bin/python scripts/backtest_pa_swing.py --dataset us_60min
.venv/bin/python scripts/backtest_pa_cn_structural.py
.venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool CN_BOND

# Reproduce a historical report against current data
.venv/bin/python tools/repro_hopp_stability.py
.venv/bin/python tools/repro_confidence_reversal.py

# Full test suite
.venv/bin/python -m pytest tests/ -q     # 315 passed currently
```

## Known followups

In rough priority order, mostly read-only / low-risk:

1. **60min lane structural stop** — `pa_us_60min` records currently
   carry `invalidation_level=None` so position sizing falls through
   to the default branch.  Audit confirmed 9 score=4 + 21 score=3
   live samples over the past year — enough to extract empirical
   stops from peak adverse excursion.  See audit memo §N5.
2. **`pa_us_dif_pos` daily-lane `at_tr_bottom` triage** — audit
   memo §S2/N2: code emits 0.65/0.40, not the 0.80 the prior STATUS
   advertised.  Either widen the gate (`pos_in_tr < 0.40`) and
   re-run K=3 WF, or formally downgrade the daily lane to a
   "BULL-phase-only" path and update the table.  Interim wording in
   the policy table above reflects what code does, **not** a
   re-validated weight — re-cite EV/hit before claiming OOS support
   for the 0.65/0.40 numbers.
3. **Sweet-spot rules dead-on-arrival for PA records** — audit memo
   §S3 / §N3: the `SWEET_SPOTS` table is keyed on context features
   (`prior_swing_distance_pct`, `wick_ratio`, `vol_ratio`) that PA
   detectors don't populate.  0/95 1y US records match
   `US-bot-swing-mid-h20`.  Either back-populate the context or
   replace the rules with PA-native predicates.  Validated date on
   surviving rules should be marked "pre-DIF-retirement, requires
   re-validation".
4. **detector.py source-level deprecation banner** — the classical 3
   DIF detectors emit from `engine/divergence/detector.py` which has
   no DEPRECATED banner.  Production behaviour is correct via
   score_today filter; source-level housekeeping is optional.
5. **Physical removal of 9 DIF detector files** — defer; once we
   confirm zero live consumers, remove the dead code.
6. **DERIVED_ROOT env-var rollout audit** — 14 scripts route through
   `_default_review_dir()` now; spot-check any new scripts added
   afterwards.
7. **Black-model option pricer** — `options_simulation` /
   `options_crossmarket` repro is gated on a pricer that didn't
   survive the migration.  Rebuild only if option-EV simulation is
   needed live.
8. **`bpull` score gradient** — audit memo §S4: 31/31 bpull records
   land at score=4 because non-opposing branches are policy-gated
   to 0.  No quality signal reaches the consumer beyond "fire / not
   fire".  Decide whether to surface bpull-internal features or
   accept the binary lane.
9. **PA `pa_isolated` / `pa_15m_confirmed` field consistency** —
   audit memo §M3 / §M4: only `pa_h2` populates these fields; other
   PA-derived levels emit them as hardcoded `None`.  Either drop the
   fields on non-applicable lanes or compute them uniformly.

## Memory & instructions

Repo conventions / strategic decisions are mirrored in Claude's project
memory at `~/.claude/projects/-Users-huhan-code-trading-macd-momentum/memory/`:

- `project_signal_source.md` — DIF retirement, PA is the active lane
- `feedback_options_style.md` — recommend + parallelize when listing options
- `MEMORY.md` — index

`CLAUDE.md` at the repo root carries the original wiki-generation task
brief (historical, completed 2026-05-21).  Future Claude sessions
should treat **this STATUS.md** as the primary "where things are"
document, not CLAUDE.md.
