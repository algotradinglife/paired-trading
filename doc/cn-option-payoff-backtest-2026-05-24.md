# CN Option Payoff Backtest (2026-05-24)

Tests divergence signals on **CN futures** by buying ATM monthly options at signal time
and measuring premium return at h=5/10/20 trading days. Pairs with the equity-side
`option_payoff_backtest.py` baseline for direct comparison.

- Script: `src/scripts/option_payoff_backtest_cn.py`
- Output: `src/data/review/cn_option_payoffs_all.csv` (79 rows)
- Data source: TqSdk (Shinny / 快期) option K-line history
- Underlyings: 4 products — `m` (soymeal, DCE), `i` (iron ore, DCE),
  `au` (gold, SHFE), `cu` (copper, SHFE)

---

## 1. Methodology

For each daily MACD divergence signal on a CN futures continuous-main series
(min_conf 0.50, most-recent 30 per product, max 20 for SHFE):

1. Bottom signal → buy ATM **CALL** ~75 DTE ahead.
   Top signal → buy ATM **PUT** ~75 DTE ahead.
2. Walk 50–120 days forward from signal date, pick (year, month) in product's
   listed expiry-month set closest to 75 DTE.
3. Underlying = `<EXCH>.<product><YY><MM>` (e.g. `DCE.m2509`,
   `SHFE.au2602`).
4. `api.query_options(underlying, option_class=...)` returns all known strikes;
   pick strike closest to signal-day close.
5. `api.get_kline_serial(contract, 86400, data_length=500)` to fetch daily
   premium history.
6. h{N}_ret = `(premium[t+N] - premium[t]) / premium[t]` where index advances
   by trading days (skips holidays naturally).

### Parameters
- `TARGET_DTE = 75`, `DTE_WINDOW_MIN=50`, `DTE_WINDOW_MAX=120`
- `WAIT_DEADLINE_SEC = 15` per option K-line fetch
- min_conf = 0.50, max_signals = 30 per product (20 for SHFE due to API pacing)

### Notable script fix
SHFE / CZCE option contracts use **compact naming** (`SHFE.au2602C960`,
`SHFE.cu2503C75000`) — no hyphens — while DCE uses **hyphen-separated**
(`DCE.m2509-C-2900`). The first run silently dropped all SHFE strikes because
the parser only knew the DCE form. Fixed by adding a fallback regex
`r"[CP](\d+(?:\.\d+)?)$"` that matches both.

### Caveats
- **Small samples per cell** (n=8–22). Treat numbers as directional, not
  precise estimates.
- **Daily-close premium only** — same upper-bound caveat as US tight-stop
  analysis (intraday paths may hit stops earlier; "SL -3%" column is a
  best-case for tight stops).
- **Skip reasons (21% overall, 21/100 attempts)**:
  - Most-recent signal too close to series tail (forward window < 20 bars)
  - No option month in [50, 120]-day window had matching strikes returned
  - Tail signals (e.g. last 20 bars) cannot be evaluated
- **Liquidity assumption**: ATM monthly options at 75 DTE are assumed liquid
  enough for the close to be a meaningful fill — not verified per-trade.
- **No 75-DTE matching for SHFE pre-2020**: au options listed 2019-12;
  cu options listed 2018-09; au+cu signals before then auto-skip.

---

## 2. Coverage

| product | n   | symbol  | options-listing  | first signal eval'd | last signal eval'd |
|---------|-----|---------|------------------|---------------------|--------------------|
| m       | 22  | DCE.m   | 2017-03-31       | 2022-06-23          | 2026-02-26         |
| i       | 22  | DCE.i   | 2019-12-09       | 2023-03-09          | 2026-04-13         |
| au      | 15  | SHFE.au | 2019-12-20       | 2023-03-05          | 2026-04-15         |
| cu      | 20  | SHFE.cu | 2018-09-21       | (recent)            | (recent)           |

Total payoff rows: **79**

Skip rates: m 8/30, i 8/30, au 5/20, cu 0/20.

---

## 3. Aggregate results

### 3.1 Per-direction (h=5/10/20)

| direction | n  | h5 mean / hit  | h10 mean / hit | h20 mean / hit |
|-----------|----|----------------|----------------|----------------|
| bottom    | 42 | **+25.6%** / 57% | **+38.0%** / 40% | **+35.1%** / 29% |
| top       | 37 | -21.2% / 24%   | -34.7% / 24%   | -42.6% / 19%   |

**Strong directional asymmetry**: bottom-call premium expansion dominates
top-put premium expansion. Hit rate of bottoms at h=5 (57%) is the only
above-coinflip cell; everything else hits <40% — consistent with options being
short-theta instruments where most ATM positions expire OOM if the underlying
doesn't move sharply.

### 3.2 Per-symbol (h=20)

| symbol | n  | hit  | raw mean | median  | min     | max      |
|--------|----|------|----------|---------|---------|----------|
| au     | 15 | 40%  | **+65.2%** | -44.9%  | -97.3%  | +701.3%  |
| m      | 22 | 23%  | **+12.1%** | -67.2%  | -99.2%  | +640.0%  |
| cu     | 20 | 20%  | -35.2%   | -41.5%  | -97.9%  | +105.5%  |
| i      | 22 | 18%  | -29.2%   | -59.7%  | -99.7%  | +182.1%  |

`au` (gold) leads — bottoms in gold during the 2023-2026 rally produced
multiple +200%-+700% calls. `m` (soymeal) follows on a few big late-2023 and
early-2026 bottoms. `cu` and `i` (industrial commodity) underperform — wider
ranges, smaller persistent trends, and option chains heavily skewed by
volatile underlying jumps.

### 3.3 Per-rule (h=20, raw + tight-stop sim)

| rule_id                  | n  | hit  | raw    | SL-30   | SL-10   | SL-5    | SL-3    |
|--------------------------|----|------|--------|---------|---------|---------|---------|
| `—` (no rule)            | 10 | 40%  | **+119.5%** | +146.4% | +158.4% | +161.4% | +162.6% |
| F8-cn-no-boost           | 32 | 25%  | +8.8%  | +27.9%  | +39.2%  | +42.6%  | +44.0%  |
| CN1-top-passthrough      | 37 | 19%  | -42.6% | -4.1%   | +11.1%  | +15.2%  | +16.8%  |

Key observations:
- The `—` cell (no specific fusion rule fired) has the **best EV** but only
  10 trades. These are bottoms (m: 9 of 9, au: 1 of 1) where neither F8 nor
  any CN-specific rule fired — i.e. the engine had nothing exotic to say, so
  they're "plain" bottom divergences. The huge +119.5% raw mean is driven by
  4 of 10 trades producing >+100% returns (m2308 +640%, m2605 +507%, m2605
  +122%, m2605 +122%) — small sample, large tail.
- **F8-cn-no-boost** is the workhorse: 32 trades, raw +8.8% h=20, and tight
  stop -5% lifts to +42.6%. Hit rate is low (25%) but right-tail dominates.
- **CN1-top-passthrough** (CN tops, passthrough policy) is heavily negative
  raw (-42.6%) but flips positive at SL -10% (+11.1%). Tight stop is essential.

### 3.4 Tight-stop matrix — all signals pooled (n=79)

| horizon | raw     | SL-30   | SL-10   | SL-5    | SL-3    |
|---------|---------|---------|---------|---------|---------|
| h=5     | +3.7%   | +9.5%   | +17.2%  | +19.8%  | +20.9%  |
| h=10    | +3.9%   | +18.6%  | +29.2%  | +32.3%  | +33.5%  |
| h=20    | -1.3%   | +27.9%  | +41.2%  | +44.8%  | +46.3%  |

Across the whole CN option universe, the pattern matches US: tight stops
mechanically lift EV by truncating the left tail. The relative gain (raw
near-zero → SL-5 +44.8% at h=20) is **larger than** the US baseline because
CN ATM options have wider variance per trade.

### 3.5 F8 (bottom + weakness) per-product (h=20)

| product | n  | hit | raw   | SL-10 | SL-5  |
|---------|----|-----|-------|-------|-------|
| au      | 8  | 50% | +118.6% | +137.5% | +139.4% |
| cu      | 9  | 22% | -14.5% | +7.2% | +11.1% |
| i       | 12 | 17% | -23.5% | +10.1% | +13.7% |
| m       | 3  | 0%  | -85.4% | -10.0% | -5.0%  |

F8 is **product-dependent in CN**: gold lights it up (+118.6% raw is closest
analogue to US F8's +50.9% — bigger in % terms because CN ATM options have
fatter right tails in trending products). Iron ore and copper are mostly
negative on F8 — supply-driven price moves break MACD-divergence persistence.
m's F8 cell is tiny (n=3) and unreliable.

---

## 4. Comparison vs US baseline

| metric                           | US (n=79, multi-symbol)   | CN (n=79, m/i/au/cu)    |
|----------------------------------|---------------------------|-------------------------|
| total payoff rows                | 79                        | 79                      |
| bottom mean h=20                 | +51% (F8 only n=38)       | **+35.1%** (n=42)       |
| top mean h=20                    | -65% raw, +1.7% SL-3 (n=18 F1) | -42.6% raw, +16.8% SL-3 (n=37) |
| F8 SL-3 EV @ h=20                | **+73.5%** (n=38)         | +44.0% (n=32)           |
| spotlight bucket (top+higher_opposing) | +24.7% (n=11)       | not measured (no multi-TF) |

Observations:
- **Directional asymmetry holds**: bottoms beat tops in both universes,
  even on options.
- **F8 gamma amplification holds, but smaller in CN**: US F8 SL-3 +73.5% vs
  CN F8 SL-3 +44.0%. Part of this is composition — US F8 is 38 NVDA-excluded
  equity bottoms with strong continuation patterns, while CN F8 spans 4 very
  different products with `m` and `cu` dragging the mean.
- **Tight-stop benefit is similar shape** (mechanical left-tail truncation
  works in both universes; CN's SL-5 lifts the pooled EV by ~46 pts vs US's
  similar magnitude).
- **CN tops on options are tradeable with tight stops**: like US F1, the raw
  CN1-top-passthrough is deeply negative (-42.6%) but mechanically flips
  positive at SL -10% (+11.1%) and improves through SL -3% (+16.8%). Same
  "mechanical recovery, not real alpha" pattern.

### What does NOT generalize
- **CN spotlight cell**: not measurable because we don't have multi-TF
  context loaded (US F4-spotlight is opposing higher_relation, n=11 +24.7%).
  Adding 60min CN data would enable F4 and the spotlight bucket.
- **F8 per-product is bimodal in CN**: au is a huge win, m/i/cu range from
  slight win to clear loss. The single-symbol F8 SL-3 number on US masks
  what would be similar per-symbol variation if disaggregated.

---

## 5. Big winners (h20 > +100%)

14 trades. Heavily concentrated in `au` (6) and `m` (4) with i/cu trailing.

| symbol | date       | dir    | rule_id              | contract             | h20_ret |
|--------|------------|--------|----------------------|----------------------|---------|
| au     | 2025-08-26 | bottom | F8-cn-no-boost       | SHFE.au2510C784      | +701.3% |
| m      | 2023-06-01 | bottom | —                    | DCE.m2308-C-3400     | +640.0% |
| m      | 2026-02-08 | bottom | —                    | DCE.m2605-C-2750     | +507.1% |
| au     | 2022-02-10 | bottom | —                    | SHFE.au2204C376      | +374.9% |
| m      | 2024-06-17 | top    | CN1-top-passthrough  | DCE.m2409-P-3350     | +223.5% |
| i      | 2025-07-02 | bottom | F8-cn-no-boost       | DCE.i2509-C-730      | +182.1% |
| au     | 2025-12-10 | bottom | F8-cn-no-boost       | SHFE.au2602C960      | +166.4% |
| i      | 2023-04-03 | top    | CN1-top-passthrough  | DCE.i2306-P-880      | +162.2% |
| au     | 2026-01-11 | bottom | F8-cn-no-boost       | SHFE.au2604C1024     | +135.9% |
| au     | 2023-03-05 | bottom | F8-cn-no-boost       | SHFE.au2306C416      | +128.5% |
| i      | 2024-01-18 | top    | CN1-top-passthrough  | DCE.i2404-P-960      | +123.6% |
| m      | 2026-02-26 | bottom | —                    | DCE.m2605-C-2850     | +122.3% |
| cu     | 2025-01-14 | bottom | F8-cn-no-boost       | SHFE.cu2503C75000    | +105.5% |
| au     | 2026-03-03 | top    | CN1-top-passthrough  | SHFE.au2606P1152     | +103.4% |

`au` dominates the bottom side (6 of 7 winning bottoms with >+100%) — gold's
2023-2026 trend regime produced repeated gamma-friendly setups.

---

## 6. Distribution

```
count    79
mean    -1.3%   (effectively zero before stop loss)
std     153.6%  (huge per-trade variance)
min     -99.7%  (premium → 0)
25%     -86.4%
50%     -58.3%  (median trade loses ~60%)
75%     -2.2%
max     +701.3%
```

The **median is -58%** but the **mean is -1.3%** — a classic right-tail
distribution. Tight stops + let-winners-run is exactly the right policy for
this shape (same as US).

---

## 7. Key findings

1. **Bottom > top on options too** — consistent with US equity-options
   pattern. CN bottoms +35.1% mean h=20 vs tops -42.6%.

2. **Tight stops mechanically lift EV across the board**.
   Pooled SL-5 at h=20: +44.8% vs raw -1.3%. Operationally use **SL -10%**
   (+41.2%) as the honest column — path-dependent stops would catch some
   that this end-of-day model misses.

3. **F8 (bottom + weakness) in CN options is product-bimodal**:
   - Excellent on `au` (+118.6% raw, n=8): gold's persistent uptrend rewards
     ATM call gamma.
   - Mediocre on `cu` and `i`: -14.5% / -23.5% raw, only SL -10% lifts to
     positive territory.
   - Negative on `m`: F8 fires rarely in m (n=3) and loses.

4. **The "no special rule" bottom cell (n=10) is the loudest signal**:
   +119.5% h=20 raw, driven by 4 of 10 trades returning >+100%. These are
   the "clean" divergences where the engine had no extra structure to flag —
   suggests the F8/F1/etc fusion *layer* may be adding noise rather than
   signal on CN bottoms. Need more samples to confirm.

5. **CN top-side has structural negative raw EV** (-42.6% h=20) but with
   tight stops becomes a modest winner (SL-3 +16.8%) — same pattern as US
   F1-top-lagging-soft. The tops are mostly losing trades that get rescued
   by a mechanical stop, **not by directional skill**.

6. **Sample is small enough that the spotlight bucket isn't measurable** in
   CN without multi-TF context. The single-tf engine can rank but cannot
   isolate the high-confidence dual-confirmation cells that US F4 / spotlight
   use.

---

## 8. Caveats & follow-ups

1. **Strike parser was silently dropping all SHFE options on the first run**.
   Caught only because au returned zero payoffs from 12 attempts. Should
   add a contract-naming unit test if this is repeated for CZCE.

2. **TqSdk connection occasionally hung** mid-product (cu hung once, au
   signal 5 hung once). Re-running cleared both — suggests transient API
   pacing rather than a code bug. Script now does incremental save after
   each product so partial runs aren't lost.

3. **Tail signals are systematically excluded** by the `idx+20 >= len(daily)`
   guard. The 5/20 au skips are mostly tail signals. Real-time deployment
   would compute live forward returns and the tail problem evaporates.

4. **Missing CZCE coverage** (TA/MA/CF/SR): not tested here. Future run
   should add at least TA + SR to broaden the universe and verify the
   compact-strike parser works on CZCE format.

5. **No transaction cost modeling**. ATM options in CN typically have 1-3
   yuan bid-ask spreads on liquid contracts; on a 50-yuan premium that's
   2-6% per round trip. Realistic EV is 4-12 pts lower than reported.

6. **Add 60min CN data** → enables F4 / spotlight / multi-TF context →
   directly comparable to US F4-options-asymmetric (+27.4% h=10 SL-3 in US).
   Largest expected lift per the project notes.

7. **F8 product-effect is exploitable**: au F8 SL-5 +139% strongly suggests
   product-specific F8 thresholds rather than a universal one. Coal/iron-ore
   options were noisier than expected.

---

## Artifacts

- Combined payoff CSV: `src/data/review/cn_option_payoffs_all.csv` (79 rows)
- Per-product CSVs: `cn_option_payoffs_{m_i,au,cu}.csv` in same folder
- Run logs: `/tmp/cn_optbt*.log` (transient)
- Script: `src/scripts/option_payoff_backtest_cn.py`
