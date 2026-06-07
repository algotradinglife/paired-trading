# Exhaustion detector — forward-return precision (US daily, 2026-05-27)

**Status**: in-sample, single-pool, look-ahead corrected. Reads negative
for top events; bottom events are inconclusive (n=12, CI crosses zero).

> **Look-ahead correction (2026-05-27)**: an earlier pass of this study
> reported a marginally significant positive bottom result (+4.67%
> [+0.11%, +9.67%], n=13). Codex review flagged that the weekly bars in
> `data/raw/` are stamped at week-start with full-week OHLC, so a
> Tuesday daily candidate could "see" Wednesday–Friday weekly data when
> the detector slices `weekly_bars[timestamp <= daily_ts]`. The script
> now shifts weekly timestamps forward by 7 days (last-completed-week
> semantics) before passing to the detector. Total event count drops
> 137 → 133, and the bottom CI now straddles zero. This matches the
> known pitfall in user memory `feedback-multi-tf-sweet-spot-timing-pitfall`.

## Setup

Pool from [`exhaustion-recall-lift-2026-05-27.md`](exhaustion-recall-lift-2026-05-27.md):
- 10 US ETFs × 5y daily
- Topology A (D + 1h + W), strict 3-TF aligned
- `min_bars_in_segment=20`, `min_wick_ratio=0.4`
- Weekly bars lagged by 7 days (no-leak posture)

Methodology mirrors `analyze_sweet_spots_pool.py`:
- `signed_forward_return` at h=5/10/20: positive when price moves in the
  predicted reversal direction (down for tops, up for bottoms)
- Bootstrap 95% CI on the mean (5000 resamples, RNG seed 42)
- Tercile edges computed from labeled rows only (those with valid `ret_h{strat_h}`)

## Headline result (h=20, leak-corrected)

| Direction | n | Hit rate | Mean signed return | CI95 |
|---:|---:|---:|---:|---:|
| top | 120 | 34.2% | **-2.93%** | **[-4.48%, -1.46%]** |
| bottom | 12 | 66.7% | +3.90% | **[-0.72%, +9.17%]** (CI crosses 0) |
| all | 132 | 37.1% | -2.31% | [-3.88%, -0.94%] |

**CI on tops (h=20) excludes zero on the WRONG side**: the strict 3-TF
aligned top-exhaustion pattern is a *continuation* in this US sample, not
a reversal. **Bottoms now inconclusive** after leak fix.

## Horizon scan

| Horizon | Direction | n | Hit % | Mean % | CI95 |
|---:|---:|---:|---:|---:|---:|
| 5 | top | 120 | 42.5 | -0.23 | [-0.74, +0.25] |
| 5 | bottom | 12 | 58.3 | +0.99 | [-0.87, +3.06] |
| 10 | top | 120 | 36.7 | -1.71 | [-2.65, -0.82] |
| 10 | bottom | 12 | 75.0 | +2.59 | [-0.27, +6.06] |
| 20 | top | 120 | 34.2 | -2.93 | [-4.48, -1.46] |
| 20 | bottom | 12 | 66.7 | +3.90 | [-0.72, +9.17] |

Tops degrade with horizon. Bottoms grow positive with horizon but CI never
clears zero (n=12 is the binding constraint).

## Stratification (h=20)

### Confidence tercile (leak-corrected)

| Cell | n | Hit % | Mean % | CI95 |
|---:|---:|---:|---:|---:|
| top conf=low | 40 | 37.5 | -2.40 | [-4.68, -0.35] |
| top conf=mid | 40 | 17.5 | -4.34 | [-6.58, -2.35] |
| top conf=high | 40 | 47.5 | -2.04 | [-5.46, +0.77] |
| bottom conf=low | 4 | 50.0 | +5.01 | [-7.24, +18.87] |
| bottom conf=mid | 4 | 100.0 | +3.40 | [+0.61, +6.19] |
| bottom conf=high | 4 | 50.0 | +3.28 | [-0.71, +7.28] |

High-confidence tops do NOT recover: 48% hit / -2.04% mean. The CI just
crosses zero — no monotone "higher confidence = better top" trend.
**High-confidence bottoms also degrade** after the leak fix (was n=5,
+5.40%, [+0.38, +10.43]; now n=4, +3.28%, [-0.71, +7.28] — leak gave
one extra event into this cell with above-average forward return).

### Wick-ratio tercile (leak-corrected)

| Cell | n | Hit % | Mean % | CI95 |
|---:|---:|---:|---:|---:|
| top wick=low | 40 | 35.0 | -3.00 | [-5.81, -0.51] |
| top wick=mid | 39 | 28.2 | -4.47 | [-7.73, -1.59] |
| top wick=high | 41 | 39.0 | -1.39 | [-2.91, +0.06] |
| bottom wick=low | 4 | 75.0 | +7.40 | [-6.77, +21.26] |
| bottom wick=mid | 5 | 80.0 | +3.53 | [-0.43, +7.18] |
| bottom wick=high | 3 | 33.3 | -0.16 | [-0.91, +0.93] |

Same story: even the "cleanest" top reversal candle (high wick) only
brings the CI to [-2.91, +0.06] — touching zero, not clearing it.
Bottom high-wick cell (n=3) now slightly negative — confirms the leak
was the source of the previous bottom-side optimism.

## Reconciling with the recall report

Recall lift on down swings was +9.1 to +13.7pp — exhaustion does *catch*
historical major peaks the divergence detector misses. **The catch is
that it also fires many times on continuations**, so per-event precision
is negative even though per-swing recall is positive.

Concretely on tops in this sample (leak-corrected):
- 120 top events fired
- A small share preceded actual ≥3-5% declines (the recall-lift slice)
- The majority fired into ongoing rallies → trend continued → mean -2.93%

Note: the recall-lift report was NOT recomputed with the leak-corrected
detector configuration. If recall is rerun with weekly lag, the +9–14pp
down-swing lift may shrink (fewer top events fire → fewer catches).

This is the classic "Brooks with-trend bias" — strong trending uptrends
in US large-cap equities (2021-05 → 2026-05 is mostly bullish) generate
many bars matching the "tall upper wick + close in lower half + segment
extreme + 3-TF aligned" pattern, but most of them are just routine pauses
within a continuing trend.

## Operational read

**For US equities at this configuration, the exhaustion detector should
NOT be used as a long-exit or short-entry signal as-is.**

Open paths:
1. **CN futures re-run** — expect bottoms-dominant (bear-leaning regime
   asymmetric to US 5y). May invert this verdict.
2. **Filter on context_features** — split top-exhaustion sample by
   higher-TF confluence patterns NOT captured in trend_side alone (e.g.
   weekly near-zero-axis vs strong-trend). The 3-TF strict gate as
   currently defined just requires same-direction trending; it does not
   distinguish "weekly near a recent low + daily peaking" from "weekly
   strongly trending + daily peaking" — only the former should imply
   exhaustion.
3. **Lower `min_bars_in_segment`** to catch shorter-segment reversals;
   raise to require deeper extension and see if the late-segment events
   are cleaner.
4. **Walk-forward K=3** as the R5 standard — confirm whether the negative
   top result holds OOS or is just sample-window 2021-2026 specific.
5. **Hourly TF** — options strategies live there; the regime mix on 1h is
   different (faster mean-reversion).

## Data

- `src/data/review/exhaustion_pool_us.csv` — 133 per-event rows
  (leak-corrected, weekly bars lagged by 7 days). 132 are labeled at
  h=5/10/20; the most recent event has fewer than 20 bars of forward
  data so `ret_h5/10/20` are NaN there (`signed_forward_return` returns
  None when `idx + horizon >= len(bars)`). The summary tables drop
  unlabeled rows. Columns: symbol, candidate_bar_idx, timestamp,
  direction, wick_ratio, confidence, bars_in_segment, n_completed_cycles,
  volume_ratio, ret_h5, ret_h10, ret_h20.
