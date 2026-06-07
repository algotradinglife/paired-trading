# Results Review Packet — 2026-05-23

**Purpose**: external review of whether the backtest findings reflect real
predictive structure or methodology artifacts.

**Data**: `src/data/review/signals_2026-05-23.csv` — signal-level rows
(266 signals × 3 horizons = 798 rows). Columns:
  `symbol, date, direction, subtype, level, confidence, lower_side, lower_cycle,
   lower_relation, higher_side, higher_cycle, higher_relation, horizon, hit,
   signed_return`

`signed_return` is direction-aligned P&L (bottom signals: price-up = positive;
top signals: price-down = positive). `hit = signed_return > 0`.

**Universe**: 10 ETFs/stocks — SPY, QQQ, NVDA, GLD, DIA, IWM, TLT, XLK, XLF, GDX.
Period: 2021-05-24 → 2026-05-22 (5y).

**Three timeframes**: weekly (W), daily (D), 60min (1h).
Signals are detected on daily; weekly + 60min state at signal time is attached
as `multi_tf_context` annotation. Confidence is NOT modified by multi-TF context.

---

## Headline Findings to Verify

### Finding 1 — `top + lower_relation == lagging` is a stable red zone

```
top + lagging       n=44   45.5% hit  -0.93% avg / h=20
top + lagging × opposing(weekly down)   n=36   41.7%  -1.47%
```

**Claim**: top divergences where 60min has already turned bearish are unreliable.
The down move already executed; the daily call is descriptive, not predictive.

**Why this might be true**: causal — lower TF (1h) is a leading indicator of
intermediate-term momentum. A daily top after 1h has already turned is "the
last bar". Predicts continuation, but the candidate is the late one.

**Why this might be an artifact**:
- Lookahead in `lower_relation` computation? Verify `enrich_with_lower_tf` in
  `src/engine/divergence/multi_tf_context.py:140-170` only slices
  `lower_tf_bars[timestamp <= signal_t + 30min]`.
- Symbol/period concentration? The 36-signal bucket — is it dominated by SPY
  2022 selloff?

**Verification checklist** (slice the CSV):
- [ ] `df[(direction=='top') & (lower_relation=='lagging')]` per-symbol count
- [ ] Per-quarter distribution of these 36 signals — are they clustered?
- [ ] What's the empirical bootstrap 95% CI on the -1.47% mean (with n=36)?

---

### Finding 2 — `bottom + leading + opposing` is a sweet spot

```
bottom + leading + opposing   n=15   93.3% hit  +8.52% avg / h=20
                                    100.0% hit  +6.98% avg / h=10
```

**Claim**: when 60min still bearish + weekly still bearish + daily bottom
divergence → it's a "trend exhaustion" reversal call with very high success.

**Why this might be true**: aligns with classic Wyckoff "spring" / Song Jianyi's
multi-TF reversal pattern — extreme negativity at daily aligned with cross-TF
oversold gives the cleanest mean-reversion setup.

**Why this might be an artifact**:
- **n=15 is small**. Outlier sensitivity: if we drop the top 2 winners,
  does the avg return collapse?
- **Period bias**: 2022 bear market accounts for half of 5y. Most "weekly
  opposing" signals are in 2022. Bull-market base rate of this bucket is
  unknown.
- **Survivorship in symbol selection**: I picked liquid US equity ETFs +
  NVDA. Did I implicitly select for "things that recovered from bear
  markets"?

**Verification checklist**:
- [ ] CSV: `df[(direction=='bottom') & (lower_relation=='leading') &
        (higher_relation=='opposing'))]` — what's the symbol breakdown?
- [ ] Year breakdown: how many of these 15 are in 2022 vs other years?
- [ ] Drop top-2 winners: does +8.52% become +4% or lower?
- [ ] Compare median (+7.22%) vs mean (+8.52%) — modest skew, but verify
      no extreme outlier driving the mean.

---

### Finding 3 — `candidate × higher_relation==opposing` is 100% hit

```
candidate (conf 0.65-0.80) × opposing weekly trend   n=14  100% hit  +6.13%
```

**Claim**: confidence band 0.65-0.80 (post-direction_gate) when weekly is in
counter-trend → 14/14 wins.

**Concern flags**:
- 14/14 = 100% on n=14 is **suspiciously perfect**. Probability under random
  50% is 1/16384.
- Is this n=14 truly independent, or are several signals on the same
  symbol within a short window correlated?

**Verification checklist**:
- [ ] CSV: `df[(conf_band=='candidate') & (higher_relation=='opposing'))]`
- [ ] How many unique (symbol, week-of-year) pairs? — adjacency suggests
      auto-correlation.
- [ ] If we de-dupe to one signal per symbol per month, does the 100%
      survive?

---

### Finding 4 — `top + leading + opposing` is unexpectedly OK

```
top + leading + opposing  n=25  72% hit  +0.91% avg / h=20
                                72% hit  +0.65% avg / h=10
```

**Claim**: in strong bullish regimes (60m up + W up), daily top divergence is
an early warning — 25 signals 72% hit.

**Concern**: contradicts the simple "fight the trend = lose" intuition. Could
be an artifact of:
- Direction_gate already filtering out the worst tops, leaving only the
  strongest signals in this bucket.
- Top divergence in strong trends often resolves with consolidation rather
  than full reversal — h=20 hit-rate sensitive to small price moves.

**Verification checklist**:
- [ ] Among these 25, what's the breakdown by subtype (standard / weakness /
      hidden)? `direction_gate` drops `top + hidden` entirely.
- [ ] What's the distribution of `signed_return` magnitude? Many small wins
      (+0.5-2%) vs few big wins?

---

## Methodology Cross-References (for code-level audit)

### Signal generation
- `src/engine/features/macd.py` — MACD computation (`hist_scale=1.0`, matches
  TradingView)
- `src/engine/units/{heaps,cycles,segments}.py` — three vector units
- `src/engine/divergence/comparator.py` — unified reference-vs-candidate
  compare function (same code for all 3 levels)
- `src/engine/divergence/detector.py` — per-level orchestrators

### Confidence calibration
- `src/engine/divergence/direction_gate.py` — top-signal asymmetric
  multipliers (validated on 5y previously). **Note**: this multiplier table
  was fit on a 5y FMP+yfinance mixed dataset; current run is on unified
  Polygon. Could be slightly miscalibrated.

### Multi-TF context attachment
- `src/engine/divergence/multi_tf_context.py`
  - `enrich_with_lower_tf` lines ~140-170
  - `enrich_with_higher_tf` lines ~175-200
  - **Critical**: both slice `bars[timestamp <= signal_t + grace]`. Verify
    no future leakage. Specifically for `higher_tf` (weekly), the signal
    falls inside an in-progress weekly bar. The slice cutoff
    `signal_t + 0 minutes grace` (default) means the latest weekly bar may
    or may not be included depending on alignment. Check semantics.

### Forward returns
- `src/scripts/backtest_fusion.py` `evaluate_forward` (lines ~62-78). Computes
  forward return at h bars after signal. **Uses `bars.iloc[idx + h]['close']`
  — pure positional, no lookahead beyond the explicit horizon.**

---

## Specific Questions for Codex

1. **Lookahead in higher_tf context**: when a daily signal fires on, say,
   Wednesday, the current weekly bar (Mon-Fri) is not yet closed. Does our
   `enrich_with_higher_tf` slice include the still-open weekly bar
   (potentially containing Friday's data)? Inspect `_state_at_signal` in
   `multi_tf_context.py`. If yes, the `higher_relation` tag is computed
   from a partial weekly bar — minor leak but worth flagging.

2. **Outlier dependence**: for the strong claims (#2, #3), recompute
   hit-rate and avg_return after winsorizing top/bottom 5% of returns.
   Are the buckets still strong?

3. **Symbol concentration**: for each "interesting" bucket, what's the
   Herfindahl index of symbol weights? Buckets dominated by 1-2 symbols
   are not generalizable.

4. **Multiple testing**: we drilled into roughly 25-30 buckets across
   1-, 2-, 3-way crosses. With α=0.05 per bucket, expected false discoveries
   = 1-2. Identify which findings would survive Bonferroni correction
   (α=0.05 / 30 ≈ 0.0017).

5. **Direction_gate calibration cross-check**: the gate was fit on a
   different (mixed) dataset. On current unified-Polygon data, recompute
   the gate's input feature distribution — has it shifted enough to require
   refit?

---

## How to Use This Packet

1. Read findings + verification checklists above.
2. Load `src/data/review/signals_2026-05-23.csv` (798 rows).
3. Run the suggested slices; report which findings hold, which collapse.
4. Cross-check code paths at the file:line references for methodology bugs.
5. Output: a list of findings with **survives / collapses / inconclusive**
   verdicts, plus any new bugs found in the code.
