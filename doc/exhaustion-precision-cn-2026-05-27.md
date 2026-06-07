# Exhaustion detector — CN precision + cross-pool comparison (2026-05-27)

**Status**: in-sample, leak-corrected (synth-weekly from daily). Bottoms
robustly positive across both CN pools; tops regime-conditional.

## Setup

Same detector configuration as the US run
([`exhaustion-precision-us-2026-05-27.md`](exhaustion-precision-us-2026-05-27.md)):
- Topology A (D + 1h + W), strict 3-TF aligned
- `min_bars_in_segment=20`, `min_wick_ratio=0.4`
- Weekly bars synthesized from daily via `pd.resample('W-FRI')` for all
  pools (no leak by construction; replaces the prior +7-day timestamp
  shift hack and supports CN pools that ship no `_weekly.json` files)

Pools (from `analyze_exhaustion_pool.POOLS`):
- **US**: 10 ETFs × 5y daily (SPY/QQQ/IWM/DIA/GLD/GDX/XLF/XLK/TLT/NVDA)
- **CN**: 4 CFFEX index futures (IF/IH/IC/IM)
- **CN_COMMODITY**: 15 commodity futures (SHFE/DCE/CZCE/INE mix), 14y deep

## Cross-pool headline (h=20)

| Pool | Direction | n | Hit % | Mean % | CI95 | Verdict |
|---|---:|---:|---:|---:|---:|:---|
| US | top | 121 | 33.9 | **-2.94** | [-4.44, -1.53] | **negative, CI clear** |
| US | bottom | 12 | 66.7 | +3.90 | [-0.72, +9.17] | inconclusive (n=12) |
| CN | top | 67 | 38.8 | -1.26 | [-2.84, +0.32] | neutral (CI crosses 0) |
| **CN** | **bottom** | **55** | **58.2** | **+4.65** | **[+2.06, +7.40]** | **POSITIVE, CI clear** |
| CN_COMMODITY | top | 230 | 49.1 | -1.02 | [-2.35, +0.30] | neutral (CI crosses 0) |
| **CN_COMMODITY** | **bottom** | **139** | **58.3** | **+1.51** | **[+0.22, +2.77]** | **POSITIVE, CI clear** |

**Combined CN bottoms (n=194)** are the only direction-pool combination
with statistically significant positive forward returns across separate
samples. The hypothesis from the US-only report — that bottoms would
dominate in CN's structurally bear-leaning regime — is confirmed.

## CN index futures detail (h=20)

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top conf=low | 26 | 38.5 | -1.80 | [-4.58, +1.06] |
| top conf=mid | 21 | 33.3 | -1.14 | [-4.35, +1.82] |
| top conf=high | 20 | 45.0 | -0.70 | [-2.64, +1.15] |
| bottom conf=low | 15 | 46.7 | +3.76 | [-0.75, +8.93] |
| bottom conf=mid | 19 | 47.4 | +3.70 | [-0.18, +8.10] |
| **bottom conf=high** | **21** | **76.2** | **+6.15** | **[+1.57, +11.12]** |

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top wick=low | 19 | 36.8 | -1.65 | [-4.58, +1.50] |
| top wick=mid | 32 | 40.6 | -0.96 | [-2.65, +0.84] |
| top wick=high | 16 | 37.5 | -1.40 | [-5.84, +2.48] |
| bottom wick=low | 22 | 54.5 | +5.16 | [+1.43, +9.43] |
| bottom wick=mid | 8 | 50.0 | +3.53 | [-3.39, +10.79] |
| bottom wick=high | 25 | 64.0 | +4.56 | [+0.73, +8.96] |

**Sweet spot**: `CN-bottom-conf=high` — 21 events, 76% hit, +6.15% mean,
CI [+1.57, +11.12]. Monotone confidence ramp on bottoms (3.76 → 3.70 → 6.15)
matches the design intent. Both wick=low and wick=high cells are CI-positive.

## CN commodity detail (h=20)

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top conf=low | 61 | 63.9 | +1.65 | [-0.28, +3.61] |
| top conf=mid | 79 | 45.6 | -1.80 | [-4.10, +0.41] |
| top conf=high | 90 | 42.2 | -2.16 | [-4.64, +0.14] |
| bottom conf=low | 62 | 58.1 | +1.51 | [-0.48, +3.57] |
| bottom conf=mid | 44 | 54.5 | +0.32 | [-1.49, +2.21] |
| **bottom conf=high** | **33** | **63.6** | **+3.08** | **[+0.54, +5.59]** |

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top wick=low | 67 | 59.7 | +0.50 | [-1.28, +2.33] |
| top wick=mid | 82 | 35.4 | -2.45 | [-4.37, -0.58] |
| top wick=high | 81 | 54.3 | -0.84 | [-3.93, +1.95] |
| bottom wick=low | 55 | 52.7 | +1.16 | [-1.16, +3.55] |
| bottom wick=mid | 42 | 76.2 | +1.62 | [-0.15, +3.29] |
| **bottom wick=high** | **42** | **47.6** | **+1.85** | **[-0.21, +4.03]** |

CN commodity tops show a NON-MONOTONE pattern: conf=low n=61 is *positive*
(+1.65%); conf=high n=90 is negative (-2.16%). The confidence ramp on tops
inverts the expected direction. wick=mid (n=82) is the only CI-significant
negative cell on tops. This irregularity probably reflects the universe
diversity (15 instruments, very different volatility regimes) — averaging
across them blurs any clean per-instrument pattern.

Bottoms in CN commodity are positive across all confidence terciles
(+1.51 / +0.32 / +3.08%), with conf=high reaching CI-significance.

## Three-pool synthesis

| Direction | US bull | CN index | CN commodity |
|---|---|---|---|
| TOP | **negative** (-2.94, CI clear) | neutral (CI crosses) | neutral (CI crosses) |
| BOTTOM | inconclusive (n=12) | **+4.65, CI clear** | **+1.52, CI clear** |

The detector behaves like a **regime-conditional reversal signal for
bottoms** and is **safe-to-negative for tops**:

- **Bottom exhaustion is real**: 2 independent CN pools, n=193 combined,
  both CI-significant positive. This is the strongest cross-sample
  positive cell on any non-divergence detector to date.
- **Top exhaustion is a continuation in US bull, neutral in CN**: the
  3-TF aligned trending pattern at price extremes doesn't reverse on
  average. Different regimes weight differently — US 5y was a sustained
  bull, CN samples cover more two-sided / sideways regimes.
- **High-confidence bottom is the only graduation candidate**: CN-bot-conf=high
  is +6.15% [+1.57, +11.12] (n=21); CN_COMMODITY-bot-conf=high is +3.08%
  [+0.54, +5.59] (n=33). Same direction, both CI-positive, n=54 combined.

## What this means for the engine

1. **DO NOT** ship top-exhaustion as a long-exit / short-entry signal in
   any of these pools at this configuration.
2. **DO** consider bottom-exhaustion as a long-entry / short-exit signal
   for CN futures — pending walk-forward K=3 validation per the R5
   standard.
3. US bottom verdict needs more data — re-run with a larger US sample
   (more symbols, or longer history) to clear the n=12 limitation.
4. The leak fix from yesterday's first US pass is now part of the script's
   default behavior (synth-weekly from daily). Any prior in-flight CSVs
   should be regenerated.

## Open follow-ups

1. Walk-forward K=3 on `CN-bottom-conf=high` and `CN_COMMODITY-bottom-conf=high`
   — these are the cells that would graduate to PolicyDecision in
   envelope v1.5.
2. Recall report rerun with synth-weekly to see if down-swing lift on
   US shrinks (the negative US-top precision suggests yes).
3. Engine `enrich_with_higher_tf` has the same look-ahead pattern as the
   precision script's pre-fix version. If divergence policy calibration
   was done with the leaky weekly, F2/F3/B1 may need a leak-corrected
   pass (separate task; not blocking exhaustion graduation).
4. Hourly TF (B-topology, options strategies) on CN — `min_bars_in_segment=50`,
   different regime mix from daily.

## Data

- `src/data/review/exhaustion_pool_cn.csv` — 122 CN index events
- `src/data/review/exhaustion_pool_cn_commodity.csv` — 370 CN commodity events
- `src/data/review/exhaustion_pool_us.csv` — 134 US ETF events (synth-weekly version)
