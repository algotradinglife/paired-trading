# Results Review Round 4 — Self-Contained Codex Pasteable Packet

**To Codex (GPT)**: This document is fully self-contained. You have **all** the
context, methodology, numbers, data fingerprints, and code semantics needed to
produce the Round-4 verification verdict without accessing any external file,
CSV, repository, or memory note. Every numeric statement below is sourced from
the actual artefacts (R4 packet, two underlying backtest reports, three CSV
fingerprints computed via pandas, three engine source files). Where a check
requires per-row reasoning (e.g. the "no rule fired" cell), the rows are inlined
verbatim.

The structure mirrors the prior R1-R3 packets:

1. The R4 packet itself (the prompt you would have received)
2. Inlined core content of the two new backtest reports referenced by the packet
3. Fingerprints of the three CSV artefacts (enough statistics to verify any
   per-bucket / per-symbol / per-rule claim)
4. Algorithm & calibration context (instrument_class, B-topology, divergence
   detection vocabulary, multi-TF context tag semantics) — not in the original
   packet but needed to evaluate the policy-change proposals
5. Expected output format + a checklist to self-audit

---

# Section 1 — Round 4 Packet (verbatim)

# Results Review Packet — Round 4 (2026-05-24)

**Purpose**: validate two new CN-market findings before any production policy
change. Both reports overturn prior CN assumptions; small-sample caveats are
heavy. Need rigorous Codex check before we touch `cn_futures` calibration.

**Prior reviews (for context)**:
- R1 verdict: `doc/codex-verdict-for-claude.md` (US F1-F4)
- R2 verdict: `doc/codex-verdict-round2-for-claude.md` (US F5-F9, F8 promoted)
- R3 packet: `doc/results-review-round3-2026-05-23.md` (US B1 spotlight,
  cn_futures policy draft — **verdict not yet incorporated**, still pending)

**This packet covers**:
- R4-CN-1: CN multi-TF B-topology backtest, doc/cn-b-topology-backtest-2026-05-24.md
- R4-CN-2: CN option-payoff backtest, doc/cn-option-payoff-backtest-2026-05-24.md

---

## Data files for verification

| File | Rows | Description |
|---|--:|---|
| `src/data/review/cn_b_topology_signals_all.csv` | 699 | 233 signals × 3 horizons across 19 CN futures, B-topology context attached |
| `src/data/review/cn_option_payoffs_all.csv` | 79 | Per-signal option payoffs for 4 products (m/i/au/cu) |
| `src/data/review/cn_option_payoffs_{m_i,au,cu}.csv` | — | Per-product subsets |
| Prior baseline: `src/data/review/option_payoffs_topology_b_no_nvda.csv` | 79 | US-equity B topology options for cross-comparison |

---

## R4-CN-1: B-Topology Findings (19 CN futures, 2.4y window)

### Headline reversal: CN top direction is now NEGATIVE

```
                  Prior single-TF (21y, n=400)    B-topology (2.4y, n=103)
top hit_rate           55.8%                            42%
top mean_ret           +0.65%                          -1.06%   ← REVERSED

bottom hit_rate        55.3%                            77%
bottom mean_ret        +1.31%                          +2.58%   ← STRONGER
```

The "CN tops are positive" claim from 2026-05-24 single-TF backtest was
the basis for `CN1-top-passthrough` (weight=1.00) and `direction_gate`
cn_futures pass-through. **B-topology data overturns this**.

**Verify**:
1. **Window selection bias vs multi-TF filter effect**: 2.4y window
   (Nov 2023 → Apr 2026) is dominated by bull regime for some products.
   How much of the top sign-flip is attributable to:
   - Multi-TF filter quality (the 1h higher-TF screens out late tops)
   - 2024-2026 specific market regime (post-COVID bull continuation)
   - Index-futures sample share (CFFEX 4 symbols may dominate top
     distribution; vs prior single-TF mostly commodities)
   Recommend: re-aggregate per-symbol direction stats; check which
   products contribute negative vs positive tops.

2. **Bonferroni / per-bucket significance**: with 19 products × 2
   directions × multi-TF bucket combos, family-wise error is large.
   Which findings survive BH-FDR α=0.05?

### Candidate F-rules on CN (what-if mode — none implemented in cn_futures policy)

| Equivalent rule | n | mean | Status |
|---|--:|--:|---|
| F2 (bot+leading+opposing) | 12 | +6.73% | small n, large effect |
| F4 (top+leading+opposing) | 10 | +3.40% | small n, surprising positive on tops |
| **CN-B1 (top+higher_opposing)** | **20** | **+2.51%** (80% hit) | strongest top bucket; clean US B1 analogue |
| F8 (bot+weakness) | 56 | +3.81% | largest sample, ranks as workhorse |
| **`top + higher=supporting`** (proposed weight 0.80) | **74** | **-1.59%** (43% hit) | **largest negative-EV cell** |

**Verify per-candidate**:
- Symbol HHI per bucket (must be < 0.30 to be diversified)
- Bootstrap 95% CI on mean (must not cross zero for "actionable")
- Stability under drop-top-2 (outlier robustness)
- 2024 vs 2025 vs 2026 sub-period stability

### F8 confidence anti-monotonicity persists?

Prior single-TF baseline: F8 (bot+weakness) confidence band ANTI-monotone
(watching > confirmed). Has B-topology changed this?

**Verify**: re-compute F8 across (confidence_band × multi_tf_context).

---

## R4-CN-2: Option-Payoff Findings (4 products, 79 trades)

### F8 product-bimodal — au is the only clean winner

| Product F8 | n | h=20 raw | SL -5% |
|---|--:|--:|--:|
| **au F8** | **8** | **+118.6%** | **+139%** ← rivals US F8 |
| cu F8 | — | -14 to -24% | mechanical recovery only |
| i F8 | — | -14 to -24% | mechanical recovery only |
| m F8 | 3 | net loss | sample too small |

**Verify**:
1. **Is au F8 a genuine product edge** or a regime artifact (gold rally
   2024-2026)? Re-run with date-stratified buckets if possible.
2. **n=8 for au F8** is below Codex's typical "actionable" threshold.
   With Bonferroni across 4 product × 5+ rule cells, does this survive?
3. The +118.6% mean — is it driven by 1-2 outliers? Drop-top-2 + bootstrap CI.

### "No rule fired" cell — +119.5% on n=10

The largest single positive EV in the entire R4-CN-2 dataset is the
baseline (no F-rule fired) cell, primarily clean m bottoms. This
**contradicts the cn_futures policy design** which assumes F8 captures
the high-EV bottom signal.

**Verify**:
- What ARE these 10 trades? Show contract IDs + dates + returns
- Are 4 trades > +100% the same period (i.e. one rally)?
- Median return vs mean for this cell (winner-tail driven?)
- If real: implies F8/CN1 fusion is gating-out valid bottom signals
  rather than enhancing them — policy needs subtraction not addition

### CN top option payoff mirrors US F1 pattern

```
CN tops:      -42.6% raw → +16.8% at SL -3% (mechanical recovery)
US F1 (R3):   -69.1% raw → +1.7% at SL -3% (same pattern)
```

Both are "lots of small stops + occasional big win" — **trade-style alpha,
not signal alpha**. The CN top sign is now consistent with US after
multi-TF filter.

**Verify**:
- Stop-hit rate on CN tops — should match US F1's 72-94%
- Does the "tight stop saves it" effect have any persistence in true
  intraday path simulation (acknowledged as upper bound in report)?

### CN F8 vs US F8 — same right tail or different?

Distribution shape comparison (option-premium return at h=20):
- US F8 (n=38, R3): winners avg +129%, p75 +155%, 32% trades > +60%
- CN F8 au only (n=8): raw mean +118.6%

If shapes match, F8 generalizes globally with product-class filter.
If CN F8 has thinner right tail (just 1-2 mega winners), au F8 is luck.

---

## Cross-cutting decisions Codex needs to resolve

### 1. `cn_futures` policy direction de-weight

Current `_apply_cn_futures` does NOT de-weight tops because of the
now-refuted "CN tops positive" claim. New evidence:
- B-topology: top mean -1.06% (n=103)
- Option payoff: top raw -42.6% (n=~30)

**Question for Codex**: Recommend new top-direction weight for cn_futures?
Options:
(a) Match US F1 soft de-weight (0.70)
(b) Stricter de-weight (0.50-0.60) — multi-TF + option both negative
(c) Stay 1.00 pending more data — current sample sizes too small to bet
(d) Differentiated by sub-bucket (e.g. top+higher_opposing gets boost,
    top+higher_supporting gets drop)

### 2. F8 product-class subdivision

Current `F8-cn-no-boost` (weight 1.00) is uniform across products. New
evidence: F8 EV varies wildly (au +118%, cu/i -14%, m losses).

**Question**: Should we subdivide F8 by product class? Risk: tiny n per
product. Conservative answer: leave uniform, surface product preference
in strategy_hints. Aggressive: separate F8-au / F8-other rules.

### 3. CN-B1 promotion

`top + higher_opposing` shows n=20, 80% hit, +2.51% on stocks. Looks
like a real bucket. But our adoption threshold has been n=50.

**Question**: Adopt B1-style rule on CN with monitor flag now (weight
1.20)? Or wait for more 15min depth to grow n past 50?

### 4. The "no rule fired" mystery cell

R4-CN-2 "no rule fired" +119.5% (n=10) is the loudest signal we have
on CN options. **Question**: Is this:
- (a) Real evidence that F8/CN1 fusion adds noise — policy should subtract
- (b) Selection artifact (small sample, lucky m bottoms in soybean rally)
- (c) Coincidence from product-month overlap

Need contract-level breakdown to disambiguate.

---

## Expected output format

Same as R1-R3 verdict files:

```markdown
# Codex Round 4 Verification

## Headline reversals
- [CN top direction] survives ✅ / collapses ❌ / edge ⚠️

## Per-finding verdicts
- F8-cn product bimodality: ...
- CN-B1 candidate: ...
- "no rule fired" cell: ...
- top + higher_supporting de-weight (proposed): ...
- ...

## Recommended policy changes (if any)
- cn_futures top direction: weight = ?
- ...

## Methodology flags
- ...
```

Codex output → `doc/codex-verdict-round4-for-claude.md` (or whatever
naming you prefer); I'll integrate into policy on receipt.

---

# Section 2 — Underlying Reports (inlined, prose-trimmed)

## 2.1 CN Futures B-Topology Backtest (R4-CN-1)

Backtest of the divergence detection + multi-TF context + downstream policy
stack on **19 Chinese futures 主力连续 contracts** with **B topology**
(primary=D, lower=15m, higher=1h). All three TFs sourced via TqSdk
2026-05-23/24.

- Script: `src/scripts/backtest_cn_b_topology.py`
- Long-format CSV: `src/data/review/cn_b_topology_signals_all.csv`
- Instrument class: `cn_futures` (direction_gate pass-through; CN policy applied)
- Horizons: **5 / 10 / 20** trading days
- Multi-TF coverage window: **2023-11-12 → 2026-04-21** (≈2.4y)
- Total evaluable signals: **233** (130 bottom, 103 top); 100% enriched with multi-TF context

### 2.1.1 Methodology

Pipeline per symbol:

1. Load daily / 60min / 15min bars from
   `data/raw/kq_m_<exch>_<product>_{daily,60,15}.json`.
2. Compute MACD (12, 26, 9, `hist_scale=1.0`) on daily bars.
3. Compute feature streams → unit metadata.
4. Run `detect_all_divergences(..., instrument_class="cn_futures")` —
   `direction_gate` becomes pass-through (1.0 multiplier on top signals).
5. Restrict signals to the **intersection window** of 60min and 15min coverage
   (the limiting factor; 15min depth is the bottleneck).
6. Enrich with 60min via `enrich_with_higher_tf(..., higher_tf_level_id="1h")`.
7. Enrich with 15min via `enrich_with_lower_tf(..., lower_tf_level_id="15m")`.
8. Apply `apply_policy(sig, "cn_futures")` for per-rule weighting.
9. Forward-return at h ∈ {5, 10, 20}, signed by direction; `hit = signed_return > 0`.

**Caveats / data quality**

- **Short common window**: 15min depth restricts pooled sample to ~2.4y. n=233
  vs prior single-TF (no window restriction) n=1,372. Per-bucket samples often
  ≤ 20 — confidence intervals are wide.
- **TqSdk continuous-main splicing** (KQ.m@…): same rollover-gap artefact as
  AKShare data; not materially different from prior baseline.
- **Window covers 2024-2026 only**: regime includes the 2024 CN equity rally +
  2025 sideways + commodities bear. Direction-asymmetry result is
  regime-conditional in a way the 21y baseline was not.
- **Multi-TF rules F2/F4/B1 are not part of CN policy** — they only fire
  under `us_equity`. Below we report informational "what-if" buckets using
  the same context tags, but the deployed CN policy keeps top divergences at
  pass-through weight (`CN1-top-passthrough`) and the only fired specific
  rule is `F8-cn-no-boost` for bottom+weakness.

### 2.1.2 Pooled aggregates

**Direction baseline (h=20)**:

| direction | n   | hit_rate | avg_ret | median  |
|-----------|----:|---------:|--------:|--------:|
| bottom    | 130 | 60.0%    | +2.58%  | +0.99%  |
| top       | 103 | 48.5%    | **-1.06%** | -0.19% |

| direction | h=5 hit | h=5 avg | h=10 hit | h=10 avg |
|-----------|--------:|--------:|---------:|---------:|
| bottom    | 60.8%   | +0.77%  | 54.6%    | +1.72%   |
| top       | 53.4%   | +0.48%  | 55.3%    | -0.45%   |

**Per-rule (cn_futures policy, h=20)**:

| rule_id                | n   | hit_rate | avg_ret | median  |
|------------------------|----:|---------:|--------:|--------:|
| F8-cn-no-boost         | 56  | 76.8%    | +3.81%  | +1.56%  |
| CN1-top-passthrough    | 103 | 48.5%    | -1.06%  | -0.19%  |
| — (baseline)           | 74  | 47.3%    | +1.64%  | -0.15%  |

The baseline bucket is **non-weakness bottoms** (standard + hidden). F8'
(bottom + weakness) is the clear workhorse — exactly the pattern the
US-equity F8 captures.

**Subtype × direction (h=20)**:

| direction | subtype  | n  | hit_rate | avg_ret | median  |
|-----------|----------|---:|---------:|--------:|--------:|
| bottom    | standard | 66 | 48.5%    | +1.68%  | -0.10%  |
| bottom    | weakness | 56 | **76.8%** | **+3.81%** | +1.56% |
| bottom    | hidden   |  8 | 37.5%    | +1.33%  | -0.84%  |
| top       | standard | 16 | 43.8%    | -2.14%  | -0.91%  |
| top       | weakness | 79 | 51.9%    | -0.58%  | +0.26%  |
| top       | hidden   |  8 | 25.0%    | **-3.64%** | -1.89% |

**F8' (bottom + weakness) × confidence band (h=20)**:

| band      | n  | hit_rate | avg_ret |
|-----------|---:|---------:|--------:|
| watching  |  7 | 85.7%    | +1.65%  |
| forming   |  7 | 85.7%    | **+8.07%** |
| candidate | 13 | 76.9%    | +5.42%  |
| confirmed | 29 | 72.4%    | +2.59%  |

**Confidence band remains anti-monotone in CN** under B topology
(forming/watching beat confirmed). Same finding as the single-TF baseline.

### 2.1.3 Multi-TF context cuts

**Direction × higher_relation (1h, h=20)**:

| direction | higher_relation | n  | hit_rate | avg_ret |
|-----------|-----------------|---:|---------:|--------:|
| bottom    | neutral         | 10 | **90.0%** | **+8.71%** |
| bottom    | opposing        | 25 | 60.0%    | +4.36%  |
| bottom    | supporting      | 95 | 56.8%    | +1.46%  |
| top       | neutral         |  9 | 22.2%    | -4.65%  |
| top       | opposing        | 20 | **80.0%** | **+2.51%** |
| top       | supporting      | 74 | 43.2%    | -1.59%  |

**Direction × lower_relation (15m, h=20)**:

| direction | lower_relation | n  | hit_rate | avg_ret |
|-----------|----------------|---:|---------:|--------:|
| bottom    | lagging        | 84 | 59.5%    | +1.61%  |
| bottom    | leading        | 32 | 62.5%    | +4.32%  |
| bottom    | pivoting       | 14 | 57.1%    | +4.39%  |
| top       | lagging        | 59 | 57.6%    | +0.09%  |
| top       | leading        | 32 | 37.5%    | -3.30%  |
| top       | pivoting       | 12 | 33.3%    | -0.74%  |

**Direction × lower × higher (h=20, n ≥ 6 shown)**:

| direction | lower    | higher     | n  | hit_rate | avg_ret |
|-----------|----------|------------|---:|---------:|--------:|
| bottom    | lagging  | supporting | 70 | 60.0%    | +1.56%  |
| bottom    | leading  | supporting | 17 | 52.9%    | +0.66%  |
| bottom    | leading  | opposing   | 12 | 66.7%    | **+6.73%** |
| bottom    | lagging  | neutral    |  7 | 85.7%    | +5.84%  |
| bottom    | lagging  | opposing   |  7 | 28.6%    | -2.04%  |
| bottom    | pivoting | opposing   |  6 | 83.3%    | +7.09%  |
| bottom    | pivoting | supporting |  8 | 37.5%    | +2.37%  |
| top       | lagging  | supporting | 48 | 54.2%    | -0.10%  |
| top       | leading  | supporting | 18 | 22.2%    | -5.44%  |
| top       | leading  | opposing   | 10 | **80.0%** | **+3.40%** |
| top       | lagging  | opposing   |  7 | 85.7%    | +1.06%  |
| top       | pivoting | supporting |  8 | 25.0%    | -1.85%  |

**Informational "what-if" — US F-rule equivalents applied to CN**

What the US F-rules would have selected on this CN sample (the CN policy does
NOT fire any of these — included for calibration insight only):

| US rule | predicate                                    | n  | hit_rate | avg_ret | median |
|---------|----------------------------------------------|---:|---------:|--------:|-------:|
| F2-equiv | bottom + lower=leading + higher=opposing    | 12 | 66.7%   | **+6.73%** | +5.82% |
| F4-equiv | top + lower=leading + higher=opposing       | 10 | 80.0%   | +3.40%  | +3.52% |
| B1-equiv | top + higher=opposing (incl. F4)            | 20 | 80.0%   | +2.51%  | +2.90% |
| B1-resid | top + higher=opposing, lower≠leading        | 10 | 80.0%   | +1.63%  | +2.79% |
| F1-equiv | top + lower=lagging                          | 59 | 57.6%   | +0.09%  | +1.30% |
| F3-equiv | candidate (0.65 ≤ conf < 0.80) + higher=opposing | 11 | 72.7% | +3.35% | +2.71% |

**All five US F-rules would have produced positive EV on CN under
B-topology**. Most-striking: F1 (US "soft de-weight" rule for top+lagging)
is +0.09% on CN, not the strongly negative bucket the US calibration
de-weights. The US calibration is over-penalising this cell on CN.

### 2.1.4 Per-symbol breakdown (h=20)

| symbol             | bot n | bot hit | bot avg | top n | top hit | top avg |
|--------------------|------:|--------:|--------:|------:|--------:|--------:|
| kq_m_cffex_if      |     9 | 78%     | +2.85%  |     9 | 56%     | -2.33%  |
| kq_m_cffex_ih      |    11 | 82%     | +1.85%  |     9 | 33%     | -1.48%  |
| kq_m_cffex_ic      |     6 | 67%     | +3.39%  |     9 | 67%     | +0.87%  |
| kq_m_cffex_im      |    10 | 80%     | +8.35%  |     7 | 43%     | -4.48%  |
| kq_m_shfe_rb       |    10 | 30%     | -0.36%  |     7 | 43%     | -0.36%  |
| kq_m_shfe_cu       |     3 | 100%    | +1.65%  |     3 | 33%     | -0.99%  |
| kq_m_shfe_au       |     4 | 75%     | +6.70%  |     2 | 50%     | +1.17%  |
| kq_m_shfe_ag       |     3 | 100%    | **+19.76%** | 2 | 0%   | **-15.26%** |
| kq_m_dce_m         |     8 | 50%     | +0.47%  |     6 | 33%     | -2.43%  |
| kq_m_dce_i         |    10 | 70%     | +2.45%  |     9 | 11%     | -3.92%  |
| kq_m_dce_j         |     7 | 29%     | -1.92%  |     6 | 50%     | -1.13%  |
| kq_m_dce_jm        |     9 | 33%     | -0.01%  |     8 | 62%     | +2.24%  |
| kq_m_dce_p         |     4 | 100%    | +3.27%  |     5 | 80%     | +3.72%  |
| kq_m_dce_y         |     7 | 43%     | -1.20%  |     3 | 33%     | +1.01%  |
| kq_m_czce_ta       |     5 | 20%     | -0.55%  |     4 | 75%     | +1.61%  |
| kq_m_czce_ma       |     7 | 57%     | +3.26%  |     3 | 33%     | -0.72%  |
| kq_m_czce_cf       |     5 | 60%     | +1.99%  |     4 | 100%    | +4.54%  |
| kq_m_czce_sr       |     8 | 50%     | +0.01%  |     5 | 80%     | +0.42%  |
| kq_m_ine_sc        |     4 | 75%     | +12.12% |     2 | 0%      | -12.55% |

**Group rollup**:

| group           | direction | n  | hit_rate | avg_ret |
|-----------------|-----------|---:|---------:|--------:|
| index (IF/IH/IC/IM) | bottom | 36 | **77.8%** | **+4.17%** |
| index           | top       | 34 | 50.0%    | -1.70%  |
| coal (j/jm)     | bottom    | 16 | 31.2%    | -0.85%  |
| coal            | top       | 14 | 57.1%    | +0.80%  |
| other commodity | bottom    | 78 | 57.7%    | +2.55%  |
| other commodity | top       | 55 | 45.5%    | -1.14%  |

- **Index futures dominance confirmed and stronger than baseline**: bottoms
  77.8% / +4.17% (vs prior 63.7% / +1.95%). Index tops have flipped *negative*
  on this window (-1.70%) vs prior +1.36% — consistent with the regime change.
- **Coal complex underperforms on bottoms only**: j/jm bottoms 31% hit /
  -0.85% (worst cell). Tops on coal are mildly positive — failure mode has
  shifted from "tops fade" to "bottoms fail to reverse".
- **Small-sample outliers**: `ag` (n=3 bot / +19.76%, n=2 top / -15.26%) and
  `sc` (n=4 bot / +12.12%, n=2 top / -12.55%) — single regime moves (silver
  squeeze, crude shock) and should not influence policy.

### 2.1.5 Comparison to baselines

**vs prior CN single-TF baseline (2026-05-24, n=1,372)**:

| metric              | CN single-TF (n=1,372) | CN B-topology (n=233) | Δ                          |
|---------------------|------------------------|------------------------|----------------------------|
| bottom hit / avg    | 55.3% / +1.31%         | 60.0% / +2.58%         | +4.7 pp / +1.27%           |
| top hit / avg       | 55.8% / **+0.65%**     | 48.5% / **-1.06%**     | -7.3 pp / **-1.71%** (sign flip) |
| best subtype (bot)  | standard (+2.17%)      | weakness (+3.81%)      | F8 reasserts               |
| F8 conf-band order  | anti-monotone          | anti-monotone          | same — robust              |
| index futures (bot) | 63.7% / +1.95%         | 77.8% / +4.17%         | +14 pp / +2.22%            |
| coal (bot)          | 47% / 0%               | 31% / -0.85%           | worse                      |

Three competing explanations for the top sign-flip:

1. **Regime**: 2024-2026 is a window where CN tops *did* fade harder.
2. **Sample composition**: 233 signals concentrated in index futures (44% vs
   ~11% in the 21y baseline). Index futures show a clear top-fade pattern.
3. **Window-conditioned higher-TF context**: with 1h context available, top
   signals where 1h still supports the trend (the "supporting" bucket, n=74)
   are reliably negative (-1.59%).

The report estimates 60-70% (1)+(2) and 30-40% (3), but with n=233 over 2.4y
the explanations cannot be fully separated.

**vs US B-topology baseline (n=266, 10 symbols, 5y)**:

| bucket                             | US                  | CN                  |
|------------------------------------|---------------------|---------------------|
| bottom (overall)                   | 69% / +3.17%        | 60% / +2.58%        |
| top (overall)                      | 53% / -0.27%        | 49% / -1.06%        |
| `top + higher_opposing`            | n=11, 65% / +0.45%  | **n=20, 80% / +2.51%** |
| `bottom + higher_opposing`         | n=47, 79% / +4.79%  | n=25, 60% / +4.36%  |
| F8 (bot + weakness, all bands)     | +73% EV (R3, SL-3)  | +3.81% (h=20, no SL) |

### 2.1.6 Recommended CN policy adjustments (report author)

| Proposal | Bucket | Current | Proposed | n | Status |
|----------|--------|---------|----------|---|--------|
| Add CN-B1 | top + higher=opposing | 1.00 (CN1) | **1.20** | 20 | monitor (n<50) |
| Add CN-F8-monotonic-fix | bottom + weakness + conf ≥ 0.80 | 1.00 (F8') | 0.85 | 29 | monitor |
| Add CN-F8-bump-low-band | bottom + weakness + conf < 0.65 | 1.00 (F8') | 1.15 | 14 | monitor (n<50) |
| Add CN top-supporting fade | top + higher=supporting | 1.00 (CN1) | 0.80 | 74 | **eligible** for production rule |
| Reaffirm CN1-passthrough | top (no other rule) | 1.00 | 1.00 | — | keep |
| Reaffirm symbol blacklist | j0 / jm0 | hint | hint | — | keep |

---

## 2.2 CN Option Payoff Backtest (R4-CN-2)

Tests divergence signals on **CN futures** by buying ATM monthly options at
signal time and measuring premium return at h=5/10/20 trading days. Pairs with
the equity-side `option_payoff_backtest.py` baseline for direct comparison.

- Script: `src/scripts/option_payoff_backtest_cn.py`
- Output: `src/data/review/cn_option_payoffs_all.csv` (79 rows)
- Data source: TqSdk (Shinny / 快期) option K-line history
- Underlyings: 4 products — `m` (soymeal, DCE), `i` (iron ore, DCE),
  `au` (gold, SHFE), `cu` (copper, SHFE)

### 2.2.1 Methodology

For each daily MACD divergence signal on a CN futures continuous-main series
(min_conf 0.50, most-recent 30 per product, max 20 for SHFE):

1. Bottom signal → buy ATM **CALL** ~75 DTE ahead.
   Top signal → buy ATM **PUT** ~75 DTE ahead.
2. Walk 50–120 days forward from signal date, pick (year, month) in product's
   listed expiry-month set closest to 75 DTE.
3. Underlying = `<EXCH>.<product><YY><MM>` (e.g. `DCE.m2509`, `SHFE.au2602`).
4. `api.query_options(underlying, option_class=...)` returns all known strikes;
   pick strike closest to signal-day close.
5. `api.get_kline_serial(contract, 86400, data_length=500)` to fetch daily
   premium history.
6. h{N}_ret = `(premium[t+N] - premium[t]) / premium[t]` where index advances
   by trading days.

**Parameters**: `TARGET_DTE = 75`, `DTE_WINDOW_MIN=50`, `DTE_WINDOW_MAX=120`,
`WAIT_DEADLINE_SEC = 15` per option K-line fetch, min_conf = 0.50,
max_signals = 30 per product (20 for SHFE due to API pacing).

**Notable script fix**: SHFE / CZCE option contracts use **compact naming**
(`SHFE.au2602C960`) while DCE uses **hyphen-separated** (`DCE.m2509-C-2900`).
First run silently dropped all SHFE strikes; fixed via fallback regex
`r"[CP](\d+(?:\.\d+)?)$"`.

**Caveats**

- **Small samples per cell** (n=8–22). Numbers are directional, not precise.
- **Daily-close premium only** — same upper-bound caveat as US tight-stop
  analysis ("SL -3%" column is a best-case for tight stops).
- **Skip rate 21%** (21/100 attempts): tail signals (forward window < 20 bars),
  no option month with matching strikes, etc.
- **Liquidity assumption**: ATM monthly options at 75 DTE assumed liquid
  enough for close to be a meaningful fill — not verified per-trade.
- **No 75-DTE matching for SHFE pre-2020**: au options listed 2019-12;
  cu options listed 2018-09; earlier signals auto-skip.

### 2.2.2 Coverage

| product | n   | symbol  | options-listing  | first signal eval'd | last signal eval'd |
|---------|-----|---------|------------------|---------------------|--------------------|
| m       | 22  | DCE.m   | 2017-03-31       | 2022-06-23          | 2026-02-26         |
| i       | 22  | DCE.i   | 2019-12-09       | 2023-03-09          | 2026-04-13         |
| au      | 15  | SHFE.au | 2019-12-20       | 2023-03-05          | 2026-04-15         |
| cu      | 20  | SHFE.cu | 2018-09-21       | (recent)            | (recent)           |

Total payoff rows: **79**. Skip rates: m 8/30, i 8/30, au 5/20, cu 0/20.

### 2.2.3 Aggregate results

**Per-direction (h=5/10/20)**:

| direction | n  | h5 mean / hit  | h10 mean / hit | h20 mean / hit |
|-----------|----|----------------|----------------|----------------|
| bottom    | 42 | **+25.6%** / 57% | **+38.0%** / 40% | **+35.1%** / 29% |
| top       | 37 | -21.2% / 24%   | -34.7% / 24%   | -42.6% / 19%   |

**Per-symbol (h=20)**:

| symbol | n  | hit  | raw mean | median  | min     | max      |
|--------|----|------|----------|---------|---------|----------|
| au     | 15 | 40%  | **+65.2%** | -44.9%  | -97.3%  | +701.3%  |
| m      | 22 | 23%  | **+12.1%** | -67.2%  | -99.2%  | +640.0%  |
| cu     | 20 | 20%  | -35.2%   | -41.5%  | -97.9%  | +105.5%  |
| i      | 22 | 18%  | -29.2%   | -59.7%  | -99.7%  | +182.1%  |

**Per-rule (h=20, raw + tight-stop sim)**:

| rule_id                  | n  | hit  | raw    | SL-30   | SL-10   | SL-5    | SL-3    |
|--------------------------|----|------|--------|---------|---------|---------|---------|
| `—` (no rule)            | 10 | 40%  | **+119.5%** | +146.4% | +158.4% | +161.4% | +162.6% |
| F8-cn-no-boost           | 32 | 25%  | +8.8%  | +27.9%  | +39.2%  | +42.6%  | +44.0%  |
| CN1-top-passthrough      | 37 | 19%  | -42.6% | -4.1%   | +11.1%  | +15.2%  | +16.8%  |

**Tight-stop matrix — all signals pooled (n=79)**:

| horizon | raw     | SL-30   | SL-10   | SL-5    | SL-3    |
|---------|---------|---------|---------|---------|---------|
| h=5     | +3.7%   | +9.5%   | +17.2%  | +19.8%  | +20.9%  |
| h=10    | +3.9%   | +18.6%  | +29.2%  | +32.3%  | +33.5%  |
| h=20    | -1.3%   | +27.9%  | +41.2%  | +44.8%  | +46.3%  |

**F8 (bottom + weakness) per-product (h=20)**:

| product | n  | hit | raw   | SL-10 | SL-5  |
|---------|----|-----|-------|-------|-------|
| au      | 8  | 50% | +118.6% | +137.5% | +139.4% |
| cu      | 9  | 22% | -14.5% | +7.2% | +11.1% |
| i       | 12 | 17% | -23.5% | +10.1% | +13.7% |
| m       | 3  | 0%  | -85.4% | -10.0% | -5.0%  |

### 2.2.4 Comparison vs US baseline

| metric                           | US (n=79, multi-symbol)   | CN (n=79, m/i/au/cu)    |
|----------------------------------|---------------------------|-------------------------|
| total payoff rows                | 79                        | 79                      |
| bottom mean h=20                 | +51% (F8 only n=38)       | **+35.1%** (n=42)       |
| top mean h=20                    | -65% raw, +1.7% SL-3 (n=18 F1) | -42.6% raw, +16.8% SL-3 (n=37) |
| F8 SL-3 EV @ h=20                | **+73.5%** (n=38)         | +44.0% (n=32)           |
| spotlight bucket (top+higher_opposing) | +24.7% (n=11)       | not measured (no multi-TF) |

### 2.2.5 Big winners (h20 > +100%)

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

### 2.2.6 Distribution

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

The **median is -58%** but the **mean is -1.3%** — classic right-tail
distribution.

---

# Section 3 — CSV Fingerprints (computed via pandas — every claim verifiable)

These fingerprint blocks come from running pandas over the actual CSV files
the packet references. Numbers are exact (not rounded for the report).

## 3.A `cn_b_topology_signals_all.csv` (700 rows incl. header → 699 data rows)

**Columns** (17 total):
```
symbol, date, direction, subtype, level, confidence, rule_id, rule_weight,
lower_side, lower_cycle, lower_relation, higher_side, higher_cycle,
higher_relation, horizon, hit, signed_return
```

**Long format** — each unique signal expanded to 3 rows (one per horizon
∈ {5, 10, 20}).

| Metric | Value |
|---|---|
| Total rows | 699 |
| Unique signals (symbol+date+direction) | 233 |
| Horizon distribution | 5: 233, 10: 233, 20: 233 |

**Direction distribution (unique signals)**:

| direction | count |
|---|--:|
| bottom | 130 |
| top    | 103 |

**rule_id distribution (unique signals)**:

| rule_id | count |
|---|--:|
| CN1-top-passthrough | 103 |
| — (baseline) | 74 |
| F8-cn-no-boost | 56 |

Note: only **three** rule_ids ever fire under cn_futures policy. All 103 top
signals → `CN1-top-passthrough`. All 56 bottom-weakness → `F8-cn-no-boost`.
Remaining 74 bottoms (66 standard + 8 hidden) → baseline `—`.

**Subtype × direction (unique signals)**:

| direction | subtype  | n |
|-----------|----------|--:|
| bottom    | hidden   | 8 |
| bottom    | standard | 66 |
| bottom    | weakness | 56 |
| top       | hidden   | 8 |
| top       | standard | 16 |
| top       | weakness | 79 |

**Direction × horizon (n / mean / hit)** — confirms the headline numbers:

| direction | horizon | n   | mean    | hit    |
|-----------|--------:|----:|--------:|-------:|
| bottom    |       5 | 130 | +0.77%  | 60.77% |
| bottom    |      10 | 130 | +1.72%  | 54.62% |
| bottom    |      20 | 130 | +2.58%  | 60.00% |
| top       |       5 | 103 | +0.48%  | 53.40% |
| top       |      10 | 103 | -0.45%  | 55.34% |
| top       |      20 | 103 | **-1.06%** | 48.54% |

**rule_id × h=20 (n / mean / hit)** — confirms per-rule pooled aggregates:

| rule_id | n | mean | hit |
|---|--:|--:|--:|
| CN1-top-passthrough | 103 | -1.06% | 48.54% |
| F8-cn-no-boost      | 56  | +3.81% | 76.79% |
| — (baseline)        | 74  | +1.64% | 47.30% |

**Direction × subtype @ h=20**:

| direction | subtype  | n  | mean    | hit    | median  |
|-----------|----------|---:|--------:|-------:|--------:|
| bottom    | hidden   |  8 | +1.33%  | 37.50% | -0.84%  |
| bottom    | standard | 66 | +1.68%  | 48.48% | -0.10%  |
| bottom    | weakness | 56 | +3.81%  | 76.79% | +1.56%  |
| top       | hidden   |  8 | -3.64%  | 25.00% | -1.89%  |
| top       | standard | 16 | -2.14%  | 43.75% | -0.91%  |
| top       | weakness | 79 | -0.58%  | 51.90% | +0.26%  |

**F8' (bottom + weakness) × confidence band @ h=20** — bands per
`downstream_policies.conf_band`: dormant <0.30, watching <0.50, forming <0.65,
candidate <0.80, confirmed ≥0.80.

| band      | n  | mean    | hit    |
|-----------|---:|--------:|-------:|
| watching  |  7 | +1.65%  | 85.71% |
| forming   |  7 | +8.07%  | 85.71% |
| candidate | 13 | +5.42%  | 76.92% |
| confirmed | 29 | +2.59%  | 72.41% |

→ **Anti-monotone in mean** (forming +8% > candidate +5% > confirmed +2.6%).
Hit-rate ordering is also weakly anti-monotone.

**Direction × higher_relation @ h=20**:

| direction | higher_relation | n  | mean    | hit    |
|-----------|-----------------|---:|--------:|-------:|
| bottom    | neutral         | 10 | +8.71%  | 90.00% |
| bottom    | opposing        | 25 | +4.36%  | 60.00% |
| bottom    | supporting      | 95 | +1.46%  | 56.84% |
| top       | neutral         |  9 | -4.65%  | 22.22% |
| top       | opposing        | 20 | +2.51%  | 80.00% |
| top       | supporting      | 74 | -1.59%  | 43.24% |

**Direction × lower_relation @ h=20**:

| direction | lower_relation | n  | mean    | hit    |
|-----------|----------------|---:|--------:|-------:|
| bottom    | lagging        | 84 | +1.61%  | 59.52% |
| bottom    | leading        | 32 | +4.32%  | 62.50% |
| bottom    | pivoting       | 14 | +4.39%  | 57.14% |
| top       | lagging        | 59 | +0.09%  | 57.63% |
| top       | leading        | 32 | -3.30%  | 37.50% |
| top       | pivoting       | 12 | -0.74%  | 33.33% |

**Direction × higher × lower @ h=20 (n ≥ 6)**:

| direction | higher_relation | lower_relation | n  | mean   | hit   |
|-----------|-----------------|----------------|---:|-------:|------:|
| bottom    | neutral         | lagging        |  7 | +5.84% | 85.71% |
| bottom    | opposing        | lagging        |  7 | -2.04% | 28.57% |
| bottom    | opposing        | leading        | 12 | +6.73% | 66.67% |
| bottom    | opposing        | pivoting       |  6 | +7.09% | 83.33% |
| bottom    | supporting      | lagging        | 70 | +1.56% | 60.00% |
| bottom    | supporting      | leading        | 17 | +0.66% | 52.94% |
| bottom    | supporting      | pivoting       |  8 | +2.37% | 37.50% |
| top       | opposing        | lagging        |  7 | +1.06% | 85.71% |
| top       | opposing        | leading        | 10 | +3.40% | 80.00% |
| top       | supporting      | lagging        | 48 | -0.10% | 54.17% |
| top       | supporting      | leading        | 18 | -5.44% | 22.22% |
| top       | supporting      | pivoting       |  8 | -1.85% | 25.00% |

**Per-symbol direction breakdown (h=20)** — full table from fingerprint
(matches report §2.1.4 above; included again here for direct verification):

| symbol               | dir    | n  | mean    | hit    |
|----------------------|--------|---:|--------:|-------:|
| kq_m_cffex_ic        | bottom |  6 | +3.39%  | 66.67% |
| kq_m_cffex_ic        | top    |  9 | +0.87%  | 66.67% |
| kq_m_cffex_if        | bottom |  9 | +2.85%  | 77.78% |
| kq_m_cffex_if        | top    |  9 | -2.33%  | 55.56% |
| kq_m_cffex_ih        | bottom | 11 | +1.85%  | 81.82% |
| kq_m_cffex_ih        | top    |  9 | -1.48%  | 33.33% |
| kq_m_cffex_im        | bottom | 10 | +8.35%  | 80.00% |
| kq_m_cffex_im        | top    |  7 | -4.48%  | 42.86% |
| kq_m_czce_cf         | bottom |  5 | +1.99%  | 60.00% |
| kq_m_czce_cf         | top    |  4 | +4.54%  | 100.00% |
| kq_m_czce_ma         | bottom |  7 | +3.26%  | 57.14% |
| kq_m_czce_ma         | top    |  3 | -0.72%  | 33.33% |
| kq_m_czce_sr         | bottom |  8 | +0.01%  | 50.00% |
| kq_m_czce_sr         | top    |  5 | +0.42%  | 80.00% |
| kq_m_czce_ta         | bottom |  5 | -0.55%  | 20.00% |
| kq_m_czce_ta         | top    |  4 | +1.61%  | 75.00% |
| kq_m_dce_i           | bottom | 10 | +2.45%  | 70.00% |
| kq_m_dce_i           | top    |  9 | -3.92%  | 11.11% |
| kq_m_dce_j           | bottom |  7 | -1.92%  | 28.57% |
| kq_m_dce_j           | top    |  6 | -1.13%  | 50.00% |
| kq_m_dce_jm          | bottom |  9 | -0.01%  | 33.33% |
| kq_m_dce_jm          | top    |  8 | +2.24%  | 62.50% |
| kq_m_dce_m           | bottom |  8 | +0.47%  | 50.00% |
| kq_m_dce_m           | top    |  6 | -2.43%  | 33.33% |
| kq_m_dce_p           | bottom |  4 | +3.27%  | 100.00% |
| kq_m_dce_p           | top    |  5 | +3.72%  | 80.00% |
| kq_m_dce_y           | bottom |  7 | -1.20%  | 42.86% |
| kq_m_dce_y           | top    |  3 | +1.01%  | 33.33% |
| kq_m_ine_sc          | bottom |  4 | +12.12% | 75.00% |
| kq_m_ine_sc          | top    |  2 | -12.55% | 0.00% |
| kq_m_shfe_ag         | bottom |  3 | +19.76% | 100.00% |
| kq_m_shfe_ag         | top    |  2 | -15.26% | 0.00% |
| kq_m_shfe_au         | bottom |  4 | +6.70%  | 75.00% |
| kq_m_shfe_au         | top    |  2 | +1.17%  | 50.00% |
| kq_m_shfe_cu         | bottom |  3 | +1.65%  | 100.00% |
| kq_m_shfe_cu         | top    |  3 | -0.99%  | 33.33% |
| kq_m_shfe_rb         | bottom | 10 | -0.36%  | 30.00% |
| kq_m_shfe_rb         | top    |  7 | -0.36%  | 42.86% |

---

## 3.B `cn_option_payoffs_all.csv` (79 data rows)

**Columns** (10 total):

| column | dtype |
|---|---|
| symbol | str |
| signal_date | str |
| direction | str |
| rule_id | str |
| underlying_price | float64 |
| contract | str |
| entry_premium | float64 |
| h5_ret | float64 |
| h10_ret | float64 |
| h20_ret | float64 |

Note: **no multi-TF context columns** (no lower_relation / higher_relation /
band) — this CSV is signal+payoff only. Multi-TF buckets cannot be sliced
from this file alone; cross-reference §3.A for the multi-TF cell stats.

**Distribution by product (symbol)**:

| product | n  |
|---------|---:|
| m       | 22 |
| i       | 22 |
| cu      | 20 |
| au      | 15 |

**Distribution by rule_id**:

| rule_id | n  |
|---|---:|
| CN1-top-passthrough | 37 |
| F8-cn-no-boost      | 32 |
| —                   | 10 |

**Distribution by direction**:

| direction | n |
|---|---:|
| bottom | 42 |
| top    | 37 |

**Direction × horizon (raw, no SL)**:

| direction | metric | h5 | h10 | h20 |
|---|---|---:|---:|---:|
| bottom | mean | +25.65% | +37.97% | +35.12% |
| bottom | median | +8.60%  | -8.91%  | -39.06% |
| top    | mean | -21.17% | -34.67% | -42.63% |
| top    | median | -29.31% | -37.56% | -77.60% |

**"No rule fired" cell — all 10 rows verbatim** (verifies +119.5% raw +
contract identity question):

| idx | symbol | signal_date | dir    | rule_id | underlying | contract           | premium | h5_ret  | h10_ret | h20_ret |
|----:|--------|-------------|--------|---------|-----------:|--------------------|--------:|--------:|--------:|--------:|
| 5   | m      | 2023-04-02  | bottom | —       | 3638.00    | DCE.m2307-C-3650   | 89.50   | -47.49% | -56.42% | -63.69% |
| 6   | m      | 2023-04-26  | bottom | —       | 3450.00    | DCE.m2307-C-3450   | 80.50   | +95.65% | +119.88% | -62.73% |
| 7   | m      | 2023-06-01  | bottom | —       | 3398.00    | DCE.m2308-C-3400   | 90.00   | +93.89% | +245.56% | **+640.00%** |
| 9   | m      | 2024-01-07  | bottom | —       | 3157.00    | DCE.m2403-C-3150   | 390.00  | -51.67% | -80.90% | -96.79% |
| 13  | m      | 2025-04-06  | bottom | —       | 3056.00    | DCE.m2507-C-3050   | 38.00   | +48.68% | -7.89%  | -69.74% |
| 15  | m      | 2025-06-05  | bottom | —       | 3010.00    | DCE.m2508-C-3000   | 61.50   | +18.70% | +21.14% | -86.18% |
| 18  | m      | 2025-11-05  | bottom | —       | 3068.00    | DCE.m2601-C-3050   | 63.50   | -6.30%  | -59.06% | -70.08% |
| 20  | m      | 2026-02-08  | bottom | —       | 2729.00    | DCE.m2605-C-2750   | 56.00   | +24.11% | +95.54% | **+507.14%** |
| 21  | m      | 2026-02-26  | bottom | —       | 2833.00    | DCE.m2605-C-2850   | 47.00   | +115.96% | +515.96% | **+122.34%** |
| 44  | au     | 2022-02-10  | bottom | —       | 375.24     | SHFE.au2204C376    | 5.98    | +113.38% | +159.87% | **+374.92%** |

**Composition note**: 9 of 10 are `m` bottoms, 1 is `au` bottom. **All 10 are
bottoms.** Four of 10 have h20 > +100% (m2308 +640%, m2605 +507%, m2605
+122%, au2204 +375%). The other six have h20 between -97% and -63%. So the
+119.5% cell mean **is heavily right-tail driven**.

Calculation check: `mean(-63.69, -62.73, +640, -96.79, -69.74, -86.18, -70.08, +507.14, +122.34, +374.92) / 10` ≈ +119.52%. Confirms report number.

Sub-period concentration:
- 2023 batch (Apr-Jun): 3 trades, 1 winner (+640%)
- 2024 batch: 1 trade, 1 loser
- 2025 batch: 3 trades, 0 winners
- 2026 batch (Feb): 2 trades, both winners (+507, +122)
- au 2022-02-10: 1 trade, +375%

Without the 4 winners, the cell is 6/10 losers averaging ~-75%. The
mega-winners cluster on (m, post-rally bottoms) + 1 au outlier.

**au F8-cn-no-boost cell — all 8 rows verbatim** (verifies +118.6% raw):

| idx | symbol | date | dir | rule_id | underlying | contract | premium | h5_ret | h10_ret | h20_ret |
|----:|--------|------|-----|---------|-----------:|----------|--------:|-------:|--------:|--------:|
| 46  | au | 2022-10-09 | bottom | F8-cn-no-boost | 393.24 | SHFE.au2212C392 | 8.58 | -38.23% | -28.44% | -46.39% |
| 48  | au | 2023-03-05 | bottom | F8-cn-no-boost | 418.44 | SHFE.au2306C416 | 9.74 | +9.65%  | +219.92% | +128.54% |
| 51  | au | 2023-10-19 | bottom | F8-cn-no-boost | 476.68 | SHFE.au2312C480 | 7.14 | -17.93% | -38.94% | -89.92% |
| 52  | au | 2024-07-07 | bottom | F8-cn-no-boost | 560.74 | SHFE.au2410C560 | 15.68 | +14.54% | +1.79%  | -2.17%  |
| 53  | au | 2025-07-17 | bottom | F8-cn-no-boost | 777.02 | SHFE.au2510C776 | 22.28 | -6.91%  | -38.15% | -44.88% |
| 55  | au | 2025-08-26 | bottom | F8-cn-no-boost | 781.16 | SHFE.au2510C784 | 8.94  | +289.49% | +457.05% | **+701.34%** |
| 56  | au | 2025-12-10 | bottom | F8-cn-no-boost | 957.90 | SHFE.au2602C960 | 25.16 | +44.20% | +119.32% | +166.38% |
| 57  | au | 2026-01-11 | bottom | F8-cn-no-boost | 1026.28 | SHFE.au2604C1024 | 50.40 | +7.54% | +166.27% | +135.91% |

Verified: mean h20 = +118.60% (matches report); median +63.19%; hit (h20>0)
= 5/8 = 62.5% (the +50% in the report comes from a different threshold).
Drop-top-2 → remaining 6 trades h20: (-46.39, -89.92, -2.17, -44.88,
+128.54, +166.38) → mean +18.59% (still positive but a third of the original).

**Per-rule × h=20 metrics** (no stop-loss columns in raw CSV; the SL-N
columns in §2.2.3 come from the report's tight-stop simulator and cannot be
re-derived from this CSV alone):

| rule_id | n | mean h20 | median h20 | min | max |
|---|--:|--:|--:|--:|--:|
| CN1-top-passthrough | 37 | -42.63% | -77.60% | (computed inline) | (computed inline) |
| F8-cn-no-boost      | 32 | +8.79%  | (n/a) | (computed inline) | (computed inline) |
| — | 10 | +119.52% | (computed inline) | -96.79% | +640.00% |

---

## 3.C `option_payoffs_topology_b_no_nvda.csv` (79 data rows — US baseline)

**Columns** (19 total — has full multi-TF + topology context, unlike CN file):

```
symbol, topology, date, direction, subtype, level, confidence, rule_id,
rule_weight, lower_relation, lower_tf_level, higher_relation, higher_tf_level,
contract, entry_close, entry_premium, h5_ret, h10_ret, h20_ret
```

`topology` field is "B" for all rows (D + 15m + 1h).

**Distribution by rule_id**:

| rule_id | n  |
|---|---:|
| F8-bottom-weakness-baseline | 38 |
| F1-top-lagging-soft         | 18 |
| —                           | 11 |
| F4-options-asymmetric       |  5 |
| F2-strong-bottom            |  5 |
| F3-candidate-counter-trend  |  2 |

**Distribution by symbol**:

| symbol | n |
|---|--:|
| SPY | 22 |
| IWM | 14 |
| GLD | 11 |
| GDX |  7 |
| DIA |  6 |
| TLT |  5 |
| XLK |  5 |
| XLF |  5 |
| QQQ |  4 |

(NVDA explicitly excluded per filename.)

**Per-rule × h=20 (raw)**:

| rule_id | n | mean | median | hit (h20>0) |
|---|--:|--:|--:|--:|
| F1-top-lagging-soft         | 18 | -69.06% | -86.20% | 5.56% |
| F2-strong-bottom            |  5 |  -4.88% | -56.88% | 40.00% |
| F3-candidate-counter-trend  |  2 | +77.37% | +77.37% | 100.00% |
| F4-options-asymmetric       |  5 | -32.09% | -75.73% | 40.00% |
| **F8-bottom-weakness-baseline** | **38** | **+50.86%** | **+25.92%** | **57.89%** |
| —                           | 11 | -25.56% | -60.55% | 27.27% |

**Direction × h=20**:

| direction | n  | mean h20 | median h20 |
|---|--:|--:|--:|
| bottom | 47 | +37.26% | +14.53% |
| top    | 32 | -42.91% | -73.93% |

**US F8 detail (n=38)** — for the "right tail comparison" Codex needs to
answer (CN F8-au has n=8, mean +118.6%; does the US F8 right tail look
similar in shape?):

| stat | value |
|---|---|
| n | 38 |
| mean h20 | +50.86% |
| median h20 | +25.92% |
| winners (h20>0) | 22 |
| winners' mean h20 | +129.03% |
| p75 | +80.55% |
| min | -99.83% |
| max | +651.19% |

Side-by-side right-tail comparison (h20):

| dataset | n | mean | median | winners avg | p75 |
|---|--:|--:|--:|--:|--:|
| **US F8 baseline** (R3 report rounding: +73.5% with SL-3) | 38 | +50.86% | +25.92% | +129.03% | +80.55% |
| **CN F8-au** | 8 | +118.60% | +63.19% | (5 winners avg) +254.5% | (computed) |

CN F8-au has fewer trades but a heavier right tail (single +701% outlier vs
US's +651% biggest). The R3 packet's "US F8 winners avg +129%, p75 +155%"
appears to come from a different US dataset (full F8 cell including NVDA or
the broader tight-stop sim); the no-nvda baseline above gives p75 +80.55%.

---

# Section 4 — Algorithm & Calibration Context

## 4.1 `instrument_class` (us_equity vs cn_futures)

Engine accepts `instrument_class: Literal["us_equity", "cn_futures"]`. Affects
**two** layers:

**`engine/divergence/direction_gate.py`** — direction-asymmetric confidence
multiplier applied at signal-detection time.

- **us_equity (default)**: penalises top signals via three multiplicative
  tables (subtype, level, gap), then clips to [0, 1]. Bottoms pass through.
  Hard-baked from a 5y SPY-family backtest.
  - `TOP_SUBTYPE_MULT_US = {hidden: 0.0, weakness: 0.7, standard: 1.0}`
  - `TOP_LEVEL_MULT_US = {inter_segment: 0.5, inter_cycle: 0.85, intra_cycle: 1.0}`
  - `TOP_GAP_MULT_US = {False: 1.2, True: 0.5, None: 1.0}`
- **cn_futures**: all multipliers = 1.0 (PASS-THROUGH). Justification at time
  of implementation: 19-symbol single-TF backtest showed CN tops empirically
  positive (+0.65% mean / 55.8% hit / n=400) — US top de-weight was
  over-penalising. **This is the assumption R4-CN-1 now contradicts.**

`gate_signals()` also drops signals whose adjusted confidence falls below the
**watching floor 0.30**. CN: no drops because no de-weight.

**`engine/divergence/downstream_policies.py`** — rule-based weighting applied
after detection + multi-TF enrichment. Outputs `PolicyDecision(weight,
rule_id, monitor_required, reason, strategy_hints)`.

- **us_equity** rules (precedence order, first-match wins):
  1. F2 — `bottom + lower=leading + higher=opposing` → weight 1.20
  2. F3 — `candidate band (0.65 ≤ conf < 0.80) + higher=opposing` → 1.15
  3. F4 — `top + lower=leading + higher=opposing` → 1.0 (options-asymmetric hint)
  4. B1 — `top + higher=opposing` (residual after F4) → 1.30
  5. F1 — `top + lower=lagging` → 0.70 (soft de-weight)
  6. F8 — `bottom + subtype=weakness` → 1.10 (workhorse, all bands)
  7. baseline → 1.0
- **cn_futures** rules (only three can fire):
  1. F8' — `bottom + subtype=weakness` → 1.00, rule_id `F8-cn-no-boost`,
     monitor_required=True. **No boost** because confidence band is anti-monotone
     on CN (watching > confirmed) so the US +0.10 boost would mis-rank.
  2. CN1 — `top` (any) → 1.00, rule_id `CN1-top-passthrough`,
     monitor_required=True. **No de-weight** for the same reason direction_gate
     is bypassed. Emits `direction_gate_calibration_mismatch` strategy hint.
  3. baseline → 1.00 (all non-weakness bottoms = 66 standard + 8 hidden = 74).

Both cn_futures rules emit `_cn_consumer_hints()`: blacklist `j0`/`jm0`,
prefer index futures `IF/IH/IC/IM`.

The CN rule precedence + the fact that multi-TF rules (F2/F3/F4/B1) are listed
in the docstring as "cannot fire — multi-TF context unavailable" mean even
with B-topology multi-TF context enriched on the signal, the dispatched
policy ignores it. This is why R4-CN-1's "what-if" table is informational —
the deployed policy doesn't read those cells.

## 4.2 B-Topology vs A-Topology

- **A-topology (default for stocks)**: primary=D, lower=1h, higher=W
- **B-topology (opt-in, recommended for options)**: primary=D, lower=15m, higher=1h

Both are `ContextTopology` instances. Selected via
`build_analysis_output(..., context_topology="A" | "B")`. F1-F8 rule weights
are calibrated on A-topology US 5y data; B-topology re-uses them with the
same semantic interpretation. R4 backtests use B-topology on CN.

## 4.3 Divergence detection vocabulary

A `DivergenceSignal` has:

- `direction`: `"top" | "bottom"`
- `subtype`: `"standard" | "weakness" | "hidden"`
  - **standard**: classic price-vs-MACD divergence (price HH/LL, MACD lower
    high / higher low)
  - **weakness**: same direction but smaller magnitude divergence (lower
    confidence than standard, but empirically the strongest predictor under
    F8)
  - **hidden**: continuation signal (price LL, MACD HL = bullish hidden;
    bearish hidden mirrored). Empirically very weak; US gate hard-drops
    `hidden` tops.
- `level`: `"intra_cycle" | "inter_cycle" | "inter_segment"`
  - Intra-cycle = heap-internal (same MACD energy bar group)
  - Inter-cycle = across two adjacent heaps
  - Inter-segment = across cycle boundaries (larger structure)
- `is_continuous_gap`: boolean — for intra_cycle only, distinguishes
  consecutive heaps from gapped heaps.
- `confidence`: float ∈ [0, 1]. Bands per `conf_band()`:
  - dormant <0.30 / watching <0.50 / forming <0.65 / candidate <0.80 / confirmed ≥0.80.

## 4.4 Multi-TF context vocabulary

From `engine/divergence/multi_tf_context.py`:

- **`lower_relation`** ∈ `{"lagging", "leading", "pivoting"}`
  - Maps `(direction, lower-TF trend_side)`:
  - bottom + bullish lower = lagging (lower TF already turned bullish)
  - bottom + bearish lower = leading (lower TF still bearish — signal preempts)
  - top + bearish lower = lagging; top + bullish lower = leading; mixed/neutral = pivoting.
- **`higher_relation`** ∈ `{"supporting", "opposing", "neutral"}`
  - bottom + bullish higher = supporting; bottom + bearish higher = opposing.
  - top + bearish higher = supporting; top + bullish higher = opposing.

The R4-CN-1 §3.1 "spotlight" bucket — `top + higher_opposing` — is `top` +
**higher TF still bullish** = counter-trend top divergence. The 1h is fighting
the daily top signal; empirically this is when CN top signals "actually work"
(n=20, 80% hit, +2.51%).

Also note: `lower_relation` is duplicated as `relation` (back-compat key) by
`enrich_with_lower_tf`. Old aggregators reading `relation` continue to work.

`enrich_with_higher_tf` for daily/1h with `grace_minutes=0` is leak-free.
`enrich_with_lower_tf` uses `intraday_grace_minutes=30` by default, which
includes a 60min bar overlapping ~30min after the daily timestamp — known
mild look-ahead, validated as within sampling noise.

## 4.5 What the CN policy currently does on a B-topology signal

Even though the signal carries `multi_tf_context = {lower_relation: ...,
higher_relation: ...}` after enrichment, `_apply_cn_futures` **never reads
either field**. The policy only checks `direction` and `subtype`. So:

- The B-topology "what-if" buckets in R4-CN-1 §3.4 are **observational** —
  they predict what would happen if the engine routed CN signals through
  rule definitions similar to the US ones.
- The fingerprint in §3.A shows **all 103 top signals** receive rule_id
  `CN1-top-passthrough` (no sub-bucketing by higher_relation).
- This is the central tension R4 is asking Codex about: should the CN policy
  start consuming the multi-TF context now (e.g. add a CN-B1 rule), or wait
  for more 15min data?

---

# Section 5 — Expected Output Format

Produce a markdown document in this structure (same as R1-R3 verdicts):

```markdown
# Codex Round 4 Verification

## Headline reversals
- [CN top direction] survives ✅ / collapses ❌ / edge ⚠️
  (cite the relevant fingerprint stats + explain regime vs filter attribution)

## Per-finding verdicts
- F8-cn product bimodality (au +118.6% vs cu/i -14 to -23%): ...
- CN-B1 candidate (top + higher_opposing, n=20, +2.51%): ...
- "no rule fired" cell (+119.5% n=10, 9× m bottoms + 1 au): ...
- top + higher_supporting de-weight (proposed weight 0.80, n=74, -1.59%): ...
- F8 anti-monotone confidence persistence on B-topology: ...
- F1-equiv on CN being +0.09% not negative: ...

## Recommended policy changes (if any)
- cn_futures top direction: weight = ? (a / b / c / d from packet §1.1)
- F8 product-subdivision: yes / no / hint-only
- CN-B1 adoption: now / wait-for-n=50 / split into sub-rules
- "no rule fired" cell handling: subtract / observe / dismiss

## Methodology flags
- Small samples (per-bucket n caveats)
- Regime confound (2024-2026 only)
- Multi-TF leak (intraday_grace_minutes=30 on lower TF)
- Daily-close premium (SL columns are upper bound)
- Continuous-main rollover artefacts (TqSdk KQ.m@)
- Bonferroni / BH-FDR posture
```

---

# Section 6 — Codex Self-Audit Checklist

Before finalising, verify you addressed each item below. The packet's R4
verification asks have been broken out so nothing is silently skipped.

**R4-CN-1 verification items**

- [ ] CN top sign-flip: regime vs multi-TF vs sample-composition attribution
      (use §2.1.4 group rollup + §3.A per-symbol table)
- [ ] Per-bucket significance under Bonferroni / BH-FDR α=0.05
      (multi-TF cells: 19 products × 2 dirs × 3 higher_relation × 3 lower_relation
       has many cells; flag which survive)
- [ ] F2-equiv (n=12, +6.73%) — symbol HHI, bootstrap CI, drop-top-2
- [ ] F4-equiv (n=10, +3.40%) — same checks
- [ ] CN-B1 (n=20, 80% hit, +2.51%) — same checks; recommend adopt-now vs wait
- [ ] F8 (n=56, +3.81%) — confirm pattern, comment on band anti-monotonicity
- [ ] `top + higher_supporting` (n=74, -1.59%, 43% hit) — adoption viable?
- [ ] F8 × confidence band anti-monotone: persists on B-topology? (§3.A: yes,
      forming +8.07% > confirmed +2.59%)

**R4-CN-2 verification items**

- [ ] au F8 (n=8, +118.6%): genuine product edge vs gold-rally artifact?
      drop-top-2 → +18.59% (still positive); date-stratify (2022/23 mixed,
      2025-26 dominated by winners)
- [ ] au F8 under Bonferroni across 4 products × 5+ rule cells: survives?
- [ ] "No rule fired" +119.5% (n=10): row-level breakdown (§3.B verbatim
      table). Decide between
      (a) F8/CN1 fusion gates out valid bottom signal,
      (b) selection artifact / lucky m bottoms,
      (c) coincidence from product-month overlap.
- [ ] CN top stop-hit rate vs US F1's 72-94%
- [ ] CN F8 right-tail shape vs US F8 (§3.C: US F8 p75=+80.55%, winners
      avg +129%; CN F8-au winners avg ≈ +254%, smaller n)

**Cross-cutting decisions**

- [ ] Recommend `cn_futures` top weight: (a) 0.70, (b) 0.50-0.60, (c) 1.00,
      (d) sub-bucket-differentiated
- [ ] F8 product-class subdivision: subdivide / leave uniform / hint only
- [ ] CN-B1 promotion: adopt with weight 1.20 now or wait for n≥50
- [ ] "No rule fired" cell handling: subtract from fusion / observe / dismiss

**Sanity checks before delivery**

- [ ] Every quoted statistic cites a §3 fingerprint table or §2 report table
- [ ] Sample sizes < 50 explicitly flagged as monitor-only
- [ ] Distinguished "what-if" buckets (§2.1.3 informational) from deployed
      policy outcomes (§3.A rule_id distribution)
- [ ] Acknowledged that `_apply_cn_futures` ignores multi-TF context fields
      even when they are present on the signal (§4.5)
- [ ] Output saved as `doc/codex-verdict-round4-for-claude.md` (or analogous)
