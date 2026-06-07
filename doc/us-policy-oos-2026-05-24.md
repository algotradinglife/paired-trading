# us_equity Policy — Full OOS Validation

**Date:** 2026-05-24  
**Scope:** all rules in `engine/divergence/downstream_policies._apply_us_equity`  
**Data:** `src/data/review/b_topology_signals_all.csv` h=20, 2021-06-08 → 2026-04-15 (~5y, 10 symbols)  
**Bootstrap:** 5000 resamples, numpy default_rng(42)  
**Pre-registered min test n:** 15  

## Note on rule classification
CSV's `rule_id` column was generated 2026-05-23 BEFORE B1 was added to the policy. Signals are re-classified under the CURRENT precedence:
F2 → F3 → F4 → **B1** → F1 → F8 → baseline. Old-F1 signals with higher=opposing now route to B1.

**Re-classified distribution (h=20):**

```
  F8-bottom-weakness-baseline          102
  (baseline)                            52
  F1-top-lagging-soft                   37
  F2-strong-bottom                      34
  F4-options-asymmetric                 23
  F3-candidate-counter-trend             9
  B1-top-higher-opposing                 9
```

## Pre-registered judgment criteria (same as CN harness)
- **claim=negative** STRONG CONFIRM: mean ∈ [-3.0, -0.5%], CI upper ≤ +0.5%
- **claim=positive** STRONG CONFIRM: mean ∈ [+0.5, +6.0%], CI lower ≥ -0.5%
- **claim=ambiguous** CONFIRM: CI crosses zero (pass-through justified)
- **REJECT** when sign opposite to claim, or CI excess in wrong direction (≥1.5%)
- **INSUFFICIENT** when test n < 15

## Splits (same date axis across all rules)
- **S1 50/50 by time**: cutoff 2023-11-11
- **S2 40/60 by time**: cutoff 2023-05-17
- **S3 last 12mo as test**: cutoff 2025-04-15

---

## F2-strong-bottom  (claim: positive, current weight 1.2)

**Description:** bottom + lower=leading + higher=opposing (R1)  
**Prior review:** R1: validated multi-TF reversal, n≈30 single-TF baseline  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 34 | +4.57% | +2.94% | 79% | [+1.96%, +7.64%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 16 | +4.93% | +4.08% | 75% | [+0.33%, +11.28%] |
| Test | 18 | +4.24% | +2.54% | 83% | [+1.85%, +7.03%] |

**Verdict:** **STRONG CONFIRM** (mean +4.24% in [0.5, 6.0], CI lower +1.85% ≥ -0.5%)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 15 | +5.58% | +4.72% | 80% | [+0.92%, +11.77%] |
| Test | 19 | +3.76% | +2.48% | 79% | [+1.27%, +6.62%] |

**Verdict:** **STRONG CONFIRM** (mean +3.76% in [0.5, 6.0], CI lower +1.27% ≥ -0.5%)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 27 | +4.23% | +2.89% | 78% | [+1.25%, +8.11%] |
| Test | 7 | +5.85% | +6.60% | 86% | [+2.21%, +10.02%] |

**Verdict:** **INSUFFICIENT** (n=7 < 15)

**Rule-level verdict: MARGINAL** → monitor; consider weight reduction if pattern persists

---

## F3-candidate-counter-trend  (claim: positive, current weight 1.15)

**Description:** confidence ∈ candidate band + higher=opposing (R1)  
**Prior review:** R1: 14/14 perfect in 5y sample — itself a fit flag  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 9 | +5.35% | +4.05% | 89% | [+2.55%, +8.92%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 7 | +5.92% | +4.83% | 86% | [+2.40%, +10.33%] |
| Test | 2 | +3.34% | +3.34% | 100% | [+3.12%, +3.55%] |

**Verdict:** **INSUFFICIENT** (n=2 < 15)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 3 | +6.47% | +3.66% | 67% | [-1.59%, +17.34%] |
| Test | 6 | +4.78% | +4.44% | 100% | [+3.73%, +5.98%] |

**Verdict:** **INSUFFICIENT** (n=6 < 15)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 9 | +5.35% | +4.05% | 89% | [+2.55%, +8.92%] |
| Test | 0 | — | — | — | — |

**Verdict:** **INSUFFICIENT** (n=0 < 15)

**Rule-level verdict: INSUFFICIENT** → data thin; accumulate and re-run

---

## F4-options-asymmetric  (claim: positive, current weight 1.0)

**Description:** top + lower=leading + higher=opposing (R1)  
**Prior review:** R1: 24/25 ≈ 96% small-win, options-asymmetric pattern  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 23 | -0.21% | +1.33% | 57% | [-4.35%, +2.90%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 11 | -2.89% | -1.29% | 45% | [-10.25%, +2.36%] |
| Test | 12 | +2.24% | +1.34% | 67% | [-0.33%, +5.19%] |

**Verdict:** **INSUFFICIENT** (n=12 < 15)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 10 | -2.87% | +0.06% | 50% | [-11.26%, +2.76%] |
| Test | 13 | +1.83% | +1.33% | 62% | [-0.60%, +4.72%] |

**Verdict:** **INSUFFICIENT** (n=13 < 15)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 19 | -0.80% | +1.33% | 58% | [-5.21%, +2.59%] |
| Test | 4 | +2.57% | +0.90% | 50% | [-2.60%, +9.38%] |

**Verdict:** **INSUFFICIENT** (n=4 < 15)

**Rule-level verdict: INSUFFICIENT** → data thin; accumulate and re-run

---

## B1-top-higher-opposing  (claim: positive, current weight 1.3)

**Description:** top + higher=opposing (residual after F4/F3) (R3)  
**Prior review:** R3: 27% stop-hit vs F1's 72%, h=20 +33.8% under SL-10%  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 9 | -0.01% | +2.51% | 67% | [-4.30%, +2.85%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 2 | -6.16% | -6.16% | 50% | [-15.06%, +2.74%] |
| Test | 7 | +1.75% | +2.51% | 71% | [+0.05%, +3.29%] |

**Verdict:** **INSUFFICIENT** (n=7 < 15)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 1 | -15.06% | -15.06% | 0% | [-15.06%, -15.06%] |
| Test | 8 | +1.87% | +2.63% | 75% | [+0.36%, +3.19%] |

**Verdict:** **INSUFFICIENT** (n=8 < 15)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 7 | -0.64% | +2.51% | 57% | [-5.93%, +3.10%] |
| Test | 2 | +2.21% | +2.21% | 100% | [+1.54%, +2.89%] |

**Verdict:** **INSUFFICIENT** (n=2 < 15)

**Rule-level verdict: INSUFFICIENT** → data thin; accumulate and re-run

---

## F1-top-lagging-soft  (claim: negative, current weight 0.7)

**Description:** top + lower=lagging (residual after F4/B1) (R1)  
**Prior review:** R1: edge-significant downside; R3 stop-hit 72-94%  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 37 | -0.70% | -0.69% | 46% | [-2.77%, +1.27%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 8 | +2.10% | +3.94% | 75% | [-4.25%, +7.06%] |
| Test | 29 | -1.48% | -1.01% | 38% | [-3.43%, +0.37%] |

**Verdict:** **STRONG CONFIRM** (mean -1.48% in [-3.0, -0.5], CI upper +0.37% ≤ +0.5%)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 5 | +5.05% | +3.55% | 80% | [+0.87%, +9.45%] |
| Test | 32 | -1.60% | -0.99% | 41% | [-3.72%, +0.33%] |

**Verdict:** **STRONG CONFIRM** (mean -1.60% in [-3.0, -0.5], CI upper +0.33% ≤ +0.5%)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 24 | -0.15% | +0.25% | 50% | [-2.64%, +2.30%] |
| Test | 13 | -1.72% | -1.01% | 38% | [-5.08%, +1.45%] |

**Verdict:** **INSUFFICIENT** (n=13 < 15)

**Rule-level verdict: MARGINAL** → monitor; consider weight reduction if pattern persists

---

## F8-bottom-weakness-baseline  (claim: positive, current weight 1.1)

**Description:** bottom + subtype=weakness (residual after F2) (R2)  
**Prior review:** R2: n=123 workhorse, R3 +73.5% EV at SL -3%  

### Full-sample (under current precedence)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full | 102 | +2.40% | +1.96% | 68% | [+1.21%, +3.65%] |

### S1 50/50 by time  (cutoff 2023-11-11)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 33 | +0.64% | +1.18% | 64% | [-1.19%, +2.33%] |
| Test | 69 | +3.24% | +2.41% | 70% | [+1.79%, +4.75%] |

**Verdict:** **STRONG CONFIRM** (mean +3.24% in [0.5, 6.0], CI lower +1.79% ≥ -0.5%)

### S2 40/60 by time  (cutoff 2023-05-17)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 20 | +2.30% | +2.42% | 75% | [+0.22%, +4.16%] |
| Test | 82 | +2.42% | +1.96% | 66% | [+1.01%, +3.86%] |

**Verdict:** **STRONG CONFIRM** (mean +2.42% in [0.5, 6.0], CI lower +1.01% ≥ -0.5%)

### S3 last 12mo as test  (cutoff 2025-04-15)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 80 | +1.66% | +1.95% | 68% | [+0.50%, +2.84%] |
| Test | 22 | +5.08% | +2.86% | 68% | [+2.02%, +8.59%] |

**Verdict:** **STRONG CONFIRM** (mean +5.08% in [0.5, 6.0], CI lower +2.02% ≥ -0.5%)

**Rule-level verdict: CONFIRM (3/3)** → keep weight 1.1

---

## Cross-rule summary

| Rule | Claim | Weight | Full n | Full mean | Verdict | Action |
|---|---|--:|--:|--:|---|---|
| F2-strong-bottom | positive | 1.2 | 34 | +4.57% | MARGINAL | monitor; consider weight reduction if pattern persists |
| F3-candidate-counter-trend | positive | 1.15 | 9 | +5.35% | INSUFFICIENT | data thin; accumulate and re-run |
| F4-options-asymmetric | positive | 1.0 | 23 | -0.21% | INSUFFICIENT | data thin; accumulate and re-run |
| B1-top-higher-opposing | positive | 1.3 | 9 | -0.01% | INSUFFICIENT | data thin; accumulate and re-run |
| F1-top-lagging-soft | negative | 0.7 | 37 | -0.70% | MARGINAL | monitor; consider weight reduction if pattern persists |
| F8-bottom-weakness-baseline | positive | 1.1 | 102 | +2.40% | CONFIRM (3/3) | keep weight 1.1 |

**Overall us_equity policy: 1/6 CONFIRM, 0 REJECT, 0 UPGRADE-RECOMMENDED, 2 MARGINAL, 3 INSUFFICIENT.**  

Partial close: 2 marginal + 3 insufficient rule(s) remain.
