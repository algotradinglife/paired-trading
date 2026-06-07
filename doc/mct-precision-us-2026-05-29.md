# MCT 3-TF Precision Study — US pool (2026-05-29)

**Script**: `scripts/detect_mct_events.py --pool US`
**Data**: alphavantage Stage D backfill, 10 ETFs × 5y daily
**CSV**: `data/review/mct_pool_us.csv` (967 events)
**Method**: causal bar-scan — conditions checked at each daily bar, no swing look-ahead

---

## Definition

**MCT UP bar**: at daily bar `t`, ALL of:
- `d_cycle_state = in_cycle`
- `d_trend_side = bearish` (DIF < 0 AND DEA < 0)
- `d_dif_sign = neg`
- weekly trend_side = bearish (no-leak weekly synthesized from daily)
- 60min trend_side = bearish (same-session cutoff: daily_ts + 17h)

**MCT DOWN bar**: symmetric with `bullish / pos`.

MIN_GAP=5 bars between same-direction events to suppress clustering.

---

## Event counts

| Pool | UP events | DOWN events | Total |
|---|---:|---:|---:|
| US (10 ETF, 5y) | 216 | 751 | 967 |

DOWN events are 3.5× more frequent than UP events — US equities are mostly
in bullish MACD states over the 5-year window.

---

## Precision results

Signed forward return: UP→raw, DOWN→-raw (positive = continuation win)

### UP MCT — all 3 horizons PASS ✓

| Horizon | n | hit% | mean% | CI95 |
|---|---:|---:|---:|---|
| h=5 | 216 | 55.1% | +0.79% | [+0.27, +1.31] ✓ |
| h=10 | 215 | 57.7% | +1.14% | [+0.48, +1.79] ✓ |
| h=20 | 213 | 55.9% | +2.08% | [+1.06, +3.16] ✓ |

At h=20: price is on average +2.08% higher than at the signal bar.
CI_lo > 0 at all horizons → passes the precision criterion.

### DOWN MCT — all 3 horizons FAIL ✗

| Horizon | n | hit% | mean% | CI95 |
|---|---:|---:|---:|---|
| h=5 | 746 | 43.0% | −0.44% | [−0.67, −0.20] |
| h=10 | 742 | 40.7% | −0.86% | [−1.19, −0.52] |
| h=20 | 730 | 35.6% | −1.65% | [−2.17, −1.13] |

Negative signed returns = price goes UP, not DOWN after DOWN MCT bars.
The bullish underlying trend dominates; down-bars in bullish MACD environments
are corrective, not continuation signals.

---

## Interpretation

**UP MCT works, DOWN MCT does not.**

When all three TFs are bearish and MACD is mid-cycle (not yet completed), bars
where the MACD conditions are maximally bearish predict UPWARD price continuation.
This is consistent with bearish-sentiment exhaustion: maximum bearish alignment
often precedes recovery, even before MACD divergence forms.

DOWN MCT fails because the US equity pool is predominantly bullish over the
5-year window. Down-bars in bullish MACD represent normal corrections, not trend
reversals. A separate analysis on CN futures (typically more balanced up/down
cycles) may yield different results for DOWN MCT.

---

## Next steps

The UP MCT signal passes. Before building a full production detector:

1. **Walk-forward validation**: split the 5y window K=3 out-of-sample
   (same methodology as `walk_forward_exhaustion.py`) to check OOS stability.
2. **CN futures**: run MCT study on CN pool — DOWN MCT may work in futures markets.
3. **Detector integration**: if walk-forward passes, add MCT UP as a new detector
   type alongside the exhaustion detector with its own `instrument_class`-aware
   policy.
