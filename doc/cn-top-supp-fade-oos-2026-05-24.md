# CN-top-supp-fade — Out-of-Sample Validation

**Date:** 2026-05-24  
**Rule under test:** CN-top-supp-fade (top + higher_relation=supporting, weight 0.80)  
**In-sample reference (R4):** n=74, mean -1.59%, CI [-3.40%, +0.02%]  
**Data:** `src/data/review/cn_b_topology_signals_all.csv` h=20  
**Date range:** 2024-01-15 → 2026-04-13  
**Bootstrap:** 5000 resamples, numpy default_rng(42)  

## Pre-registered judgment criteria
- **STRONG CONFIRM**: test mean ∈ [-3.0%, -0.5%] AND CI upper ≤ +0.5%
- **CONFIRM**: test mean < 0 AND CI upper ≤ +0.5%
- **REVERT** (→ weight 1.0 monitor): test mean > 0, OR CI upper ≥ +1.5%
- **INSUFFICIENT**: test n < 15 (defer judgment)
- **MARGINAL**: anything in between

## Full-sample sanity check
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Full (matches R4) | 74 | -1.59% | -0.75% | 43% | [-3.38%, +0.01%] |

## S1 (50/50 by time)  (cutoff: 2025-02-27)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 22 | -0.99% | -1.10% | 45% | [-5.00%, +2.22%] |
| Test | 52 | -1.84% | -0.46% | 42% | [-3.77%, -0.04%] |

**Verdict:** **STRONG CONFIRM** (mean -1.84% in [-3.0, -0.5], CI upper -0.04% ≤ +0.5%)

## S2 (60/40 by time)  (cutoff: 2025-05-20)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 35 | -0.77% | +1.49% | 51% | [-3.55%, +1.53%] |
| Test | 39 | -2.33% | -1.29% | 36% | [-4.61%, -0.16%] |

**Verdict:** **STRONG CONFIRM** (mean -2.33% in [-3.0, -0.5], CI upper -0.16% ≤ +0.5%)

## S3 (last 12mo = test)  (cutoff: 2025-04-13)
| Sample | n | mean | median | hit | 95% CI |
|---|--:|--:|--:|--:|---|
| Train | 32 | -0.76% | +0.66% | 50% | [-3.76%, +1.70%] |
| Test | 42 | -2.22% | -1.23% | 38% | [-4.41%, -0.25%] |

**Verdict:** **STRONG CONFIRM** (mean -2.22% in [-3.0, -0.5], CI upper -0.25% ≤ +0.5%)

## Aggregate verdict
| Split | Verdict |
|---|---|
| S1 (50/50 by time) | **STRONG CONFIRM** (mean -1.84% in [-3.0, -0.5], CI upper -0.04% ≤ +0.5%) |
| S2 (60/40 by time) | **STRONG CONFIRM** (mean -2.33% in [-3.0, -0.5], CI upper -0.16% ≤ +0.5%) |
| S3 (last 12mo = test) | **STRONG CONFIRM** (mean -2.22% in [-3.0, -0.5], CI upper -0.25% ≤ +0.5%) |

**OVERALL: CONFIRM** — 3/3 splits confirm. Keep weight 0.80.
