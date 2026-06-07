# cn_futures Policy — Full OOS Validation

**Date:** 2026-05-24  
**Scope:** all rules in `engine/divergence/downstream_policies._apply_cn_futures`  
**Data:** `src/data/review/cn_b_topology_signals_all.csv` h=20, 2023-11-12 → 2026-04-21  
**Bootstrap:** 5000 resamples, numpy default_rng(42)  
**Pre-registered min test n:** 15  

## Pre-registered judgment criteria (per rule claim)

**claim=negative** (de-weight rules, e.g. CN-top-supp-fade):
- STRONG CONFIRM: test mean ∈ [-3.0%, -0.5%] AND CI upper ≤ +0.5%
- CONFIRM: test mean < 0 AND CI upper ≤ +0.5%
- REJECT: test mean > 0, OR CI upper ≥ +1.5%

**claim=positive** (boost/workhorse rules, e.g. F8-cn-no-boost):
- STRONG CONFIRM: test mean ∈ [+0.5%, +6.0%] AND CI lower ≥ -0.5%
- CONFIRM: test mean > 0 AND CI lower ≥ -0.5%
- REJECT: test mean < 0, OR CI lower ≤ -1.5%

**claim=ambiguous** (pass-through, e.g. CN1-top-passthrough):
- CONFIRM: test CI crosses zero (pass-through justified)
- UPGRADE-DEWEIGHT: test CI entirely negative
- UPGRADE-BOOST: test CI entirely positive

**INSUFFICIENT** (any claim): test n < 15 → defer

## Splits (same date axis across all rules)
- **S1 50/50 by time**: cutoff 2025-01-30
- **S2 40/60 by time**: cutoff 2024-11-02
- **S3 last 12mo as test**: cutoff 2025-04-21

---

## CN-top-supp-fade  (claim: negative, current weight 0.8)

**Description:** top + higher_relation=supporting (de-weight 0.80)  
**R4 in-sample:** n=74, mean -1.59%, CI [-3.40%, +0.02%]  

### Full-sample sanity check (replication of R4)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 74 | -1.59% | -0.75% | 43% | [-3.38%, +0.01%] |

### S1 50/50 by time  (cutoff 2025-01-30)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 22 | -0.99% | -1.10% | 45% | [-5.00%, +2.22%] |
| Test | 52 | -1.84% | -0.46% | 42% | [-3.77%, -0.04%] |

**Verdict:** **STRONG CONFIRM** (mean -1.84% in [-3.0, -0.5], CI upper -0.04% ≤ +0.5%)

### S2 40/60 by time  (cutoff 2024-11-02)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 12 | -3.09% | -1.28% | 42% | [-9.64%, +2.31%] |
| Test | 62 | -1.30% | -0.46% | 44% | [-2.96%, +0.26%] |

**Verdict:** **STRONG CONFIRM** (mean -1.30% in [-3.0, -0.5], CI upper +0.26% ≤ +0.5%)

### S3 last 12mo as test  (cutoff 2025-04-21)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 34 | -0.63% | +1.49% | 53% | [-3.49%, +1.75%] |
| Test | 40 | -2.41% | -1.30% | 35% | [-4.72%, -0.34%] |

**Verdict:** **STRONG CONFIRM** (mean -2.41% in [-3.0, -0.5], CI upper -0.34% ≤ +0.5%)

**Rule-level verdict: CONFIRM (3/3 splits)** → keep weight 0.8

---

## F8-cn-no-boost  (claim: positive, current weight 1.0)

**Description:** bottom + subtype=weakness (workhorse, pass-through 1.00)  
**R4 in-sample:** n=56, mean +3.81%, CI [+1.76%, +6.22%] (survives Bonferroni)  

### Full-sample sanity check (replication of R4)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 56 | +3.81% | +1.56% | 77% | [+1.75%, +6.34%] |

### S1 50/50 by time  (cutoff 2025-01-30)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 16 | +1.69% | +1.93% | 69% | [-0.47%, +3.81%] |
| Test | 40 | +4.66% | +1.56% | 80% | [+1.95%, +8.05%] |

**Verdict:** **STRONG CONFIRM** (mean +4.66% in [0.5, 6.0], CI lower +1.95% ≥ -0.5%)

### S2 40/60 by time  (cutoff 2024-11-02)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 11 | +1.79% | +0.71% | 64% | [-1.16%, +4.62%] |
| Test | 45 | +4.31% | +1.61% | 80% | [+1.85%, +7.41%] |

**Verdict:** **STRONG CONFIRM** (mean +4.31% in [0.5, 6.0], CI lower +1.85% ≥ -0.5%)

### S3 last 12mo as test  (cutoff 2025-04-21)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 23 | +1.37% | +0.80% | 65% | [-0.29%, +2.99%] |
| Test | 33 | +5.51% | +1.62% | 85% | [+2.30%, +9.67%] |

**Verdict:** **STRONG CONFIRM** (mean +5.51% in [0.5, 6.0], CI lower +2.30% ≥ -0.5%)

**Rule-level verdict: CONFIRM (3/3 splits)** → keep weight 1.0

---

## CN1-top-passthrough  (claim: ambiguous, current weight 1.0)

**Description:** top residual after supp-fade (pass-through 1.00)  
**R4 in-sample:** pooled top: n=103, mean -1.06%, CI [-2.51%, +0.40%] (crosses zero)  

### Full-sample sanity check (replication of R4)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 29 | +0.29% | +1.38% | 62% | [-2.83%, +3.08%] |

### S1 50/50 by time  (cutoff 2025-01-30)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 7 | -3.02% | +0.02% | 57% | [-10.35%, +3.13%] |
| Test | 22 | +1.34% | +2.04% | 64% | [-2.08%, +4.19%] |

**Verdict:** **CONFIRM** (CI [-2.08%, +4.19%] crosses zero — pass-through justified)

### S2 40/60 by time  (cutoff 2024-11-02)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 4 | -6.92% | -6.90% | 25% | [-16.92%, +3.08%] |
| Test | 25 | +1.44% | +2.42% | 68% | [-1.46%, +4.08%] |

**Verdict:** **CONFIRM** (CI [-1.46%, +4.08%] crosses zero — pass-through justified)

### S3 last 12mo as test  (cutoff 2025-04-21)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 15 | +1.13% | +2.42% | 67% | [-3.45%, +5.10%] |
| Test | 14 | -0.61% | +0.90% | 57% | [-5.34%, +2.98%] |

**Verdict:** **INSUFFICIENT** (n=14 < 15)

**Rule-level verdict: MARGINAL** → consider downgrading to monitor pending more data

---

## Baseline-bottom-non-weakness  (claim: ambiguous, current weight 1.0)

**Description:** bottom + subtype!=weakness (no rule fires, baseline 1.00)  
**R4 in-sample:** bottom+standard: n=66, mean +1.68%, CI [-0.15%, +3.78%]; bottom+hidden: n=8, mean +1.33%, CI [-3.83%, +7.13%]  

### Full-sample sanity check (replication of R4)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 74 | +1.64% | -0.15% | 47% | [-0.20%, +3.74%] |

### S1 50/50 by time  (cutoff 2025-01-30)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 29 | +3.18% | +2.02% | 59% | [+0.25%, +6.43%] |
| Test | 45 | +0.65% | -0.45% | 40% | [-1.64%, +3.37%] |

**Verdict:** **CONFIRM** (CI [-1.64%, +3.37%] crosses zero — pass-through justified)

### S2 40/60 by time  (cutoff 2024-11-02)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 23 | +3.57% | +2.02% | 61% | [+0.12%, +7.60%] |
| Test | 51 | +0.77% | -0.42% | 41% | [-1.31%, +3.13%] |

**Verdict:** **CONFIRM** (CI [-1.31%, +3.13%] crosses zero — pass-through justified)

### S3 last 12mo as test  (cutoff 2025-04-21)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 35 | +1.87% | +1.54% | 54% | [-0.87%, +4.95%] |
| Test | 39 | +1.44% | -0.42% | 41% | [-1.03%, +4.38%] |

**Verdict:** **CONFIRM** (CI [-1.03%, +4.38%] crosses zero — pass-through justified)

**Rule-level verdict: CONFIRM (3/3 splits)** → keep weight 1.0

---

## Cross-rule summary

| Rule | Claim | Weight | Full n | Full mean | Verdict | Action |
|---|---|--:|--:|--:|---|---|
| CN-top-supp-fade | negative | 0.8 | 74 | -1.59% | CONFIRM (3/3 splits) | keep weight 0.8 |
| F8-cn-no-boost | positive | 1.0 | 56 | +3.81% | CONFIRM (3/3 splits) | keep weight 1.0 |
| CN1-top-passthrough | ambiguous | 1.0 | 29 | +0.29% | MARGINAL | consider downgrading to monitor pending more data |
| Baseline-bottom-non-weakness | ambiguous | 1.0 | 74 | +1.64% | CONFIRM (3/3 splits) | keep weight 1.0 |

**Overall cn_futures policy: 3/4 CONFIRM, 0 REJECT, 0 UPGRADE-RECOMMENDED, 0 INSUFFICIENT.**  

R4 §4.1 'no out-of-sample validation' blanket flag is **CLOSED** for the cn_futures path.
