# paired-trading — project status

Snapshot at 2026-06-09.  Read this first to know where the project
stands; consult linked docs / commits for the details.

> **Sync 2026-06-09** — full P0→P3 PnL push following the lane × market
> evaluation.  Cumulative EV +0.131R → +0.247R (+89% in-sample).
> K=3 OOS replay shows +23.39R total improvement (+0.060R per OOS trade
> across n=389; OOS EV +0.284R → +0.344R).  US pool went
> +0.082R → +0.260R (+217%).  2022 US H2-family drag (-21.4R) eliminated.
> 4 reject decisions documented (avoiding ~-26R of incorrect changes).
> baselines/ infrastructure (11 entries) + EXPECTED_LANES registry now
> the single source of truth.  See `doc/repro/baselines_v2_2026-06-09.md`,
> `lane_market_evaluation_2026-06-09.md`, `max_hold_experiment_2026-06-09.md`,
> `cn_regime_gate_reject_2026-06-09.md`.

> **Audit / sync 2026-06-08 (late session)** — added the strategic-
> layer **DIR module** (8-source synthesiser + 60min POC), the
> **F1 TR-position-aware** daily_structure vote, and **structural
> stops on all 8 emit lanes**.  Policy table + level table reflect
> code-as-of `d4b933d0`.  See `doc/repro/score_audit_2026-06-08.md`,
> `dir_verdict_alignment_2026-06-08.md`, and the commit timeline
> below for narrative.

## 2026-06-09 lane × market deployment summary

Cumulative production deltas (full_stack 5.5y replay, post-P0+P1c+P2+P3):

```
                       baseline         current production    Δ
EV/trade in-sample     +0.131R          +0.247R               +89%
sum R (5.5y)           +124.52R         +192.18R              +54%
EV/trade K=3 OOS       +0.284R          +0.344R               +0.060R/trade
sum R K=3 OOS          +110.42R         +133.81R              +23.39R
US pool:               +0.082R       →  +0.260R               +217%
2022 US H2 family:     -21.4R drag   →  +0.5R                95% eliminated
```

**OOS qualifier (K=3 MARGINAL PASS, not STRONG)**: F1 +15.02R / F3 +7.49R
both PASS; F2 only +0.87R / n=75. Improvement concentrated in bpull and
context_a (lanes with avg-hold previously at the 20-bar cap). max_hold=30
is a provisional global default; per-lane defaults are cleaner. See
`doc/repro/max_hold_experiment_2026-06-09.md` for K=3 fold table.

### DEPLOYED changes

| Tier | Change | Location | R impact |
|------|--------|----------|----------|
| P0 | `_CONTEXT_A_EXCLUDED_CN_METAL` = {sc} | `context_a_detector.py` | sc was 0% win n=10 -8.86R |
| P0 | `_CONTEXT_A_EXCLUDED_US` = {DIA,SPY,XLU} | `context_a_detector.py` | broad-market not H2-fittable |
| P0 | `_PA_US_60MIN_SUPPRESS` = {DIA,XLK,QQQ,XLRE} | `score_today.py:120` | per-symbol negatives |
| P1c | +SPY to `_PA_US_60MIN_SUPPRESS` | `score_today.py:120` | structural broad-market |
| P1c | new `_PA_US_DIF_POS_SUPPRESS` = {DIA,SPY} | `score_today.py:130` | same principle |
| P1a | bug fix: `load_bars_quant_or_json` | `backtest_vflush.py`, `backtest_bpull.py` | killed vflush DRIFT false alarm |
| P2 | US regime gate (SPY 200dma + 20d vol) | `engine/regime/us_regime_gate.py` | suppresses pa_us_60min + context_a US during risk_off |
| P3 | max_hold daily 20 → 30 | `backtest_full_stack.py` | K=3 MARGINAL PASS +23.39R OOS |
| housekeeping | `_CN_AGRI_POS_SYMBOLS` remove kq_m_dce_p | `score_today.py:124` | palm oil 64% full_stop rate, scoped for future climax reactivation |

### REJECTED (with evidence)

| Decision | Avoided R |
|----------|-----------|
| TP1 1R → 0.75R (P2/A) | -6.4R |
| pa_us_dif_pos regime gate (P2/C) | -0.44R |
| CN_METAL regime gate (composite/per-sym/SPY-port) | -10 to -19R |
| **Cumulative avoided** | **~-26R** |

Reject decisions ≈ deploy decisions in PnL value. See `doc/repro/p2_followups_2026-06-09.md`,
`cn_regime_gate_reject_2026-06-09.md`.

### baselines/ infrastructure (single source of truth)

- 11 entries audited via `scripts/validate_baselines.py`
- `EXPECTED_LANES.json` registry catches deleted/missing files
- `--strict` mode for CI: STALE/DRIFT/PENDING/EXPIRED/BROKEN/MISSING → exit 1
- Verdicts: STRONG PASS / PASS / CONDITIONAL PASS / marginal / REJECT / STALE / DRIFT / PENDING_VALIDATION / DEPLOYED

Current dashboard:
```
[ OK ]  bpull          cn_metal_futures  STRONG PASS         0.75
[ OK ]  context_a      cn_metal_futures  CONDITIONAL PASS    0.60
[ OK ]  context_a      us_equity         CONDITIONAL PASS    0.60
[STAL]  pa_h2_climax   cn_agri_pos       STALE               0.00
[ OK ]  pa_h2          cn_bond           STRONG PASS         0.70
[ OK ]  pa_h2          cn_futures        marginal            0.55
[ OK ]  pa_h2          cn_metal_futures  STRONG PASS         0.75
[ OK ]  pa_h2          us_equity         PASS                0.80
[PEND]  pa_us_60min    us_equity         PENDING_VALIDATION  0.65
[ OK ]  us_regime_gate us_equity         DEPLOYED               —
[ OK ]  vflush         cn_metal_futures  STRONG PASS         0.65
```

## What this is

A multi-period analysis + paired-trading engine for the joint analysis
of underlyings and options, grounded in three pillars:

- 宋建毅《K 线动能理论》— heap / cycle / segment momentum structure
- Al Brooks 《Price Action》— H2-style swing-bottom detection
- 肖淳心《飞天期权择时》— options timing on validated entries

The repo holds engine code (`src/engine/`), backtest + analysis
scripts (`src/scripts/`, `src/tools/`), engineering docs (`doc/`),
reproduction notes (`doc/repro/`), design memos (`doc/design/`), and
the historical 2026-05-31 report HTMLs (`doc/legacy/`).

## Signal lanes — what's active, what's retired

### Active (production)

PA (Price Action) detectors own live signal generation as of
2026-06-08.  Policy weights live in `src/engine/divergence/pa_detector.py::policy_weight()`
(and per-detector siblings: `bpull_detector.py`, `vflush_detector.py`,
`context_a_detector.py`), validated K=3 walk-forward (see
`doc/repro/pa_baseline_2026-06-08.md` and
`pa_policy_validation_2026-06-08.md`):

| instrument_class       | path                                | weight  | validation                                  |
|------------------------|-------------------------------------|---------|---------------------------------------------|
| `us_equity`            | uptrend + h=opp (60min)             | 0.80    | EV +0.384R, n=56, F1+0.625 F2+0.708         |
| `us_equity`            | uptrend + h=opp + legs=1 (60min)    | 0.90    | EV +0.595R, n=21, hit 62%                   |
| `us_equity`            | DIF>0 + h=opp + BULL phase (daily)  | 0.65    | dominant daily emit; score=3                |
| `us_equity`            | DIF>0 + h=opp + TR/TR_FORMING       | 0.30    | un-gated subset (B1-1 dropped at_tr_bottom; weight downgraded pending WF) |
| `us_equity` (long-bond)| tlt/tlh/iei/ief/shy                 | 0.00    | suppressed (4/4 folds negative)             |
| `cn_metal_futures`     | h=opp                               | 0.75    | EV +0.524R, n=46, 3 OOS folds all +         |
| `cn_metal_futures`     | TR phase × h=opp                    | (sub)   | EV +0.666R, n=38                            |
| `cn_bond`              | h=opp                               | 0.70    | EV +0.548R, n=31, 3 OOS folds all +         |
| `cn_futures`           | h=opp                               | 0.55    | monitoring only (EV ≈ 0)                    |
| `czce` / `cn_agri`     | (any)                               | 0.00    | OOS EV ≈ 0 with fold degradation            |

`score_today.py` is the live scorecard runner.  It emits **8 active
level identifiers** across the pools (DIF lane retired — 9 levels
gated off by default):

| Level            | Pool / instrument_class               | Emit-path policy_weight                                                | Score range            |
|------------------|---------------------------------------|------------------------------------------------------------------------|------------------------|
| `pa_us_60min`    | US 60min (us_equity, non-long-bond)   | 0.80 (uptrend + h=opp, legs=0) / 0.90 (legs=1)                         | 3 / 4                  |
| `pa_us_dif_pos`  | US daily (us_equity, non-long-bond)   | 0.65 (BULL phase) / 0.30 (TR / TR_FORMING, un-gated)                   | 3 (BULL) / 2 (TR)      |
| `context_a`      | US + CN_METAL (us_equity, cn_metal)   | 0.60 (h=opp only; other h_rel = 0.0)                                   | 3 (Conditional PASS)   |
| `pa_h2`          | CN_METAL (cn_metal_futures)           | 0.75 (h=opp) / 0.45 (supporting) / 0.60 (neutral)                      | 2–4 (iso + phase)      |
| `bpull`          | CN_METAL ex-rb (cn_metal_futures)     | 0.75 (h=opp only; non-opp gated to 0.0 so only score=4 emits)          | 4                      |
| `vflush`         | CN_METAL cu/sc only (cn_metal_futures)| 0.65 (h=opp; ag+au suppressed at 0.0)                                  | 3 (h=opp) / 2 (other)  |
| `pa_cn_bond`     | CN_BOND (cn_bond)                     | 0.70 (h=opp) / 0.40 (neutral)                                          | 3 (fixed)              |
| `pa_h2_climax`   | CN_COMMODITY agri subset              | 0.65 hardcoded (m/p/ta/ma/sr + require_climax + h=opp)                 | 3 (fixed)              |
| `intra_cycle`, `inter_cycle`, `inter_segment` | all classes (via `detect_all_divergences`) | apply_policy() per signal; **filtered out by default** under DIF retirement | n/a |
| `intra_cycle_{hist,slope,dea,bull_hist,bull_slope,bull_dea}` | all classes | apply_policy() per signal; **filtered out by default** under DIF retirement | n/a |

### Structural stops on all 8 emit lanes (locked 2026-06-08)

Per user-locked methodology "止损线架在支撑线或者压力线附近", every
emit lane sets `invalidation_level` on its record (rejected to `None`
when the computed stop ≥ entry close):

| Lane            | Stop anchor                                                                 |
|-----------------|------------------------------------------------------------------------------|
| `pa_h2`         | `PAStructureDetector.structural_stop` on daily (most-recent HL or TR floor − 1%) |
| `pa_cn_bond`    | same as `pa_h2`                                                              |
| `pa_us_dif_pos` | same as `pa_h2` + ≥-close reject                                             |
| `pa_us_60min`   | `swing_low(10) − 0.5%` (split-robust; B1-4 calibration on 30 live samples)   |
| `vflush`        | signal-bar `low × 0.99` — v-flush breaks prior support, the climax low IS the new pivot |
| `context_a`     | same as `pa_h2`                                                              |
| `pa_h2_climax`  | same as `pa_h2`                                                              |
| `bpull`         | same as `pa_h2`                                                              |

### DIR (direction synthesiser) module

`src/engine/divergence/pa_direction_assessment.py::assess_direction()`
is the strategic-layer module per the user-locked methodological
principle: every signal report must lead with multi-TF + trend
structure + context bull/bear before discussing the signal.

**8-source default path** (all daily-anchored lanes — `pa_h2`,
`pa_us_dif_pos`, `pa_cn_bond`, and currently `pa_h2_climax` /
`context_a` / `vflush` / `bpull` not yet wired):

```
weekly_trend     PAStructureDetector on weekly + W DIF        (backdrop)
daily_structure  PAStructureDetector on daily + TR position   (F1)
hourly_state     1h DIF vs ATR margin (polarity-aware)        (signal cue)
minute15_state   15m DIF vs ATR margin (fine-grain)           (signal cue)
context          Context A/B1 (bottom) or A_top/B1_top (top)  (上下文)
divergence       PA-native pivot+hist                         (背离)
force_balance    bull/bear strength over recent window        (多空力量)
exhaustion       exhausting-side detection                    (耗竭)
```

Each source carries weight 0.125; threshold 0.50 = 4-of-8 majority.

**10-source POC path** (currently only `pa_us_60min`, commit
`00b5fb9f`):

Adds two sources:
- `signal_tf_structure_60min` — PA structure on the signal's own TF
  (60min for pa_us_60min; the same TR-position policy as daily_structure)
- `resonance` — votes the shared direction when signal-TF and daily
  structures align; neutral otherwise.  "Resonance=YES" is the
  "共振" annotation; "Resonance=NO" means each TF follows its own
  structure for entry / sizing downstream.

10 × 0.125 = 1.25 total weight; threshold 0.625 = 5-of-10 majority.

DIR is **annotation-only** in score_today — verdicts land on records
but no emit gate consults them.  Promotion to a gate awaits POC
alignment data + a calibration pass.

#### F1: TR position-aware daily_structure vote

`daily_structure` formerly mapped `TR / TR_FORMING → neutral`
unconditionally.  F1 (commit `13c1904`) encodes the user's TR-policy
explicitly:

```
TR + h2_bottom + pos_in_tr ≤ 0.30 (range bottom)     → bull  (buy support)
TR + h2_top    + pos_in_tr ≥ 0.70 (range top)        → bear  (sell resistance)
TR + middle 0.30–0.70                                → neutral (don't trade)
TR + position mismatch (h2_bottom near top, etc.)    → neutral (conservative)
TR + incomplete range (tr_top or tr_bot is None)     → neutral
BULL / BEAR / UNCLEAR — unchanged
```

Position mismatch is conservative-neutral by user lock; multi-TF
sources resolve the ambiguity rather than letting daily_structure
actively veto.

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

## PA TOP — two-strike stall (Path B pending)

PA TOP detection has failed to find ANY promotable cell in two
walk-forward framings (commits `1e6c65e`, `b2a3519`):

| Framing                              | Result                                   |
|--------------------------------------|------------------------------------------|
| C4 counter-trend (PA H2 mirror, 1.5×ATR, 40 bar) | 0 cells promote; cn_bond worst |
| Step 2 trend-follow (2.5×ATR, 80 bar, BEAR phase) | 0 cells promote; CN_METAL gets worse  |

The user's strategic premise "puts must be in MVP" stands.  The
mechanism — H2-mirror tops — has been disproven in both natural
framings.  Path B (replace TOP signal source — exhaustion-anchored,
divergence-driven, or other) is the open decision.  Bear-side context
classifier (`classify_context_top` with A_top / B1_top) is implemented
in `pa_context_classifier.py` (commit `c834bc7`) and ready to plug in
when a new TOP detector lands.

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

- `MARKET_DATA` — base for bars data (currently informational; scripts
  prefer Parquet via the `data.bar_loader.DEFAULT_QUANT_ROOT` constant)
- `DERIVED_ROOT` — base for review CSVs.  Used by 21 scripts via
  `_default_review_dir()` helpers
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
b1796d6  initial STATUS.md
a4da081  DERIVED_ROOT rollout to 7 more scripts
92b41ee  Batch 1 (audit + PA TOP + Xiao design + CN_BOND P0 fix)
174ef95  Batch B1 (4 P1 audit fixes — at_tr_bottom drop, sweet-spots, STATUS sync, 60min stop)
1e6c65e  C4 PA TOP walk-forward grid + C3 Xiao module design
b2a3519  pa_direction_assessment 4-source + PA TOP trend-follow strike
6cc0b1f  D-full DIR 8-source synthesiser (multi-TF + context + exhaustion)
c834bc7  bear-side context classifier + DIR audit memo
13c1904  F1 — TR position-aware daily_structure vote
00b5fb9f  signal-TF structure + resonance POC for pa_us_60min (10-source path)
9f02be46  structural stops for vflush / context_a / pa_h2_climax
d4b933d0  bpull structural stop (8/8 emit lanes now stopped)
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
.venv/bin/python scripts/score_today.py --pool CN_COMMODITY  # CN_AGRI subset → pa_h2_climax

# PA backtests
.venv/bin/python scripts/backtest_pa_swing.py --dataset us_60min
.venv/bin/python scripts/backtest_pa_cn_structural.py
.venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool CN_BOND
.venv/bin/python scripts/backtest_pa_top_grid.py --frame counter_trend   # 2-strike negative
.venv/bin/python scripts/backtest_pa_top_grid.py --frame trend_follow    # 2-strike negative

# Reproduce a historical report against current data
.venv/bin/python tools/repro_hopp_stability.py
.venv/bin/python tools/repro_confidence_reversal.py

# Full test suite
.venv/bin/python -m pytest tests/ -q     # 441 passed currently
```

## Known followups

In rough priority order (descending), as of `d4b933d0`:

1. **POC alignment data accrual** — `pa_us_60min` is the only lane on
   the 10-source path.  Wait for ~50+ live samples before tuning the
   proportional 0.50 threshold or rolling the path out to daily lanes.
2. **PA TOP path B decision** — H2-mirror has failed twice; replace
   with exhaustion-anchored / divergence-driven / failed-bull TOP
   detector.  User commitment "puts must be in MVP" stands; mechanism
   is the open call.
3. **DIR audit followups (3 of 5 still open)** — `doc/repro/
   dir_verdict_alignment_2026-06-08.md`: (a) daily_structure was
   structurally biased neutral pre-F1 — F1 partially addresses;
   verify on next audit pass.  (b) `minute15_state` polarity rule
   fires bear on freshly-printed bottoms (15m DIF has already turned
   when the daily H2 prints); widen indifferent zone or skip 15m at
   H2 bar.  (c) Resonance source neutral when signal-TF and daily
   structures don't both vote — by design but watch for skew.
4. **Daily-lane `pa_us_dif_pos` weight calibration** — B1-1 dropped
   the at_tr_bottom gate; the un-gated TR/TR_FORMING subset has weight
   0.30 as a placeholder.  Run a focused K=3 WF on the un-gated subset
   before declaring 0.30 a calibrated value.
5. **CN_METAL PA-native sweet-spot rules** — B1-2 added US PA-native
   rules; CN_METAL pool has 0 PA-native sweet spots.  The validated
   `pa_h2 h=opp TR-phase` cell (n=38 EV +0.666R) is the natural seed.
6. **`bpull` score gradient** — 31/31 bpull records land at score=4
   because non-opposing branches policy-gate to 0.  No quality
   gradient reaches the consumer beyond fire/not-fire.  Decide
   whether to surface bpull-internal features or accept the binary
   lane.
7. **PA `pa_isolated` / `pa_15m_confirmed` field consistency** —
   only `pa_h2` populates these.  Either drop them on the other lanes
   or compute uniformly.
8. **detector.py source-level deprecation banner** — classical 3 DIF
   detectors emit from `engine/divergence/detector.py` without a
   banner; production behaviour is gated by score_today.  Source-
   level housekeeping is optional.
9. **Physical removal of 9 DIF detector files** — defer; once we
   confirm zero live consumers, remove the dead code.
10. **Black-model option pricer** — `options_simulation` /
    `options_crossmarket` repro is gated on a pricer that didn't
    survive the migration.  Rebuild only if option-EV simulation is
    needed live.
11. **Position management** — `_position_size()` is 20 lines of
    hardcoded "half/light/watch" tiers.  Disproportionate to the
    PA + DIR + structural-stop stack.  All 8 lanes now expose
    `invalidation_level`, so risk-per-trade sizing is unblocked.
    The user has explicitly deferred this until DIR + Xiao Module
    design have settled.

## Memory & instructions

Repo conventions / strategic decisions are mirrored in Claude's project
memory at `~/.claude/projects/-Users-huhan-code-trading-paired-trading/memory/`
(migrated 2026-06-09 from the pre-rename `...-macd-momentum/memory/` path):

- `project_signal_source.md` — DIF retirement, PA is the active lane
- `project_vcs_jj.md` — jj (Jujutsu) is the VCS, not raw git
- `project_baselines_infra.md` — baselines/ JSONs are the single source of truth
- `project_broad_market_suppress.md` — DIA/SPY/XLU H2 suppression is structural
- `feedback_options_style.md` — recommend + parallelize when listing options
- `feedback_signal_must_have_macro.md` — every signal report must lead
  with multi-TF + trend structure + context bull/bear
- `feedback_regime_gate_not_portable.md` — bottom-reversal lanes can't take a trend filter
- `MEMORY.md` — index

`CLAUDE.md` at the repo root carries the original wiki-generation task
brief (historical, completed 2026-05-21).  Future Claude sessions
should treat **this STATUS.md** as the primary "where things are"
document, not CLAUDE.md.
