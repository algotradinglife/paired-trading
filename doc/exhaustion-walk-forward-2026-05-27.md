# Exhaustion bottom-side cells — walk-forward K=3 (2026-05-27)

**Status**: ALL five tested cells (`bottom+conf=high`, `bottom+wick=low`,
`bottom+wick=high`, `bottom+volume=high`, `bottom+volume=low`) NOT
graduation-ready. Each axis (confidence, wick, volume) is a regime
*predictor* rather than a filter — each fold has some bucket that beats
baseline, but it's a different bucket per fold, so no fixed-direction
rule can ship.

## Setup

- Cells evaluated:
  - `direction=bottom AND confidence_tercile=high` (precision-report top candidate)
  - `direction=bottom AND wick_ratio_tercile=low` (precision-report alternate)
  - `direction=bottom AND wick_ratio_tercile=high` (precision-report alternate)
  - `direction=bottom AND volume_ratio_tercile=high` (Brooks "signal bar w/ above-avg volume" prior)
  - `direction=bottom AND volume_ratio_tercile=low` (Brooks-contrarian / quiet-capitulation hypothesis)
- Horizon: 20 bars
- Methodology: same as `analyze_b_topology_oos.py` R5 walk-forward
  - K=3 equal-count chunks sorted by event timestamp
  - fold1: train chunk[0], test chunk[1]
  - fold2: train chunk[0]+chunk[1], test chunk[2]
  - Confidence tercile edges from TRAIN's FULL event pool (tops+bottoms,
    same population `analyze_exhaustion_pool` uses to define
    `conf_tercile`); applied to TEST (out-of-range clip)
  - Horizon-overlap purge: drop train rows within `horizon × 3 + 14 = 74` calendar days of test cutoff
- Bootstrap CI: 5000 reps, RNG seed 42
- Pass gate (R5 standard): per fold, test cell n>=15 AND >=10pp hit
  uplift over same-fold test baseline AND bootstrap CI excludes zero

Two configurations tested:
- **Pooled** (CN + CN_COMMODITY combined, n=194 bottom events)
- **CN_COMMODITY only** (n=139 bottom events, largest single pool)

## Results — `bottom + conf=high`

| Config | Fold | n_test | hit | baseline | uplift | mean | CI95 |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | fold1 | 11 | 54.5% | 51.3% | +3.2pp | +2.68% | [-0.68, +7.23] |
| pooled | fold2 | 19 | 78.9% | 60.0% | +18.9pp | +7.78% | **[+2.15, +13.47]** |
| cn_comm | fold1 | 5 | 40.0% | 57.8% | -17.8pp | +4.41% | [-1.50, +13.65] |
| cn_comm | fold2 | 14 | 78.6% | 54.8% | +23.8pp | +3.38% | [-1.36, +7.68] |

R5 standard (test n>=15 AND >=10pp uplift AND CI excludes 0):

| Config | Fold | n>=15 | >=10pp uplift | CI excludes 0 | Verdict |
|---|---|---:|---:|---:|:---:|
| pooled | fold1 | ✗ (n=11) | ✗ | ✗ | FAIL |
| pooled | fold2 | ✓ | ✓ | ✓ | **PASS** |
| cn_comm | fold1 | ✗ (n=5) | ✗ | ✗ | FAIL |
| cn_comm | fold2 | ✗ (n=14) | ✓ | ✗ | FAIL |

Pooled-fold1 is the binding constraint everywhere: train chunk[0]
(2017–2021) produces only 11–14 test events at conf=high in chunk[1]
(2021–2024), well under R5's n>=15 minimum. Pooled-fold2 (recent
chunk[2], 2024–2026) is the only PASS — strong (n=19, 79% hit, +18.9pp
uplift, CI [+2.15, +13.47]) but R5 requires BOTH test folds to pass.

## Results — `bottom + wick=low`

| Config | Fold | n_test | hit | baseline | uplift | mean | CI95 |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | fold1 | 39 | 56.4% | 51.3% | +5.1pp | +3.21% | [+0.51, +6.01] |
| pooled | fold2 | 31 | 48.4% | 60.0% | **−11.6pp** | +1.38% | [-2.14, +5.17] |
| cn_comm | fold1 | 21 | 61.9% | 57.8% | +4.1pp | +4.43% | [-0.23, +9.15] |
| cn_comm | fold2 | 26 | 42.3% | 54.8% | **−12.5pp** | **−1.74%** | [-4.37, +0.93] |

R5 standard:

| Config | Fold | n>=15 | >=10pp uplift | CI excludes 0 | Verdict |
|---|---|---:|---:|---:|:---:|
| pooled | fold1 | ✓ | ✗ (+5.1pp) | ✓ | FAIL |
| pooled | fold2 | ✓ | ✗ (−11.6pp) | ✗ | FAIL |
| cn_comm | fold1 | ✓ | ✗ (+4.1pp) | ✗ | FAIL |
| cn_comm | fold2 | ✓ | ✗ (−12.5pp) | ✗ | FAIL |

`bottom+wick=low` flips harder than `bottom+conf=high`: the n-floor
issue is gone (all four cells have n=21–39, comfortably above 15) but
fold2 — the SAME 2024-2026 chunk where conf=high looked PASS-grade —
**inverts to negative for wick=low** on CN_COMMODITY (−1.74% mean,
42% hit) and dilutes to break-even on pooled. The two features are
not co-monotonic in regime sensitivity: the recent regime favors
high-confidence bottoms but disfavors low-wick bottoms.

## Results — `bottom + wick=high`

| Config | Fold | n_test | hit | baseline | uplift | mean | CI95 |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | fold1 | 22 | 31.8% | 51.3% | **−19.5pp** | −0.18% | [-2.51, +2.63] |
| pooled | fold2 | 24 | 62.5% | 60.0% | +2.5pp | +6.33% | [+1.79, +11.11] |
| cn_comm | fold1 | 11 | 36.4% | 57.8% | **−21.4pp** | +1.59% | [-2.62, +6.74] |
| cn_comm | fold2 | 17 | 64.7% | 54.8% | +9.9pp | +3.18% | [-0.98, +7.35] |

R5 standard:

| Config | Fold | n>=15 | >=10pp uplift | CI excludes 0 | Verdict |
|---|---|---:|---:|---:|:---:|
| pooled | fold1 | ✓ | ✗ (−19.5pp) | ✗ | FAIL |
| pooled | fold2 | ✓ | ✗ (+2.5pp) | ✓ | FAIL |
| cn_comm | fold1 | ✗ (n=11) | ✗ (−21.4pp) | ✗ | FAIL |
| cn_comm | fold2 | ✓ | ✗ (+9.9pp) | ✗ | FAIL |

Same regime split as wick=low BUT flipped: in fold1 (2017→2021 train,
2021→2024 test) wick=high collapses to ~33% hit (vs the 56% wick=low
showed in the same fold), while in fold2 wick=high holds the +EV that
wick=low loses. The wick axis isn't a regime-stable filter at all —
it's a regime *predictor*: which wick tercile leads depends on which
window you're in.

## Results — `bottom + volume_ratio=high` (Brooks "above-avg volume" prior)

| Config | Fold | n_test | hit | baseline | uplift | mean | CI95 |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | fold1 | 13 | 30.8% | 51.3% | **−20.5pp** | **−2.50%** | **[-4.73, -0.48]** |
| pooled | fold2 | 21 | 71.4% | 60.0% | +11.4pp | +2.57% | [-0.83, +5.82] |
| cn_comm | fold1 | 10 | 20.0% | 57.8% | **−37.8pp** | **−3.38%** | **[-6.06, -0.90]** |
| cn_comm | fold2 | 17 | 64.7% | 54.8% | +9.9pp | +0.96% | [-2.64, +4.16] |

R5 standard: 0/2 PASS in both configs. fold1 (2021→2024 test) is
**actively negative** for high-volume bottoms — pooled mean −2.50% with
CI excluding zero on the WRONG side. This is the opposite of Brooks's
"signal bar with above-average volume" prior in this CN sample.

## Results — `bottom + volume_ratio=low` (Brooks-contrarian / quiet bottom)

| Config | Fold | n_test | hit | baseline | uplift | mean | CI95 |
|---|---|---:|---:|---:|---:|---:|---:|
| pooled | fold1 | 30 | 70.0% | 51.3% | **+18.7pp** | +3.82% | **[+1.14, +6.55]** |
| pooled | fold2 | 29 | 44.8% | 60.0% | **−15.2pp** | +2.16% | [-1.50, +6.28] |
| cn_comm | fold1 | 14 | 78.6% | 57.8% | **+20.8pp** | +5.89% | **[+1.42, +10.19]** |
| cn_comm | fold2 | 21 | 33.3% | 54.8% | **−21.5pp** | **−2.37%** | **[-4.49, -0.19]** |

R5 standard: **pooled fold1 PASSES** (n=30, +18.7pp uplift, +3.82%,
CI [+1.14, +6.55]). The only other PASS-grade single-fold cell across
all five tested is `conf=high` pooled fold2 above; those two passes
are in opposite folds and on different feature axes — no single rule
captures both. fold2 here inverts in both configs and CN_COMM fold2
turns actively negative (−2.37%, CI excludes zero on wrong side).
1/2 on pooled, 0/2 on CN_COMM — still NOT graduation-ready under R5.

The volume axis swap-flips exactly like the wick axis: fold1 favors
LOW volume (quiet bottoms), fold2 favors HIGH volume. Volume=high in
fold1 is the WORST cell tested overall (pooled −2.50%); volume=low
in fold2 CN_COMM is the runner-up worst (−2.37%). Each fold flips
which bucket is the winner.

## Read

The +6.15% / +3.08% in-sample mean for `bottom+conf=high` (per
`exhaustion-precision-cn-2026-05-27.md`) is REGIME-DRIVEN:

- 2024-04 onward (fold2 test in both configs): ~79% hit, +7.78% mean
  pooled / +3.38% cn_commodity. Very strong.
- 2021-02 → 2024-04 (pooled fold1 test): 54.5% hit, +2.68% mean,
  n=11 — modestly positive but below R5's n>=15 floor.
- 2017-2020 mid-period (cn_commodity fold1 test): only 40% hit, +4.41%
  mean with wide CI [-1.50, +13.65], n=5 — the cell is too sparse to
  draw any conclusion.

This is the same pattern Codex R5 documented for the CN policy: the
4.3x sample didn't produce any walk-forward-stable B-topology cells.
Adding a NEW detector type doesn't automatically yield walk-forward
stability — the same regime-conditionality applies.

## Why fold1 looks so different (and why every axis inverts)

Two non-mutually-exclusive hypotheses:
1. **Regime shift after 2024**: CN futures volatility / mean-reversion
   character changed post 2024 reforms; the detector's sweet spot is
   capturing a regime feature, not a universal pattern.
2. **Sample drift in tercile edges**: train edges shift across folds
   (pooled wick lo edge fold1=0.5588, fold2=0.5455). Modest but
   re-tiers some marginal events differently than later folds.

Each tested axis behaves as a regime *predictor*, not a filter:

| Axis | fold1 (2021–2024 test) favors | fold2 (2024–2026 test) favors |
|---|---|---|
| confidence | (low n in fold1) | high — only PASS for conf=high pooled |
| wick_ratio | LOW (wick=low +5.1pp; wick=high −19.5pp) | HIGH (wick=high +2.5pp; wick=low −11.6pp) |
| volume_ratio | **LOW** (volume=low +18.7pp; volume=high −20.5pp) | high-ish (volume=high +11.4pp; volume=low −15.2pp) |

Each fold has *some* tercile per axis that beats baseline — but it's
a different tercile each time, so no fixed-direction filter ships.

The lack of CI clearance for conf=high even where uplift is large
(cn_comm fold2 +23.8pp uplift but CI [-1.36, +7.68]) is an n-problem.
For wick=low and volume=low fold2 it's an UPLIFT problem (n is
comfortable, but the cell tracks baseline or worse). The wick=high
fold1 and volume=high fold1 cells are the worst — they collapse
*below* the baseline-bottom rate, sometimes with CI excluding zero on
the wrong side (volume=high fold1: pooled −2.50% [-4.73, -0.48];
cn_comm −3.38% [-6.06, -0.90]).

## Implication for graduation

**DO NOT ship any single-axis exhaustion cell as a PolicyDecision rule
in envelope v1.5.** All five tested cells (`conf=high`, `wick=low`,
`wick=high`, `volume=high`, `volume=low`) fail the R5 standard.
Operationally:

1. **No CN-exhaustion policy entry in v1.5** until either a larger sample
   or a regime-conditional rule has been validated walk-forward.
2. **Keep `exhaustion_events` in the envelope** (the events ARE useful
   diagnostics) but consumers must apply their own filtering — the
   engine does NOT promise a stable +EV.
3. **Continue to use BOTTOM events as a research signal** for hand
   review and strategy ideation — the recent-regime performance is real
   even if not generalizable.
4. **Do not raise confidence-band weights** in the detector itself; the
   confidence formula is fine — the issue is downstream regime-dependence,
   not formula calibration.

## Open paths that could change the verdict

1. **Time-decay weighted training**: weight recent train events more
   heavily so the train-derived tercile edges track regime drift. Risk:
   re-introduces overfitting to recent regime.
2. **Regime indicator conditioning** (D4 from R5 review): pre-specify a
   regime feature (e.g. weekly trend strength, VIX-analog volatility)
   and condition the rule on it. Both folds may pass within the
   "favorable regime" subset even if pooled fails.
3. **Larger sample**: extend CN intraday history further (qveris max
   was 14y; not feasible to grow without alternative provider).
4. ~~bottom+wick=high pending~~ — tested, also FAIL. The wick
   axis is fully regime-fragile.
5. ~~bottom+volume_ratio terciles pending~~ — tested, same regime-flip
   pattern. Pooled volume=low fold1 PASSES in isolation (n=30, +18.7pp
   uplift, +3.82% CI [+1.14, +6.55]) — one of only two PASS-grade
   single-fold cells (the other is conf=high pooled fold2, on a
   different axis and a different fold). But fold2 reverses to −15.2pp
   uplift, so still NOT graduation-ready. The "quiet capitulation"
   hypothesis (Brooks-contrarian: low-volume bottoms reverse harder) is
   the most intriguing finding here but needs a regime indicator to
   ship safely.

## Data

- Inputs: `src/data/review/exhaustion_pool_cn.csv` +
  `src/data/review/exhaustion_pool_cn_commodity.csv`
- Harness: `src/scripts/walk_forward_exhaustion.py`
- Reproduce:
  ```
  # bottom + conf=high (default cell):
  uv run python src/scripts/walk_forward_exhaustion.py \
    --csv src/data/review/exhaustion_pool_cn.csv \
    --csv src/data/review/exhaustion_pool_cn_commodity.csv \
    --horizon 20 -K 3

  # bottom + wick=low / wick=high / volume=low / volume=high:
  for FEAT in wick_ratio volume_ratio; do
    for BUCKET in low high; do
      uv run python src/scripts/walk_forward_exhaustion.py \
        --csv src/data/review/exhaustion_pool_cn.csv \
        --csv src/data/review/exhaustion_pool_cn_commodity.csv \
        --horizon 20 -K 3 --feature "$FEAT" --bucket "$BUCKET"
    done
  done
  ```
