# Missed-swing diagnostic — US pool (2026-05-29)

**Script**: `scripts/missed_swing_state.py --pool US --threshold 5`
**Data**: alphavantage Stage D backfill, 10 ETFs × 5y daily
  (NVDA included; pre-2024-06 split discontinuity only affects intraday;
  daily data is continuous so NVDA contributes to this daily-level analysis)
**Log**: `data/review/missed_swing_us_log.txt`
**CSV**: `data/review/missed_swing_us.csv` (per-swing rows)
**Exhaustion detector recall baseline**: ~5–11% of labeled swings
  (from `doc/exhaustion-recall-lift-2026-05-27.md`)

---

## Pool summary

| Metric | Value |
|---|---:|
| Symbols | 10 (SPY QQQ IWM DIA GLD GDX XLF XLK TLT NVDA) |
| Swing threshold | 5% |
| Total missed swings | 3700 |
| Missed UP swings | 1825 |
| Missed DOWN swings | 1875 |

These are swings labeled by `swing_labeler` with magnitude ≥ 5% that had
**no matching divergence detector event within 10 bars before the head**.

---

## Dominant pattern: counter-trend mid-cycle swings

### Missed UP swings (price bounces ≥5% while MACD is bearish)

| Feature | Value |
|---|---:|
| d_trend_side = bearish | **57%** |
| d_cycle_state = in_cycle | **73%** |
| d_dif_sign = neg | **67%** |
| 3-TF all bearish (bearish/bearish/bearish) | 191 events = **10%** |

### Missed DOWN swings (price drops ≥5% while MACD is bullish)

| Feature | Value |
|---|---:|
| d_trend_side = bullish | **56%** |
| d_cycle_state = in_cycle | **75%** |
| d_dif_sign = pos | **62%** |
| 3-TF all bullish (bullish/bullish/bullish) | 202 events = **11%** |

### Higher/lower TF state: ~75–76% NaN

The 1h and W TF state is unavailable for most missed swings. Only the
daily TF contributes reliably. This limits 3-TF config filtering.

---

## Why the exhaustion detector misses these

The exhaustion detector requires:
1. At least one **completed** MACD heap cycle
2. **Divergence** between price extreme and MACD extreme
3. Strict 3-TF alignment on the SAME direction

Counter-trend swings mid-cycle (in_cycle=73-75%) don't produce
divergence patterns — they ARE part of the active cycle, not the
termination of it. The detector literally cannot fire at these points.

---

## Candidate new detector: Mid-Cycle Counter-trend (MCT)

Fires when a significant price swing occurs AGAINST the current daily
MACD trend while MACD is in an active cycle.

**Minimum conditions (daily-only):**
- `d_cycle_state = in_cycle`
- UP swing: `d_dif_sign = neg` (MACD bearish, price bounces up)
- DOWN swing: `d_dif_sign = pos` (MACD bullish, price drops)

**Higher-confidence variant (3-TF filter):**
- bearish/bearish/bearish → UP swing (n=191, 5y, 10 ETF)
- bullish/bullish/bullish → DOWN swing (n=202, 5y, 10 ETF)

### Event density comparison

| Detector | Events (5y, 10 ETF) | Events/sym/yr |
|---|---:|---:|
| Exhaustion (current) | 190 | ~4.2 |
| MCT 3-TF aligned | 393 | ~7.9 |
| MCT daily-only | ~2200+ | ~44 |

The 3-TF variant has comparable density to exhaustion and is the
cleaner starting point for precision validation.

---

## Key open question before building MCT

**Are these counter-trend swings tradeable reversals or just noise?**

A counter-trend bounce in a bearish MACD could be:
(a) A genuine trend change (MACD about to reverse) → tradeable long
(b) A temporary correction within a larger downtrend → fades back

The exhaustion detector was designed for (a) with a divergence signal.
MCT fires without divergence — it needs precision analysis to determine
whether the 3-TF aligned variant predicts actual trend change vs noise.

**Next step: run precision analysis on MCT events** (same methodology
as `analyze_exhaustion_pool.py`) before investing in full detector code.

---

## Recommended next action

1. Write `detect_mct_events()` — a lightweight event extractor that
   applies the daily-only MCT conditions to the existing pool data,
   producing a CSV in the same format as `exhaustion_pool_us.csv`.
2. Run `analyze_exhaustion_pool`-style precision on the MCT CSV at
   h=5/10/20.
3. If CI clears zero: proceed to full detector + walk-forward.
   If not: the MCT signal is noise — look at other detector types.
