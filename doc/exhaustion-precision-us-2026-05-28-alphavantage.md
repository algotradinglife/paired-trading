# Exhaustion detector — forward-return precision (US daily, 2026-05-28, alphavantage)

**Status**: in-sample, single-pool, look-ahead corrected.
**Vendor**: alphavantage (via qveris) — replaces polygon as primary source.
**Data**: Stage D backfill — 10 US ETFs × 3 TFs, daily 2006-2026, intraday 2021-2026.

> **Pre-vendor-switch baseline** (polygon, 2026-05-27): see
> `doc/exhaustion-precision-us-2026-05-27.md` — all numbers there are
> tagged "pre-vendor-switch" and superseded by this document.

---

## Setup

Pool: SPY, QQQ, IWM, DIA, GLD, GDX, XLF, XLK, TLT, NVDA
- Topology A (D + 1h + W), strict 3-TF alignment
- `min_bars_in_segment=20`, `min_wick_ratio=0.4`
- Weekly bars synthesized from daily via `pd.resample('W-FRI')` (no-leak)
- Forward returns: signed by predicted reversal direction (positive = correct)

---

## Headline result (h=20)

| Direction | n | Hit % | Mean % | CI95 |
|---:|---:|---:|---:|---:|
| top | 146 | 36.3 | **-1.95** | **[-3.31, -0.64]** ✅ CI clears 0 |
| bottom | 40 | 50.0 | +1.13 | [-0.96, +3.51] ❌ CI crosses 0 |
| all | 186 | 39.2 | -1.29 | [-2.46, -0.14] |

**Top CI clears zero negative at every horizon ≥ 10.**
**Bottoms remain inconclusive** at the headline level despite 3× more events.

---

## Horizon scan

| Horizon | Direction | n | Hit % | Mean % | CI95 |
|---:|---:|---:|---:|---:|---:|
| 5 | top | 146 | 45.9 | -0.15 | [-0.58, +0.27] |
| 5 | bottom | 41 | 65.9 | +1.78 | [+0.70, +2.89] ✅ |
| 10 | top | 146 | 37.0 | -1.22 | [-2.06, -0.40] ✅ |
| 10 | bottom | 40 | 62.5 | +1.61 | [+0.23, +3.11] ✅ |
| 20 | top | 146 | 36.3 | -1.95 | [-3.31, -0.64] ✅ |
| 20 | bottom | 40 | 50.0 | +1.13 | [-0.96, +3.51] |

Note: h=5 bottoms CI also clears zero (+0.70 to +2.89), as does h=10 bottoms.
Only h=20 bottoms is inconclusive.

---

## Stratification (h=20)

### Confidence tercile

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top conf=low | 45 | 42.2 | -0.48 | [-2.99, +1.96] |
| top conf=mid | 48 | 20.8 | **-3.58** | **[-5.52, -1.80]** ✅ strongest top cell |
| top conf=high | 53 | 45.3 | -1.73 | [-4.34, +0.45] |
| bottom conf=low | 17 | 35.3 | +0.20 | [-3.41, +4.37] |
| bottom conf=mid | 14 | 57.1 | +0.78 | [-2.61, +4.10] |
| bottom conf=high | 9 | 66.7 | **+3.43** | **[+0.34, +6.93]** ✅ n=9, fragile |

### Wick-ratio tercile

| Cell | n | Hit % | Mean % | CI95 |
|---|---:|---:|---:|---:|
| top wick=low | 47 | 38.3 | -0.87 | [-3.44, +1.65] |
| top wick=mid | 47 | 36.2 | -2.11 | [-4.15, -0.18] ✅ |
| top wick=high | 52 | 34.6 | **-2.79** | **[-5.28, -0.80]** ✅ |
| bottom wick=low | 15 | 60.0 | +3.31 | [-0.96, +7.93] |
| bottom wick=mid | 15 | 53.3 | -0.46 | [-3.49, +2.53] |
| bottom wick=high | 10 | 30.0 | +0.24 | [-2.30, +3.78] |

---

## Per-symbol event counts

| Symbol | Events |
|---|---:|
| NVDA | 28 |
| SPY | 28 |
| XLF | 21 |
| GDX | 20 |
| TLT | 20 |
| XLK | 20 |
| DIA | 18 |
| QQQ | 13 |
| IWM | 12 |
| GLD | 10 |
| **Total** | **190** |

---

## Comparison vs polygon pre-switch baseline (h=20)

| Metric | Polygon (2026-05-27) | Alphavantage (2026-05-28) | Delta |
|---|---:|---:|---:|
| total events | 133 | 190 | +43% |
| top n | 120 | 146 | +22% |
| top mean % | -2.93 | -1.95 | +0.98pp (weaker) |
| top CI low | -4.48 | -3.31 | shifted right |
| top CI high | -1.46 | -0.64 | shifted right |
| top CI clears 0 | ✅ | ✅ | preserved |
| bottom n | 12 | 40 | +233% |
| bottom mean % | +3.90 | +1.13 | -2.77pp (weaker) |
| bottom CI clears 0 | ❌ | ❌ | unchanged |

**Why the +43% event delta**: MACD warmup divergence from 20y vs 5y daily history
(same cause as the +47% on SPY-alone in Stage C). Longer warmup reaches 2021-05
start with different segment state → different exhaustion candidate boundaries.

**Why top signal weakened but held**: +22% more top events dilute the mean.
The directional finding (continuation, not reversal) is unchanged.

**Why bottom signal weakened despite 3× more events**: The original polygon
n=12 was an upward-biased small-sample artifact. 40 events with a CI that
crosses 0 is the more accurate picture. The h=5/h=10 bottom CIs *do* clear
zero, suggesting short-horizon bottom setups may have mild predictive value.

---

## Sweet cells (CI clears 0, actionable)

| Cell | n | Mean % | CI95 | Confidence |
|---|---:|---:|---:|---|
| h=20 top conf=mid | 48 | -3.58 | [-5.52, -1.80] | high (n=48, CI tight) |
| h=20 top wick=high | 52 | -2.79 | [-5.28, -0.80] | medium |
| h=20 top wick=mid | 47 | -2.11 | [-4.15, -0.18] | medium |
| h=20 top headline | 146 | -1.95 | [-3.31, -0.64] | high (n=146) |
| h=20 bottom conf=high | 9 | +3.43 | [+0.34, +6.93] | low (n=9, fragile) |
| h=5 bottom | 41 | +1.78 | [+0.70, +2.89] | medium |
| h=10 bottom | 40 | +1.61 | [+0.23, +3.11] | medium |

---

## Output

Per-event CSV: `data/review/exhaustion_pool_us_alphavantage.csv`

---

## Walk-forward OOS (K=3, h=20, 2026-05-28)

All tested cells fail the R5 graduation criterion. Consistent with CN results.

| Cell | fold1 result | fold2 result | Verdict |
|---|---|---|---|
| top conf=mid | CI [-6.31, +0.54] crosses 0 | CI [-4.96, -0.01] near-pass | FAIL |
| top wick=high | CI [-3.97, -0.15] crosses 0 | CI [-4.53, +0.42] crosses 0 | FAIL |
| top wick=mid | CI [-7.09, +2.11] crosses 0 | CI [-3.43, +1.30] crosses 0 | FAIL |
| bottom conf=high | n=4 < 15 | n=1 < 15 | FAIL (too sparse per fold) |

**Note on top-direction criterion**: `walk_forward_exhaustion.py` tests
`CI_lo > 0` (designed for bottom/positive-return cells). The correct check
for top direction is `CI_hi < 0`. Under that criterion, top conf=mid fold2
CI [-4.96, -0.01] would pass, but fold1 [-6.31, +0.54] still fails.
Even with the corrected criterion, 0/4 cells achieve 2/2 folds.

**Conclusion**: no new cells graduate to policy rules. Existing policy
rules are unchanged. alphavantage baseline fully established.
