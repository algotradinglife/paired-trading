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
