# Internal Round-4 Pre-Review (2026-05-24)

> **INTERNAL CLAUDE PRE-REVIEW — NOT CODEX.**
> This document is produced by the project-internal Claude session against
> the same R4 packet that will be sent to external Codex. It is not a
> substitute for external review:
> - Codex = independent second opinion, decides production policy.
> - This document = sanity floor. Every number Codex receives has been
>   replicated here against the raw CSVs so that Codex can directly
>   `diff` against my numbers and concentrate review on interpretation
>   rather than re-running statistics.
>
> Where I disagree with the packet, I say so explicitly. Where the
> sample is too thin to conclude, I refuse to grade. Codex remains the
> tie-breaker on weight changes.
>
> Reproducer: `/tmp/r4_pre_review.py` (full log: `/tmp/r4_pre_review.out`).
> All bootstraps n_boot=5000, RNG seed 20260524, percentile method.

---

## Headline verdicts

| Claim from packet | Status | Key number |
|---|---|---|
| CN top direction has reversed to **negative** | **collapses to "edge"** | top mean −1.06% but two-sided p=0.149, 95% CI [−2.61%, +0.40%] — **CI crosses zero**. Drop-best-2 deepens to −1.35%, drop-worst-2 lifts to −0.48%. Sign is suggestive, not significant. |
| CN bottom EV roughly doubles | **survives** | bot mean +2.58%, CI [+1.15%, +4.21%], p=0.0016, hit 60% |
| F8 (bot+weakness) is the workhorse | **survives** | n=56, mean +3.81%, CI [+1.77%, +6.36%], p=0.0026 — only candidate that survives both Bonferroni and BH-FDR alongside F4-eq |
| `top + higher=opposing` (CN-B1) at +2.51% n=20 is a "clean B1 analogue" | **edge — does NOT survive corrections** | two-sided p=0.115, 95% CI [−1.11%, +5.35%]. Hit 80% looks great but CI crosses zero. Bonferroni/BH-FDR both reject. |
| `top + higher=supporting` n=74 / −1.59% is the largest negative-EV cell | **edge** | CI [−3.35%, +0.07%], two-sided p=0.066, one-sided p=0.040. **CI just barely touches zero from below**. Real, but tiny effect size; do not over-weight. |
| F8 confidence band remains anti-monotone | **does NOT hold cleanly in B-topology data** | watching +1.65% / forming +9.14% / candidate +5.42% / **confirmed +2.59%**. confirmed is the lowest non-watching cell, but **watching itself (+1.65%) is below confirmed**. Pattern is humped (peak at "forming"), not strictly anti-monotone. Packet/source report over-states this. |
| au F8 +118.6% is a genuine product edge | **does NOT survive outlier removal** | n=8, 95% CI [−13.9%, +305.3%]. **One contract (SHFE.au2510C784, +701%) drives 74% of total sum**. Drop-top-2 collapses mean to +13.5%. Pre-2025 mean is −2.5% (n=4). |
| "no rule fired" cell at +119.5% n=10 contradicts F8 design | **does NOT survive contract-overlap & drop-2** | n=10. **m2605 expiry alone (n=2) means +315%**. Drop-top-2 collapses mean to +6.0%. Median is **−63%**. 6 of 10 trades return < −60%; the +119% mean is 100% right-tail. |
| CN top option pattern mirrors US F1 | **survives** | CN top stop-hit (≥3% loss within window) = 94.6% (n=37); US F1 = 100% (n=18). Same "mechanical recovery, not directional alpha" pattern. |

## Methodology probes (packet didn't ask)

- **Multi-TF context coverage**: 100% of 233 signals have non-null
  `lower_relation` and `higher_relation`. No silent fallback. ✅
- **Symbol coverage**: all 19 CN futures have both bottoms and tops
  (zero missing direction cells). ✅
- **Sample HHI**: top sample HHI by symbol = 0.064, bot HHI = 0.060.
  Well below 0.30 — no single-symbol dominance. ✅
- **Year distribution**: 2024/2025/2026 = 62/131/36 signals. 2025 is
  56% of all signals — single-year regime risk is real.
- **Window-overlap probe**: when single-TF baseline (n=4,116) is
  restricted to the same 2023-11-12 → 2026-04-21 window, single-TF
  shows **top mean +0.37%** (n=63, CI crosses zero), **bot mean
  +2.09%** (n=167). So:
  - The bottom-strengthening is **mostly window/regime**, not multi-TF
    filter (single-TF in same window already shows +2.09%).
  - The top sign-flip is **partly window** (+0.65% over 21y → +0.37%
    in 2023-26 window, also CI-crossing) and partly multi-TF
    filter (−1.06% with B-topology vs +0.37% same-window single-TF).
  - **The single-TF baseline and the multi-TF backtest are NOT
    sampled from the same symbol set** (overlap ∩ same symbols = 0)
    — single-TF aggregate uses different continuous-main naming. So
    the comparison is approximate, not strict.

---

## R4-CN-1 verdicts (B-topology)

### CN top direction reversal

| metric | value |
|---|---|
| top n | 103 |
| top mean (h=20) | −1.0595% |
| top 95% CI (bootstrap, n=5000) | [−2.6058%, +0.3988%] |
| two-sided p (H0 mean=0) | **0.1492** |
| hit rate | 48.5% |
| median | −0.19% |
| drop-best-2 mean | −1.35% (sign holds) |
| drop-worst-2 mean | −0.49% (sign weakens) |
| sample HHI by symbol | 0.0640 (diversified) |

**Verdict**: the sign-flip narrative is plausible but **statistically
not significant at α=0.05**. The 95% CI crosses zero. The packet's
phrasing "top direction has reversed to NEGATIVE" over-states the
evidence. Honest framing is "top direction is now non-distinguishable
from zero and trending negative, vs prior single-TF marginally positive
(also non-significant in the matched window)."

Bottom strengthening, by contrast, is solid: bot mean +2.58%, p=0.0016,
hit 60%, CI well above zero.

**Per-symbol top contribution**: most negative contributors are
`kq_m_dce_i` (sum −0.35), `kq_m_cffex_im` (−0.31), `kq_m_shfe_ag`
(n=2, −0.31), `kq_m_ine_sc` (n=2, −0.25). The `ag` and `sc` cells
have n=2 each and are correctly flagged as outliers by the source
report. Positive contributors: `kq_m_dce_p` (+0.19), `kq_m_czce_cf`
(+0.18), `kq_m_dce_jm` (+0.18). The negative sign is broad-based,
not from a single symbol — but it's also not strong.

**Decomposition of the apparent reversal** (best-effort, can't fully
separate due to non-overlapping symbol sets):

1. **Window/regime**: single-TF in same 2023-11-12 → 2026-04-21
   window shows top mean +0.37% (down from +0.65% over 21y, but
   not negative). Window explains roughly half the magnitude.
2. **Multi-TF filter**: same window comparison gives B-topology
   −1.06% vs single-TF +0.37% — a ~1.4pp downward shift from
   adding multi-TF context. Plausible but not big.
3. **Symbol set**: single-TF aggregate uses different continuous-main
   naming (overlap = 0 by exact match), so this isn't a clean
   like-for-like. Source report claims index-futures dominate the
   multi-TF window; my data: index futures = 34 of 103 tops = 33%
   share, not 44% as the packet states.

### Candidate F-rule significance

| candidate | n | mean (h=20) | 95% CI | two-sided p | drop-top-2 mean | Bonferroni (α=.01) | BH-FDR (α=.05) |
|---|---:|---:|---|---:|---:|---|---|
| **F8-eq** (bot+weakness) | 56 | +3.81% | [+1.77%, +6.36%] | 0.0026 | +2.33% | ✅ | ✅ |
| **F4-eq** (top+leading+opposing) | 10 | +3.40% | [+1.11%, +5.66%] | 0.0024 | +2.34% | ✅ | ✅ |
| F2-eq (bot+leading+opposing) | 12 | +6.73% | [+0.01%, +13.87%] | 0.057 | +2.86% | ✗ | ✗ |
| CN-B1 (top+higher_opposing) | 20 | +2.51% | [−1.11%, +5.35%] | 0.115 | +1.56% | ✗ | ✗ |
| top+higher_supporting | 74 | −1.59% | [−3.35%, +0.07%] | 0.066 | −1.94% | ✗ | ✗ |

**Verdict**:

- **F8-eq** is the only large-sample (n=56) winner. Robust to
  drop-top-2, passes both multiple-testing corrections, HHI 0.091.
  Production-grade.
- **F4-eq** passes corrections but n=10 is small and HHI 0.140. The
  surprising thing is F4-eq is *positive on tops* (+3.40%, 80% hit).
  Worth a monitor flag, not production weight — multi-testing
  inflation across more rule families would weaken this.
- **F2-eq**: drop-top-2 cuts mean from +6.73% to +2.86%, and only
  one outlier away from non-significance. Insufficient evidence.
- **CN-B1**: the headline claim "n=20, 80% hit, +2.51%" is correct
  but **statistically not actionable** — CI [−1.11%, +5.35%]
  crosses zero, p=0.115. Hit-rate is impressive, but mean magnitude
  is small and noisy. Source report itself says n=20 is below
  production bar — this is correct.
- **top+higher_supporting**: marginal. CI just touches zero from
  below. Drop-top-2 deepens the effect to −1.94%, which is good
  consistency, but the magnitude is small. Per-year breakdown shows
  consistency: 2024 −0.92%, 2025 −0.85%, 2026 −4.94% (n=13). Real
  but not large.

### F8 confidence-band monotonicity

Source report and packet both claim F8 is anti-monotone (lower bands
beat higher). My data:

| band | n | mean (h=20) | 95% CI | hit |
|---|---:|---:|---|---:|
| watching | 8 | +1.65% | [−0.60%, +3.60%] | 87.5% |
| forming | 6 | +9.14% | [−0.07%, +23.98%] | 83.3% |
| candidate | 13 | +5.42% | [+0.75%, +12.44%] | 76.9% |
| confirmed | 29 | +2.59% | [+0.68%, +4.54%] | 72.4% |

This is **humped, not monotone**. Peak at "forming" (n=6), then
declines through candidate → confirmed. But watching is itself
lower than confirmed. Strict "anti-monotone" claim does not hold.

What does hold: **confirmed is the lowest non-watching mean** —
so a "don't boost confirmed F8" rule is justified by the data,
just don't call it anti-monotone. The packet/source-report
phrasing is misleading; the policy implication (no confidence
boost on F8-CN) survives, but for slightly different reasons
than stated.

Also notable: F8 by higher_relation shows F8 fires **hardest on
higher=supporting** (n=44 +4.15% / hit 79.6%), not on
higher=opposing (n=10 +2.64%). This is *opposite* to the
narrative that F8+opposing is the high-EV bucket — for CN F8,
higher=supporting is where the size and edge both are. Worth
flagging in policy notes.

---

## R4-CN-2 verdicts (options)

### au F8 +118.6% reality check

| metric | value |
|---|---|
| n | 8 |
| raw mean h=20 | +118.6% |
| 95% CI (bootstrap) | [−13.9%, +305.3%] |
| median | +63.2% |
| hit_rate | 50.0% |
| drop-top-2 mean | +13.5% |
| **top-1 contribution** | **+701.3% single trade = 73.9% of total sum** |
| pre-2025 mean (n=4) | **−2.5%** |
| 2025+ mean (n=4) | +239.7% |

**Verdict**: insufficient evidence that this is a product edge.
The mean is dominated by one trade (SHFE.au2510C784, 2025-08-26
signal, +701%). Remove it and mean drops to +35% (n=7). Drop top
2 → +13.5%. The 4 pre-2025 signals collectively returned −2.5%.
This looks like a 2025 gold-rally artifact more than a structural
product edge.

50% hit rate on n=8 is decent but median +63% is still mostly the
tail. With n=8, no statistical claim is supportable — **mark as
INSUFFICIENT EVIDENCE / MONITOR, do not productize**.

Note for Codex: source report's `+118.6% raw` is correct as a
number, but presenting it as evidence of "product edge" without
disclosing the 74% single-trade dependence is the problem.

### "No rule fired" +119.5% cell (n=10)

The 10 trades:

| symbol | date | contract | h20_ret |
|---|---|---|---:|
| m | 2023-04-02 | DCE.m2307-C-3650 | −63.7% |
| m | 2023-04-26 | DCE.m2307-C-3450 | −62.7% |
| m | 2023-06-01 | DCE.m2308-C-3400 | **+640.0%** |
| m | 2024-01-07 | DCE.m2403-C-3150 | −96.8% |
| m | 2025-04-06 | DCE.m2507-C-3050 | −69.7% |
| m | 2025-06-05 | DCE.m2508-C-3000 | −86.2% |
| m | 2025-11-05 | DCE.m2601-C-3050 | −70.1% |
| m | 2026-02-08 | DCE.m2605-C-2750 | **+507.1%** |
| m | 2026-02-26 | DCE.m2605-C-2850 | **+122.3%** |
| au | 2022-02-10 | SHFE.au2204C376 | **+374.9%** |

- 9 of 10 are `m` (soymeal), 1 is `au`.
- **m2605 expiry has 2 signals (2026-02-08, 2026-02-26)** — same
  contract month, both winners. n=2 in this expiry alone =
  +315%. **These are NOT independent observations** — they
  reference the same soymeal rally window.
- m2307 expiry has 2 losers (same loser-month).
- **Median = −63.2%**. **6 of 10 trades < −60% loss**.
- Drop-top-2 collapses mean to +6.0%.
- 95% CI [−33%, +295%].

**Verdict**: **packet's interpretation (b) "selection artifact" is
correct**. This cell is not evidence that F8/CN1 fusion adds
noise — it's a textbook small-sample, right-tail-dominated
artifact with at-best one independent winning event (m2605
rally) double-counted. No policy implication.

Recommendation: **do not subtract** from F8/CN1 weights based on
this finding. The signal is noise.

### CN top option vs US F1 pattern

| metric | CN top all (n=37) | US F1 (US top+lagging, n=18) |
|---|---:|---:|
| raw h=20 mean | −42.6% | −69.1% |
| stop-hit rate ≥3% (any of h5/h10/h20) | 94.6% | 100.0% |
| stop-hit rate ≥5% | 94.6% | 100.0% |
| stop-hit rate ≥10% | 91.9% | 100.0% |

**Verdict**: pattern matches. Both are "almost everything triggers
a small stop, occasional uncapped winner saves the EV." Source
report's framing as "mechanical recovery, not directional alpha"
is correct.

**Caveat** (source report flags this): stop-hit is computed on
daily-close minimums, which **underestimates** intraday stop-hit
because it can't see the path. The reported SL columns therefore
**overstate** real-world tight-stop EV. Codex should treat these
as upper bounds.

### CN F8 vs US F8 distribution shape

| dataset | n | mean | median | winners n | winners avg | p75 | >+60% | >+100% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CN F8 (4 products) | 32 | +8.8% | −30.6% | 8 | +184.8% | +5.7% | 18.8% | 18.8% |
| CN F8 au only | 8 | +118.6% | +63.2% | 4 | +283.0% | +143.5% | 50.0% | 50.0% |
| US F8 | 38 | +50.9% | +25.9% | 22 | +129.0% | +80.6% | 31.6% | 18.4% |

**Verdict**:
- US F8 is fundamentally different shape: 58% winners (vs CN 25%),
  median +26% (vs CN −31%). US F8 wins because most trades win.
- CN F8 wins (when it wins) because of fatter right-tail: when
  winners hit, they average +185% vs US +129%. But 75% of CN F8
  trades are losers.
- au F8 is the only CN product where shape resembles US F8 — but
  on n=8.
- **Implication**: F8 does NOT generalize to CN as a uniform rule.
  US F8 captures something signal-like (bottom+weakness → continuation);
  CN F8 captures something gamma-like (bottom+weakness in a strong
  trending product → fat right tail). They are different mechanisms
  rather than the same mechanism on different markets.

Per-product CN F8 (h=20 raw):

| product | n | mean | hit |
|---|---:|---:|---:|
| au | 8 | +118.6% | 50% |
| cu | 9 | −14.5% | 22% |
| i | 12 | −23.5% | 17% |
| m | 3 | −85.4% | 0% |

m F8 is **disastrous** (0/3 winners, mean −85%). cu/i are slightly
negative. Only au is positive — and that's primarily one trade.
**Uniform F8-cn-no-boost (weight 1.0) is mis-specified given this
spread**, but the right correction is more conservative than the
packet implies: not a product-class boost, but a product-class
**blacklist** for m on the option side.

---

## Cross-cutting policy recommendations

These are my **internal** recommendations for what to send Codex. They
are conservative; Codex is the tie-breaker.

### 1. cn_futures top direction weight

Source report tentatively suggests 0.85-0.90 mild de-weight. My data:

- top mean −1.06%, but **CI crosses zero**, p=0.149.
- Sub-bucket analysis shows the effect lives in `top + higher_supporting`
  (n=74, −1.59%, p=0.066) — and the bucket-specific finding is the
  honest one. Pooled top de-weight is overkill given marginal
  significance.

**Recommend**: option **(d) differentiated by sub-bucket**.
- `top + higher_supporting`: weight 0.85 (n=74, marginal effect,
  drop-top-2 robust). NOT 0.70-0.80 — effect size too small.
- `top + higher_opposing` (CN-B1): keep at 1.00 with MONITOR flag.
  n=20, hit 80% looks great but CI crosses zero. Do NOT promote
  to 1.20 yet. Wait for n≥50 as source report itself recommends.
- All other tops: keep at 1.00.

Pooled passthrough (option a or b) would over-apply the deweight
to buckets where the data does not support it.

### 2. F8 product subdivision

au F8 +118% is one-trade-dominated. m F8 −85% (n=3) is closer to
production-relevant because every trade in n=3 was a loser.

**Recommend**:
- Do NOT split F8 into per-product weights based on n=8/9/12/3
  cells. Sample is too thin per product.
- DO add a **product blacklist for option-side F8** on `m` (n=3,
  0/3 winners, mean −85%). Use `strategy_hints` to suggest
  "skip F8 option on m"; don't change the underlying signal weight.
- Leave futures-side F8 weight at 1.0 (it's working: +3.81% on
  n=56 in B-topology backtest, BH-FDR pass).
- Surface au F8 as a **monitored opportunity** in
  `strategy_hints` (not a rule), pending n≥20 for au.

### 3. CN-B1 promotion

Source report self-recommends "monitor, re-fit at n≥50". I agree.
n=20 / hit 80% / CI [−1.1%, +5.3%] is not adequate for a 1.20
weight bump. The hit-rate is impressive but the mean has very
wide CI.

**Recommend**: keep CN1-top-passthrough behavior, add a
`spotlight_candidate` tag in output schema noting
`top+higher_opposing` saw 80% hit on n=20 sample. No weight
change.

### 4. "No rule fired" cell — policy implication

Packet asks whether this cell suggests F8/CN1 fusion is *subtracting
signal*. **Verdict (b): selection artifact**. n=10 with median −63%
and one m2605-expiry-driven outlier cluster. Drop-top-2 → +6%.

**Recommend**: **no policy change**. Do NOT subtract from F8/CN1
weights. The +119.5% is a distributional shape, not a signal —
exactly the kind of small-n right-tail event that should not drive
calibration.

---

## Methodology flags for Codex

1. **Bootstrap CIs on n≤20 cells are very wide** — every spotlight
   bucket (CN-B1, F2-eq, F4-eq, au F8, "no rule fired") has CI
   that either crosses zero or is so wide as to be uninformative.
   The source report's mean numbers are correct but the
   uncertainty around them is severe.

2. **Outlier dominance not disclosed**: au F8 (1 trade = 74% of
   sum), "no rule fired" (m2605 = +315% on n=2), m F8 (n=3
   all losers). The source reports show means but not the
   contribution structure.

3. **Window/symbol decomposition is approximate**: single-TF
   and multi-TF backtests use different continuous-main symbol
   naming (intersect = 0 on exact match). The "regime vs filter
   vs composition" attribution in the source report (60-70% / 30-40%)
   is not rigorously decomposable from the data we have.

4. **F8 confidence-band claim is overstated**: humped at
   "forming", not strictly anti-monotone. Policy recommendation
   (no confidence boost) still defensible, but for different
   reason. Codex should not endorse the anti-monotone framing as-is.

5. **Daily-close-only stop simulation** is a known upper bound
   (source report flags). All SL-N% lifts in the option payoff
   tables overstate realistic EV. Codex should not endorse SL-3%
   numbers as actionable.

6. **Index futures share**: source report says 44% of multi-TF
   signals are index futures; actual = 35 of 233 = 15%
   (bottoms = 36/130 = 28%; tops = 34/103 = 33%). Either the
   share figure is wrong or there's a definitional mismatch.
   Worth verifying.

7. **2025 dominates the sample**: 131 of 233 signals are 2025.
   Any "improvement vs prior 21y baseline" is heavily a 2025
   regime read. Year-stratified results (F8: 2024 +2.1%, 2025
   +4.2%, 2026 +5.7%; top+supporting: 2024 −0.9%, 2025 −0.9%,
   2026 −4.9%) suggest 2026 is moving the direction even more,
   but n=10-13 per year makes that fragile.

---

## What to send Codex

Codex's review should focus on:

1. **Whether top direction marginal significance (p=0.149,
   CI crosses zero) justifies any weight change at all** —
   I lean "no, except in `higher_supporting` sub-bucket". Codex
   should rule on whether the sub-bucket evidence (p=0.066) is
   strong enough.

2. **Whether the F8 anti-monotone framing should be retracted**
   or just rephrased. Data does not support strict monotonicity.

3. **Whether to formalize an option-side `m` blacklist for F8**
   given n=3 all losers, or leave as a `strategy_hint`.

4. **Whether to disclose the 74% single-trade dependence on au F8**
   in any production-facing material; my view is yes,
   prominently.

The remaining packet questions (CN-B1 promotion, "no rule fired"
mystery) have unambiguous "wait for more data" / "selection
artifact" answers in the numbers above, and don't really require
Codex's judgment.

---

## Reproducibility

- Script: `/tmp/r4_pre_review.py`
- Full output log: `/tmp/r4_pre_review.out`
- All bootstraps use `np.random.default_rng(20260524)`, n_boot=5000,
  percentile method. BH-FDR implemented as standard step-up at α=0.05.
- Inputs:
  - `src/data/review/cn_b_topology_signals_all.csv` (699 rows, 233
    signals × 3 horizons, 19 symbols, multi-TF context 100% non-null)
  - `src/data/review/cn_option_payoffs_all.csv` (79 rows, 4 products)
  - `src/data/review/option_payoffs_topology_b_no_nvda.csv` (79 rows,
    US baseline)
  - `src/data/review/cn_futures_signals_aggregate.csv` (4,116 rows,
    21y single-TF baseline)

Codex can rerun any single cell from the script blocks; bootstrap
seed is fixed so numbers should match to last decimal.
