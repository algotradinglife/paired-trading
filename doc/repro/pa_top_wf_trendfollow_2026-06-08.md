# PA TOP walk-forward — TREND-FOLLOW frame — 2026-06-08

Step-2 of the put-MVP investigation.  C4's bottom-mirrored frame
(`stop = 1.5×ATR`, `max_hold = 40 bars`, no phase gate; treated as
"counter-trend" implicitly because it short-fades a swing high) found
zero promotable cells.  Hypothesis under test: the broken piece was
the **frame**, not the **strategy** — a put thesis is naturally
trend-following (you short into developing weakness, hold for a
larger move, give it room) so a counter-trend frame is the wrong yard
stick.

This memo re-runs the same grid under a trend-following frame and
compares apples-to-apples with the C4 numbers.

## Headline

**Trend-following frame finds zero promotable cells either.**  The
put thesis fails on its own merits under both frames; the broken
piece is the strategy, not the frame.  Concretely:

- Under `--frame trend_follow` no `(pool × phase × h_rel × context ×
  top_div)` cell meets the promotion gate
  (`n_oos ≥ 20`, `EV_oos > 0`, stable OOS-fold sign).
- The trend_follow frame **degrades** more cells than it improves: of
  the 10 cells with `n_oos ≥ 20` in both frames, 4 flip from positive
  to negative EV, 5 stay negative and only 1 stays positive — and
  that one (`cn_commodity_daily × TR_FORMING × opposing × div=T`,
  +0.073 R → +0.104 R, n = 20) was already C4's "closest contender"
  with sign-flipping OOS folds.  The improvement is fold-rebalancing,
  not stabilisation.
- The user-emphasised `cn_metal_daily` pool gets **much worse** under
  trend_follow: pool-level `h=opp` EV falls from −0.15 R to −0.41 R,
  and 5 individual cells become stable-negative.
- The user-emphasised `cn_metal_daily × h=supporting` cell stays
  decisively negative under both frames (−0.42 R counter-trend,
  −0.42 R trend_follow, n = 41 / 33).
- `cn_bond_daily × supporting` is the **only** rollup that improves
  meaningfully (−0.286 → −0.040, n = 12) — but n = 12 < 20 promotion
  gate, and one fold (F3) is +1.17 R on n = 3 (i.e. 1–2 trades doing
  the lifting).  Not actionable.

Important factual correction to the C4 memo: **the C4 grid DID
evaluate h=supporting**, contrary to the read that "we never tested
supporting".  The grid's `GRID_KEYS` includes `h_rel`, so both
`opposing` and `supporting` rows appear in the original
`pa_top_wf_grid.csv` (verified — 23 supporting rows out of 62).  The
memo's pool-level rollup table did show supporting EVs (e.g.
`us_60min supporting −0.049 R`, `cn_metal_daily supporting
−0.419 R`).  The negative C4 verdict therefore covers both branches,
not just opposing.

## Run parameters

| Parameter             | counter_trend (C4)         | trend_follow (this run)    |
|-----------------------|----------------------------|----------------------------|
| `stop_mult`           | 1.5 × ATR                  | 2.5 × ATR                  |
| `max_hold`            | 40 bars                    | 80 bars                    |
| Phase gate (entry)    | none — all phases retained | reject `BULL`; keep `BEAR`, `TR_FORMING`, `UNCLEAR` |
| `min_quality`         | 0.3                        | 0.3                        |
| `min_gap`             | 10                         | 10                         |
| `min_l_legs`          | 2                          | 2                          |
| Detector              | `PATopDetector`            | `PATopDetector`            |
| K=3 folds             | same                       | same                       |
| Grid keys             | `phase × h_rel × context × top_div` | same              |

The script is the same (`src/scripts/backtest_pa_top_grid.py`) with
a new `--frame {counter_trend,trend_follow}` switch.  `counter_trend`
preserves bit-exact C4 behaviour; `trend_follow` swaps in the values
above.

## Fires per pool (after `min_gap` dedup, after phase gate)

| Pool                | counter_trend fires | trend_follow fires | Δ      |
|---------------------|--------------------:|-------------------:|-------:|
| us_60min            |              3 351  |             3 147  |  −204  |
| cn_metal_daily      |                157  |               141  |   −16  |
| cn_bond_daily       |                131  |               111  |   −20  |
| cn_commodity_daily  |                222  |               212  |   −10  |

The trend_follow phase gate (drop BULL) removes 6–10 % of fires per
pool — small because BULL was already a minority of TOP entries.

## Pool × h_rel rollup (OOS, all phases / contexts / divergence)

Weighted by per-cell n_oos so the comparison is on identical samples.

| Pool                | h_rel       | n_oos | EV counter_trend | EV trend_follow | Δ       |
|---------------------|-------------|------:|-----------------:|----------------:|--------:|
| us_60min            | opposing    | 1664→1527 |  −0.031 R  |  **−0.059 R**   | −0.028  |
| us_60min            | supporting  |  742→726  |  −0.049 R  |  **−0.095 R**   | −0.046  |
| cn_metal_daily      | opposing    |   54→48   |  −0.153 R  |  **−0.411 R**   | −0.258  |
| cn_metal_daily      | supporting  |   41→33   |  −0.419 R  |   −0.416 R      | +0.003  |
| cn_bond_daily       | opposing    |   29→25   |  −0.275 R  |   −0.331 R      | −0.056  |
| cn_bond_daily       | supporting  |   14→12   |  −0.286 R  |  **−0.040 R**   | **+0.246** |
| cn_commodity_daily  | opposing    |   97→92   |  **+0.043 R**  |   −0.056 R   | **−0.099** |
| cn_commodity_daily  | supporting  |   41→41   |  −0.155 R  |   −0.117 R      | +0.038  |

(n drops slightly because the phase gate removes BULL entries.)

Six of the eight rollup cells get **worse** under trend_follow.  The
two that improve are noise-band (`cn_metal_daily supporting +0.003`)
and small-n (`cn_bond_daily supporting +0.246` rests on n = 12 with
+1.17 R on 3 F3 trades).  The headline positive cell from C4
(`cn_commodity_daily opposing +0.043`) **flips negative**.

## Per-pool best & worst cells under trend_follow

### us_60min — best/worst (n_oos ≥ 5)

| Phase       | h_rel       | div | n_oos | EV_oos    | F1     | F2     | F3     | stable |
|-------------|-------------|-----|------:|-----------|--------|--------|--------|--------|
| BEAR        | supporting  | F   |  42   | −0.028 R  | −0.469 | −0.072 | +0.411 | no     |
| TR_FORMING  | opposing    | F   | 964   | −0.033 R  | −0.020 | −0.002 | −0.063 | yes (−) |
| TR_FORMING  | supporting  | T   | 224   | −0.096 R  | −0.117 | −0.038 | −0.102 | yes (−) |
| BEAR        | supporting  | T   |  11   | −0.318 R  | +0.000 | −1.000 | −0.500 | no     |
| BEAR        | opposing    | F   |  17   | −0.294 R  | +0.250 | −0.300 | −0.563 | no     |

US 60min is flat-to-negative everywhere; the largest n cell (964) is
stable-negative.  BEAR phase under trend_follow is consistently
worse than under counter_trend.

### cn_metal_daily — best/worst (n_oos ≥ 5)

| Phase       | h_rel       | div | n_oos | EV_oos    | F1     | F2     | F3     | stable |
|-------------|-------------|-----|------:|-----------|--------|--------|--------|--------|
| TR_FORMING  | opposing    | T   |  12   | −0.313 R  | −0.167 | −1.000 | −0.282 | yes (−) |
| TR_FORMING  | supporting  | T   |  25   | −0.350 R  | −0.433 | −0.347 | −0.303 | yes (−) |
| TR_FORMING  | opposing    | F   |  33   | −0.393 R  | −0.875 | −0.154 | −0.331 | yes (−) |
| TR_FORMING  | supporting  | F   |   7   | −0.570 R  | −1.000 | −0.330 | −0.667 | yes (−) |

cn_metal_daily under trend_follow has **no positive cell at any n**.
Every TR_FORMING combination is stable-negative.  This is the
strongest empirical evidence that the put thesis on CN metals is
broken at the strategy level, not the frame level.

### cn_bond_daily — best/worst (n_oos ≥ 5)

| Phase       | h_rel       | div | n_oos | EV_oos    | F1     | F2     | F3     | stable |
|-------------|-------------|-----|------:|-----------|--------|--------|--------|--------|
| TR_FORMING  | opposing    | T   |   9   |  0.000 R  | −0.333 | −0.167 | +0.500 | no     |
| TR_FORMING  | supporting  | T   |  12   | −0.040 R  | −0.167 | −0.583 | +1.172 | no     |
| TR_FORMING  | opposing    | F   |  15   | −0.552 R  | −1.000 | −1.000 | −0.160 | yes (−) |

The "marginal positive" supporting cell rests entirely on F3
(+1.172 R on n = 3).  This is fold noise, not a real edge.

### cn_commodity_daily — best/worst (n_oos ≥ 5)

| Phase       | h_rel       | div | n_oos | EV_oos    | F1     | F2     | F3     | stable |
|-------------|-------------|-----|------:|-----------|--------|--------|--------|--------|
| TR_FORMING  | opposing    | T   |  20   | +0.104 R  | −0.583 | +0.500 | +0.297 | no     |
| TR_FORMING  | supporting  | T   |  38   | −0.115 R  | −0.545 | +0.443 | −0.165 | no     |
| TR_FORMING  | opposing    | F   |  63   | −0.140 R  | −0.377 | +0.095 | −0.131 | no     |

The closest contender from C4 (TR_FORMING × opp × div=T) actually
**improves** under trend_follow (+0.073 → +0.104) but the OOS folds
are still sign-flipping (F1 −0.58 / F2 +0.50 / F3 +0.30) — fails the
stability gate.  Indistinguishable from noise at n = 20.

## Side-by-side: same cell, both frames (n_oos ≥ 20 in both)

| Pool                | Phase       | h_rel       | div | n_oos | EV ct   | EV tf   |
|---------------------|-------------|-------------|-----|------:|---------|---------|
| cn_commodity_daily  | TR_FORMING  | opposing    | T   |  20   | +0.073  | **+0.104** |
| cn_commodity_daily  | TR_FORMING  | supporting  | T   |  38   | −0.220  | −0.115  |
| cn_commodity_daily  | TR_FORMING  | opposing    | F   |  63   | **+0.012**  | **−0.140** |
| cn_metal_daily      | TR_FORMING  | supporting  | T   |  25   | −0.244  | −0.350  |
| cn_metal_daily      | TR_FORMING  | opposing    | F   |  33   | −0.264  | −0.393  |
| us_60min            | BEAR        | supporting  | F   |  42   | **+0.023**  | **−0.028** |
| us_60min            | TR_FORMING  | opposing    | F   | 964   | **+0.012**  | **−0.033** |
| us_60min            | TR_FORMING  | supporting  | T   | 224   | **+0.011**  | **−0.096** |
| us_60min            | TR_FORMING  | supporting  | F   | 449   | −0.079  | −0.096  |
| us_60min            | TR_FORMING  | opposing    | T   | 540   | −0.090  | −0.097  |

Sign-flip summary:
- ct− → tf+ : **0** (no negative cell rescued by trend_follow)
- ct+ → tf− : **4** (four marginally positive cells flipped negative)
- Stayed negative: 5
- Stayed positive: 1 (the small-n, sign-flipping commodity cell)

Wider stop + longer hold does NOT systematically lift the put EV.
On the contrary, it costs ~2–10 bp of EV across the cells where the
sample is non-trivial.  Reading: holding losing put trades longer
just lets them lose more before time-stop closes them; the asymmetry
the trend-follow logic assumes (winners run, losers stop quick)
doesn't materialise in this top detector's signal distribution.

## Verdict — what to do with `PATopDetector.policy_weight()`

**Keep all weights at 0.0.**  Both frames vindicate the placeholder.
No cell qualifies as actionable under any reasonable promotion gate:

- No promote candidates under either frame.
- The only cell that arguably "improved" (cn_bond_daily supporting)
  is n = 12 with one-fold dominance.
- The pools the user wanted to work (`cn_metal_daily`) got worse, not
  better, under trend_follow.

No `policy_weight()` entries are recommended.  The TOP lane stays
no-emit pending a substantively different signal source.

The Xiao MVP put thesis as currently constituted (PA `h2_top` ×
phase × h_rel × top_div) **does not have an edge** in either frame,
on either CN or US pools, at the daily or 60min timeframes covered.

## Honest assessment for the user

The user's request was clear: "puts must be in MVP, run it under a
trend-following frame."  We did.  The trend-following frame did not
find evidence that the MVP put thesis works; if anything it produced
weaker numbers than the counter-trend frame on the same cells.

This is not a "the frame was right after all, here's the green light"
result.  Honestly reporting:

- 0 promotable cells under trend_follow (matches 0 under
  counter_trend).
- The cell that improved most in % terms (cn_bond_daily supporting,
  EV from −0.29 to −0.04) is n = 12 with F3 dominance.  This is the
  kind of small-n positive that gets a +0.0 placeholder in the
  policy table, not a real weight.
- The bigger effect is the *worsening* of US 60min and cn_metal_daily
  under the wider-stop/longer-hold treatment.

The put thesis still belongs in the MVP per the user's locked
constraint, but as a **zero-weight slot** until a different signal
source (e.g. exhaustion or weekly DIF) lights it up.  Forcing a
weight onto a TOP cell under either frame would mean acting on
noise.

## Next-experiment proposals (3)

If the user wants to keep iterating on puts before committing to a
non-PA signal source, these are the three I'd run in priority order:

1. **5-source grid: add the 15min PA confirmation as a 5th dim** for
   `cn_metal_daily` and `cn_commodity_daily`.  C4's pa_baseline memo
   established a 0.45 weight on `h=supporting` × `15m_confirmed` for
   BOTTOM on CN metals; if a similar lift exists on TOP, it would
   show up in the per-pool table for those two pools.  Cheap to
   add — `score_today` already has the 15min confirmation helper.

2. **Per-pool stop/hold tuning** rather than one-size-fits-all.  US
   60min and CN daily probably want different stops because their
   ATR/bar distributions differ by an order of magnitude.  A 2×2 grid
   of (stop_mult ∈ {1.5, 2.5}) × (max_hold ∈ {40, 80}) per pool would
   isolate whether the trend_follow loss on US 60min is the stop or
   the hold.

3. **Replace `PATopDetector` with an exhaustion-anchored entry.**  The
   working-bottom detector relies on H2 (failed-rally fade), which is
   a counter-trend pattern by construction; symmetrising it gives a
   counter-trend TOP detector.  A trend-following put thesis arguably
   wants an exhaustion / climax bar + lower-low confirmation, not an
   H2 mirror.  This would be Step-3 of the broader Module DIR brief
   (`exhaustion` was already deferred).

If none of the above land, the honest move is to **freeze puts at
weight 0 in the MVP** and document the negative finding rather than
manufacture a positive weight to satisfy the lock-in.

## Audit trail

- `src/scripts/backtest_pa_top_grid.py` — extended with `--frame
  {counter_trend, trend_follow}`.  counter_trend reproduces bit-exact
  C4 behaviour; trend_follow runs with `stop=2.5×ATR`, `max_hold=80`,
  `phase_allow={BEAR, TR_FORMING, UNCLEAR}` (BULL rejected).
- `data/review/pa_top_wf_grid.csv` — unchanged (C4 counter_trend
  reference; 62 rows).
- `data/review/pa_top_wf_grid_trend_follow.csv` — new (46 rows).
- `pytest tests/ -q` — 327 passed (no engine touch).

### Reproduce

```bash
cd src
.venv/bin/python scripts/backtest_pa_top_grid.py --frame counter_trend
.venv/bin/python scripts/backtest_pa_top_grid.py --frame trend_follow
```
