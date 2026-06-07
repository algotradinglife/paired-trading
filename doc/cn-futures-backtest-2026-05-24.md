# CN Futures Single-TF Divergence Backtest (2026-05-24)

Backtests the existing divergence detection + direction-gate + F8 fusion engine on **19 Chinese futures 主力连续合约 (continuous main contract)** daily snapshots fetched via AKShare on 2026-05-23/24.

- Script: `src/scripts/backtest_cn_futures.py`
- Long-format CSV: `src/data/review/cn_futures_signals_aggregate.csv`
- min_conf: **0.30** (watching band and above)
- Horizons: **5 / 10 / 20** trading days
- Total evaluable signals: **1,372** (after the 20-bar forward-window cutoff at each series tail)

---

## 1. Methodology

Pipeline per symbol (identical to `scripts/backtest_signals.py`, single-TF only):

1. Load daily bars from `data/raw/<symbol>_daily.json`.
2. Compute MACD (12, 26, 9, `hist_scale=1.0`).
3. Compute feature streams → unit metadata.
4. Run `detect_all_divergences(...)` (includes direction-gate; F1–F4 multi-TF rules cannot fire because no 60min/weekly data is loaded; F8 bottom+weakness rule fires when applicable).
5. Filter `confidence >= 0.30`.
6. For each signal with `candidate_bar_idx + 20 < len(bars)`:
   - `forward_return = (close[t+h] - close[t]) / close[t]` for h ∈ {5, 10, 20}
   - `signed_return = forward_return` for `bottom` signals; `-forward_return` for `top` signals
   - `hit = signed_return > 0`
   - MFE/MAE measured over the high/low envelope inside the forward window
7. Aggregate by symbol, direction, subtype, conf_band.

### Caveats

- **Rollover artifact**: 主力连续 splices the most-active contract; mechanical price jumps at rollover are treated by the engine as ordinary bars. We flag (but do **not** filter) the worst 15 `|signed_return| > 25%` outliers in §6. Their effect on pooled means is small (≈0.05% on a 972-bottom-sample mean).
- **No multi-TF context**: We have only daily data for these symbols. Fusion rules F1/F2/F3/F4 require multi_tf_context and so cannot fire — these results are the pure single-TF baseline with the direction-gate.
- **Sample length is heterogeneous**: `im0` (2022→present, 927 bars) and `sc0` (2018→present, 1,977 bars) have far less history than the 21-year `cu0`/`m0`/`cf0` samples.
- **Asia trading hours / overnight gaps** are not equity-comparable; results below should be read as relative comparison within the CN universe, not directly equity-equivalent.

---

## 2. Per-symbol summary (h=20)

Sorted by EV (average signed return).

| symbol | n   | hit_rate | avg_signed_ret | median | avg_mfe | avg_mae | mfe/mae |
|--------|-----|----------|----------------|--------|---------|---------|---------|
| im0    | 11  | 72.7%    | +6.92%         | +5.24% | 11.16%  | 2.53%   | 4.41    |
| sc0    | 31  | 61.3%    | +3.20%         | +4.70% | 11.31%  | 5.92%   | 1.91    |
| i0     | 59  | 54.2%    | +2.81%         | +0.51% | 10.92%  | 6.33%   | 1.72    |
| ta0    | 84  | 61.9%    | +2.53%         | +1.18% | 6.71%   | 2.77%   | 2.43    |
| ma0    | 45  | 60.0%    | +1.64%         | +1.54% | 7.23%   | 4.33%   | 1.67    |
| if0    | 48  | 70.8%    | +1.50%         | +1.73% | 5.06%   | 2.39%   | 2.12    |
| cu0    | 103 | 60.2%    | +1.35%         | +1.05% | 4.97%   | 3.00%   | 1.66    |
| ih0    | 39  | 66.7%    | +1.33%         | +0.74% | 4.86%   | 2.40%   | 2.03    |
| cf0    | 103 | 58.3%    | +1.33%         | +1.17% | 4.62%   | 2.70%   | 1.71    |
| rb0    | 79  | 55.7%    | +1.26%         | +1.10% | 6.04%   | 3.65%   | 1.65    |
| ag0    | 71  | 50.7%    | +1.26%         | +0.11% | 5.48%   | 3.53%   | 1.55    |
| ic0    | 49  | 55.1%    | +1.23%         | +1.14% | 5.12%   | 2.97%   | 1.73    |
| y0     | 108 | 54.6%    | +0.98%         | +0.39% | 5.25%   | 3.18%   | 1.65    |
| au0    | 87  | 55.2%    | +0.68%         | +0.82% | 3.89%   | 2.46%   | 1.58    |
| sr0    | 101 | 58.4%    | +0.68%         | +0.81% | 3.99%   | 2.87%   | 1.39    |
| p0     | 106 | 49.1%    | +0.46%         | -0.04% | 5.45%   | 4.03%   | 1.35    |
| m0     | 102 | 46.1%    | +0.20%         | -0.58% | 5.14%   | 3.91%   | 1.31    |
| j0     | 78  | 47.4%    | +0.00%         | -0.42% | 7.16%   | 6.32%   | 1.13    |
| jm0    | 68  | 47.1%    | **-0.67%**     | -0.37% | 7.98%   | 7.14%   | 1.12    |

- **Highest signal count**: `y0` (108), `p0` (106), `cu0` / `cf0` (103) — all 15+ years of history.
- **Lowest signal count**: `im0` (11 — only 3.7 years), `sc0` (31), `ih0` (39).
- **Best EV (n≥10)**: `im0`, `sc0`, `i0` — high-volatility black + crude + small-cap-index futures.
- **Worst EV (n≥10)**: `jm0`, `j0`, `m0` — coking coal / coke / soybean meal; the coal complex shows the weakest divergence-following behaviour, possibly due to policy-driven gap moves.

### 2a. Per-symbol per-direction (h=20)

The full per-symbol × direction table is in `cn_futures_signals_aggregate.csv`. Highlights:

| symbol | dir    | n  | hit  | avg_ret |
|--------|--------|----|------|---------|
| im0    | bottom | 11 | 72.7%| +6.92%  |
| ih0    | bottom | 31 | 71.0%| +1.34%  |
| sc0    | top    | 7  | 71.4%| +0.77%  |
| rb0    | top    | 20 | 70.0%| +1.72%  |
| if0    | top    | 18 | 77.8%| +1.48%  |
| cf0    | top    | 30 | 66.7%| +3.04%  |
| ag0    | top    | 22 | 27.3%| **-2.12%** |
| ma0    | top    | 13 | 53.8%| **-2.06%** |

- Index-future tops (`if0`/`ic0`/`ih0`) all hit 63–78% — best behaved.
- `ag0` top is the worst single-cell: silver tops fail systematically (likely related to chronic bid bias from PBoC easing periods).

---

## 3. Pooled aggregates

### 3.1 Direction baseline (h=20, n=1,372)

| direction | n   | hit  | avg_ret | mfe/mae |
|-----------|-----|------|---------|---------|
| bottom    | 972 | 55.3%| +1.31%  | 1.67    |
| top       | 400 | 55.8%| +0.65%  | 1.33    |

### 3.2 Subtype pooled (h=20)

| subtype   | n   | hit  | avg_ret | mfe/mae |
|-----------|-----|------|---------|---------|
| standard  | 442 | 58.4%| +1.77%  | 1.67    |
| weakness  | 868 | 54.4%| +0.85%  | 1.53    |
| hidden    | 62  | 50.0%| +0.14%  | 1.36    |

### 3.3 Confidence band pooled (h=20)

| band       | n   | hit  | avg_ret |
|------------|-----|------|---------|
| watching   | 484 | 54.8%| +0.58%  |
| forming    | 211 | 59.2%| +1.64%  |
| candidate  | 268 | 55.2%| +1.33%  |
| confirmed  | 409 | 54.5%| +1.34%  |

Confidence ordering is **non-monotonic**: `forming` (0.50–0.65) produces the best EV. `confirmed` (≥0.80) doesn't outperform `candidate`. This mirrors the round-3 finding on US equities that conf_band alone is not a return monotone — its main use is for ranking / filtering not for sizing.

### 3.4 Direction × subtype (h=20)

| direction | subtype  | n   | hit  | avg_ret |
|-----------|----------|-----|------|---------|
| bottom    | standard | 300 | 58.0%| +2.17%  |
| bottom    | weakness | 610 | 54.6%| +1.01%  |
| bottom    | hidden   | 62  | 50.0%| +0.14%  |
| top       | standard | 142 | 59.2%| +0.93%  |
| top       | weakness | 258 | 53.9%| +0.49%  |

Bottom × standard is the most productive cell (+2.17%, n=300). The "hidden" class is rare and weak — likely needs continuation-context to fire usefully.

### 3.5 F8 isolation — bottom × weakness (h=20)

| conf_band | n   | hit  | avg_ret |
|-----------|-----|------|---------|
| watching  | 64  | 62.5%| +1.97%  |
| forming   | 104 | 57.7%| +1.06%  |
| candidate | 167 | 52.7%| +1.00%  |
| confirmed | 275 | 52.7%| +0.77%  |

**F8 in CN is anti-monotone in confidence**: lower bands beat higher bands. This is the opposite of the US-equity F8 finding from round-3. Hypothesis: when the F8 fusion lifts bottom+weakness to "confirmed" without a confirming higher-TF context (which is absent here), it's catching downtrend continuations — exactly the multi-TF context failure mode anticipated in the project notes.

---

## 4. Comparison vs US-equity baseline (B-topology, 10 symbols × 5y, n=266)

| metric              | US bottom (n=179) | CN bottom (n=972) | US top (n=87) | CN top (n=400) |
|---------------------|-------------------|-------------------|---------------|----------------|
| hit_rate            | 69.3%             | 55.3%             | 52.9%         | 55.8%          |
| avg_ret_pct (h=20)  | +3.17%            | +1.31%            | -0.27%        | +0.65%         |

### Observations

- **Direction asymmetry in CN is weaker and inverted**: US showed bottoms (+3.17%) >> tops (-0.27%). CN shows bottoms (+1.31%) only mildly above tops (+0.65%) — tops are actually *positive* in CN, suggesting either (a) less persistent uptrends in CN futures so mean-reversion at tops works modestly, or (b) the absence of multi-TF context lets tops in choppy markets through that the US version would have rejected via F2/F4.
- **Bottom EV is ~40% of US baseline** — likely a mix of: (i) absence of multi-TF context boost, (ii) the included sample contains coking coal / soybean meal which drag mean down, (iii) rollover gap noise.
- **Hit rate gap narrows for tops**: CN top hit (55.8%) actually *beats* US top hit (52.9%), but the magnitude of US's average is dragged negative by a few large continuation moves — a signature that US trends harder in the up direction.
- **F8 boost did not generalize**: where US F8 (bottom+weakness `confirmed`) was the workhorse, in CN it's the worst band of that cell. The `watching` and `forming` bands of bottom+weakness are CN's best-performing F8 sub-cells. → **F8 confidence-bump policy should be re-examined when generalizing beyond US equities**.

### What holds

- Standard outperforms weakness outperforms hidden (same ranking in both universes).
- Bottoms still mildly outperform tops on EV (1.31% vs 0.65%).
- MFE/MAE ratio > 1 across all major cells (1.33–1.67) — divergence direction does carry information.

---

## 5. Index futures vs commodity futures (h=20)

| group     | dir    | n   | hit  | avg_ret | mfe/mae |
|-----------|--------|-----|------|---------|---------|
| index     | bottom | 102 | 63.7%| +1.95%  | 2.02    |
| index     | top    | 45  | 66.7%| +1.36%  | 2.43    |
| commodity | bottom | 870 | 54.4%| +1.24%  | 1.63    |
| commodity | top    | 355 | 54.4%| +0.56%  | 1.27    |

**Index futures (IF/IH/IC/IM) significantly outperform commodity futures** on both directions, hit rate, and MFE/MAE. Index futures are the closest CN analogue to the SPY/QQQ universe; their EV (+1.95% bottom / +1.36% top) is the strongest CN cell after the small-sample stars.

This suggests the divergence engine generalizes best to broad-index instruments (consistent across US equities and CN index futures). Commodity-specific noise (rollover, supply-shock gaps, policy events) reduces signal quality, especially for the coal complex.

---

## 6. Outliers (extreme |signed_return| > 25% at h=20)

15 events. Top moves (mostly genuine — black/silver/crude regime shifts):

| symbol | date       | dir    | subtype  | conf | entry  | signed_ret |
|--------|------------|--------|----------|------|--------|-----------|
| ag0    | 2025-11-26 | bottom | weakness | 0.58 | 12,227 | +44.0%    |
| sc0    | 2026-01-27 | bottom | weakness | 0.71 | 446.7  | +43.5%    |
| i0     | 2015-09-03 | bottom | standard | 0.72 | 389.0  | +41.5%    |
| cu0    | 2008-09-26 | top    | weakness | 0.32 | 53,340 | +40.5%    |
| jm0    | 2025-07-08 | bottom | standard | 0.90 | 843.5  | +40.1%    |
| im0    | 2024-09-18 | bottom | standard | 0.62 | 4,405  | +33.2%    |
| i0     | 2017-03-20 | top    | weakness | 0.66 | 711.5  | +32.5%    |
| i0     | 2016-10-19 | bottom | standard | 0.81 | 436.0  | +32.3%    |

Most of these are concentrated in `i0` (iron ore) and `jm0` (coking coal), where actual ~30%-in-a-month moves are common. The 2008 `cu0` top during the GFC crash is a real macro event. None are obvious rollover artifacts (rollover discontinuities would typically be 1–5% gaps, well below the 25% threshold used).

Pooled-mean impact: removing all 15 outliers shifts the bottom h=20 mean from +1.31% to ≈ +1.25% — small and does not change rankings.

---

## 7. Top-3 / Bottom-3 by EV (n ≥ 10, h=20)

**Best**

| symbol | n  | hit  | avg_ret | note |
|--------|----|------|---------|------|
| im0    | 11 | 72.7%| +6.92%  | small sample (3.7y); CSI1000 mini-cap volatility |
| sc0    | 31 | 61.3%| +3.20%  | crude futures, big-move regime |
| i0     | 59 | 54.2%| +2.81%  | iron ore, China property cycle |

**Worst**

| symbol | n   | hit  | avg_ret | note |
|--------|-----|------|---------|------|
| m0     | 102 | 46.1%| +0.20%  | soybean meal — choppy + policy-sensitive |
| j0     | 78  | 47.4%| +0.00%  | coke — supply-side reform shocks |
| jm0    | 68  | 47.1%| -0.67%  | coking coal — only negative-EV symbol |

The coal complex (`j0` / `jm0`) is the only segment where MACD divergence detection actively underperforms; likely candidates for an instrument-class filter or a deeper investigation of how supply-shock gaps interact with the unit segmentation logic.

---

## 8. Conclusions & follow-ups

1. **Direction asymmetry (bottom > top) is preserved** in CN futures but at a smaller magnitude than US equities (1.31% vs 0.65% — gap is 0.66%, vs US's 3.44% gap). The US F8 / multi-TF lift does not transfer.
2. **Subtype ranking (standard > weakness > hidden) generalizes** across universes.
3. **F8 (bottom+weakness) is anti-monotone in confidence on CN** — opposite to US. The F8 confidence bump should be either (a) gated on multi-TF context availability or (b) re-tuned per universe. As-is, the F8 confirm-band on CN is *worse* than the watching band.
4. **Index futures > commodity futures** for divergence-following — IF / IC / IM are the strongest CN cells.
5. **Avoid coal** (`j0`, `jm0`) as a standalone divergence target until further analysis explains the negative EV.
6. **Add 60min CN data** to enable multi-TF context — this is the single largest expected lift based on the US round-3 results, and would let us test whether the F8 inversion is a multi-TF-absence artifact.

---

### Artifacts

- Long-format signal CSV: `src/data/review/cn_futures_signals_aggregate.csv` — 4,116 rows (1,372 signals × 3 horizons)
- Aggregator script: `src/scripts/backtest_cn_futures.py`
- Raw bars: `src/data/raw/{symbol}_daily.json` for symbols in `[if0 ih0 ic0 im0 cu0 m0 au0 ag0 rb0 i0 j0 jm0 p0 y0 ta0 ma0 cf0 sr0 sc0]`
