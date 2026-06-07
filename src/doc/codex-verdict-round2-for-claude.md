# Codex Round 2 Verification — F5 to F9

**Method**: Identical to Round 1. All checks run on horizon=20 signals, Bonferroni corrected for k=237 buckets.
**Date**: 2026-05-23
**Data**: signals_2026-05-23.csv (266 rows, 266 after h=20 filter)

**Key innovation vs Round 1**: direction-split analysis for mixed-direction candidates, F2 overlap quantification, Newey-West HAC standard errors, and bottom-only baseline comparison.

---

### F5: subtype=standard + lower_relation=leading + lower_cycle=in_cycle
**Verdict: ⚠️ Edge**

**Original claim**: n=31, 83.9% hit, +3.55% mean

#### Verification data

| Check | Value |
|------|-------|
| n | 31 |
| Hit rate | 83.9% |
| Mean return | +3.55% |
| Median return | +2.89% |
| HHI (symbol diversity) | 0.126 |
| Drop top-2 mean | +3.55% → +2.80% |
| Winsorize 5% mean | +3.42% |
| Bootstrap 95% CI | [+2.15%, +5.08%] |
| p_hit (raw) | 0.000192 |
| p_mean (raw) | 0.000060 |
| p_hit (Bonferroni, k=237) | 0.0456 |
| p_mean (Bonferroni, k=237) | 0.0142 |
| Newey-West HAC SE | 0.007601 |
| NW t-stat | 4.672 |
| NW p-value | 0.000059 |
| Overlap w/ F2 (bottom+leading+opposing) | 6/31 (19.4%) |

#### Symbol Breakdown (HHI=0.126)
Top symbols: XLK: 5, XLF: 5, SPY: 4, QQQ: 4, IWM: 4, GLD: 3, ... (9 symbols total)

#### Direction-Only Baseline Comparison
| Direction | Baseline n | Baseline hit | Baseline mean |
|-----------|-----------|-------------|--------------|
| bottom | 179 | 69.3% | +3.17% |
| top | 87 | 52.9% | -0.27% |

#### Year / Regime Breakdown
| Year | Count | Hit Rate | Mean Return |
|------|-------|----------|-------------|
| 2021 | 5 | 60.0% | +1.34% |
| 2022 | 5 | 100.0% | +8.02% |
| 2023 | 5 | 100.0% | +5.65% |
| 2024 | 11 | 90.9% | +3.01% |
| 2025 | 5 | 60.0% | +0.38% |

**2022 bear market**: n=5, hit=100.0%, mean=+8.02%
**Other years**: n=26, hit=80.8%, mean=+2.69%

#### Direction Split
| Direction | n | Hit Rate | Mean | Median | CI95 | Drop-top2 |
|-----------|---|----------|------|--------|------|-----------|
| bottom | 9 | 100.0% | +7.01% | +6.20% | [+4.56%, +10.09%] | +5.08% |
| top | 22 | 77.3% | +2.14% | +2.59% | [+0.87%, +3.53%] | +1.44% |

#### Outlier Analysis
Top-3 returns: +10.18%, +11.66%, +17.34%
Bottom-3 returns: -4.34%, -2.14%, -1.29%
Mean without top-3: +2.53%

#### Rationale
HHI=0.126 < 0.30 ✅; Drop-top2: +3.55% → +2.80% ✅; Bootstrap 95% CI [+2.15%, +5.08%] > 0 ✅; Bonferroni hit p=0.0456, mean p=0.0142 — both < 0.05 ✅; 2022: 5/31 (16%) — well distributed ✅; Direction asymmetry: pattern is bottom-driven — fails as mixed-direction claim

---

### F6: lower_relation=leading + lower_cycle=in_cycle + higher_relation=opposing
**Verdict: ⚠️ Edge**

**Original claim**: n=27, 88.9% hit, +4.43% mean

#### Verification data

| Check | Value |
|------|-------|
| n | 27 |
| Hit rate | 88.9% |
| Mean return | +4.43% |
| Median return | +3.12% |
| HHI (symbol diversity) | 0.130 |
| Drop top-2 mean | +4.43% → +3.62% |
| Winsorize 5% mean | +4.31% |
| Bootstrap 95% CI | [+2.89%, +6.14%] |
| p_hit (raw) | 0.000049 |
| p_mean (raw) | 0.000018 |
| p_hit (Bonferroni, k=237) | 0.0117 |
| p_mean (Bonferroni, k=237) | 0.0042 |
| Newey-West HAC SE | 0.007743 |
| NW t-stat | 5.720 |
| NW p-value | 0.000005 |
| Overlap w/ F2 (bottom+leading+opposing) | 9/27 (33.3%) |

#### Symbol Breakdown (HHI=0.130)
Top symbols: XLF: 5, SPY: 4, IWM: 4, XLK: 4, GLD: 3, QQQ: 2, ... (9 symbols total)

#### Direction-Only Baseline Comparison
| Direction | Baseline n | Baseline hit | Baseline mean |
|-----------|-----------|-------------|--------------|
| bottom | 179 | 69.3% | +3.17% |
| top | 87 | 52.9% | -0.27% |

#### Year / Regime Breakdown
| Year | Count | Hit Rate | Mean Return |
|------|-------|----------|-------------|
| 2022 | 3 | 100.0% | +11.23% |
| 2023 | 6 | 100.0% | +5.78% |
| 2024 | 11 | 90.9% | +3.01% |
| 2025 | 6 | 66.7% | +1.81% |
| 2026 | 1 | 100.0% | +7.22% |

**2022 bear market**: n=3, hit=100.0%, mean=+11.23%
**Other years**: n=24, hit=87.5%, mean=+3.58%

#### Direction Split
| Direction | n | Hit Rate | Mean | Median | CI95 | Drop-top2 |
|-----------|---|----------|------|--------|------|-----------|
| bottom | 9 | 100.0% | +8.12% | +7.22% | [+5.91%, +10.85%] | +6.51% |
| top | 18 | 83.3% | +2.58% | +2.72% | [+1.16%, +4.12%] | +1.77% |

#### Subtype Distribution
- standard: 24
- weakness: 2
- hidden: 1

#### Outlier Analysis
Top-3 returns: +10.18%, +11.66%, +17.34%
Bottom-3 returns: -4.34%, -0.88%, -0.87%
Mean without top-3: +3.35%

#### Rationale
HHI=0.130 < 0.30 ✅; Drop-top2: +4.43% → +3.62% ✅; Bootstrap 95% CI [+2.89%, +6.14%] > 0 ✅; Bonferroni hit p=0.0117, mean p=0.0042 — both < 0.05 ✅; 2022: 3/27 (11%) — well distributed ✅; Direction asymmetry: pattern is bottom-driven — fails as mixed-direction claim

---

### F7: direction=bottom + higher_relation=opposing + higher_cycle=in_cycle
**Verdict: ⚠️ Edge**

**Original claim**: n=36, 80.6% hit, +6.72% mean

#### Verification data

| Check | Value |
|------|-------|
| n | 36 |
| Hit rate | 80.6% |
| Mean return | +6.72% |
| Median return | +6.47% |
| HHI (symbol diversity) | 0.116 |
| Drop top-2 mean | +6.72% → +5.41% |
| Winsorize 5% mean | +6.24% |
| Bootstrap 95% CI | [+4.37%, +9.29%] |
| p_hit (raw) | 0.000313 |
| p_mean (raw) | 0.000006 |
| p_hit (Bonferroni, k=237) | 0.0741 |
| p_mean (Bonferroni, k=237) | 0.0014 |
| Newey-West HAC SE | 0.016224 |
| NW t-stat | 4.142 |
| NW p-value | 0.000206 |
| Overlap w/ F2 (bottom+leading+opposing) | 10/36 (27.8%) |

#### Symbol Breakdown (HHI=0.116)
Top symbols: IWM: 6, NVDA: 5, TLT: 5, SPY: 4, GDX: 4, QQQ: 3, ... (10 symbols total)

#### Direction-Only Baseline Comparison
| Direction | Baseline n | Baseline hit | Baseline mean |
|-----------|-----------|-------------|--------------|
| bottom | 179 | 69.3% | +3.17% |
| top | 87 | 52.9% | -0.27% |

#### Year / Regime Breakdown
| Year | Count | Hit Rate | Mean Return |
|------|-------|----------|-------------|
| 2022 | 18 | 77.8% | +5.37% |
| 2023 | 14 | 78.6% | +6.07% |
| 2025 | 3 | 100.0% | +17.68% |
| 2026 | 1 | 100.0% | +7.22% |

**2022 bear market**: n=18, hit=77.8%, mean=+5.37%
**Other years**: n=18, hit=83.3%, mean=+8.07%

#### Subtype Distribution
- standard: 27
- weakness: 7
- hidden: 2

#### Outlier Analysis
Top-3 returns: +17.34%, +28.32%, +29.76%
Bottom-3 returns: -4.06%, -3.71%, -3.56%
Mean without top-3: +5.05%

#### Rationale
HHI=0.116 < 0.30 ✅; Drop-top2: +6.72% → +5.41% ✅; Bootstrap 95% CI [+4.37%, +9.29%] > 0 ✅; Bonferroni hit p=0.0741, mean p=0.0014 — one passes ⚠️; 2022: 18/36 (50%) — moderate ⚠️

---

### F8: direction=bottom + subtype=weakness
**Verdict: ✅ Survives**

**Original claim**: n=123, 68.3% hit, +2.63% mean

#### Verification data

| Check | Value |
|------|-------|
| n | 123 |
| Hit rate | 68.3% |
| Mean return | +2.63% |
| Median return | +1.97% |
| HHI (symbol diversity) | 0.118 |
| Drop top-2 mean | +2.63% → +2.09% |
| Winsorize 5% mean | +2.29% |
| Bootstrap 95% CI | [+1.47%, +3.91%] |
| p_hit (raw) | 0.000061 |
| p_mean (raw) | 0.000048 |
| p_hit (Bonferroni, k=237) | 0.0145 |
| p_mean (Bonferroni, k=237) | 0.0115 |
| Newey-West HAC SE | 0.005896 |
| NW t-stat | 4.469 |
| NW p-value | 0.000018 |
| Overlap w/ F2 (bottom+leading+opposing) | 3/123 (2.4%) |

#### Symbol Breakdown (HHI=0.118)
Top symbols: SPY: 23, XLF: 16, XLK: 14, DIA: 13, QQQ: 12, GLD: 12, ... (10 symbols total)

#### Direction-Only Baseline Comparison
| Direction | Baseline n | Baseline hit | Baseline mean |
|-----------|-----------|-------------|--------------|
| bottom | 179 | 69.3% | +3.17% |
| top | 87 | 52.9% | -0.27% |

#### Year / Regime Breakdown
| Year | Count | Hit Rate | Mean Return |
|------|-------|----------|-------------|
| 2021 | 13 | 76.9% | +1.53% |
| 2022 | 6 | 66.7% | +2.10% |
| 2023 | 28 | 64.3% | +2.55% |
| 2024 | 39 | 74.4% | +2.73% |
| 2025 | 28 | 57.1% | +1.65% |
| 2026 | 9 | 77.8% | +7.49% |

**2022 bear market**: n=6, hit=66.7%, mean=+2.10%
**Other years**: n=117, hit=68.4%, mean=+2.66%

#### Outlier Analysis
Top-3 returns: +18.43%, +28.32%, +42.69%
Bottom-3 returns: -14.00%, -10.55%, -9.93%
Mean without top-3: +1.96%

#### Rationale
HHI=0.118 < 0.30 ✅; Drop-top2: +2.63% → +2.09% ✅; Bootstrap 95% CI [+1.47%, +3.91%] > 0 ✅; Bonferroni hit p=0.0145, mean p=0.0115 — both < 0.05 ✅; 2022: 6/123 (5%) — well distributed ✅

---

### F9: lower_relation=leading (single dimension)
**Verdict: ⚠️ Edge**

**Original claim**: n=84, 72.6% hit, +2.88% mean

#### Verification data

| Check | Value |
|------|-------|
| n | 84 |
| Hit rate | 72.6% |
| Mean return | +2.88% |
| Median return | +2.79% |
| HHI (symbol diversity) | 0.109 |
| Drop top-2 mean | +2.88% → +2.19% |
| Winsorize 5% mean | +2.94% |
| Bootstrap 95% CI | [+1.15%, +4.68%] |
| p_hit (raw) | 0.000041 |
| p_mean (raw) | 0.001862 |
| p_hit (Bonferroni, k=237) | 0.0097 |
| p_mean (Bonferroni, k=237) | 0.4414 |
| Newey-West HAC SE | 0.006365 |
| NW t-stat | 4.528 |
| NW p-value | 0.000020 |
| Overlap w/ F2 (bottom+leading+opposing) | 15/84 (17.9%) |

#### Symbol Breakdown (HHI=0.109)
Top symbols: XLK: 13, XLF: 11, SPY: 10, GLD: 10, QQQ: 9, IWM: 7, ... (10 symbols total)

#### Direction-Only Baseline Comparison
| Direction | Baseline n | Baseline hit | Baseline mean |
|-----------|-----------|-------------|--------------|
| bottom | 179 | 69.3% | +3.17% |
| top | 87 | 52.9% | -0.27% |

#### Year / Regime Breakdown
| Year | Count | Hit Rate | Mean Return |
|------|-------|----------|-------------|
| 2021 | 13 | 61.5% | +0.95% |
| 2022 | 14 | 71.4% | +2.68% |
| 2023 | 12 | 66.7% | +2.85% |
| 2024 | 28 | 78.6% | +3.08% |
| 2025 | 14 | 71.4% | +3.23% |
| 2026 | 3 | 100.0% | +8.87% |

**2022 bear market**: n=14, hit=71.4%, mean=+2.68%
**Other years**: n=70, hit=72.9%, mean=+2.92%

#### Direction Split
| Direction | n | Hit Rate | Mean | Median | CI95 | Drop-top2 |
|-----------|---|----------|------|--------|------|-----------|
| bottom | 47 | 78.7% | +4.79% | +4.01% | [+2.72%, +7.28%] | +3.61% |
| top | 37 | 64.9% | +0.45% | +2.51% | [-2.31%, +2.67%] | -0.22% |

#### Subtype Distribution
- standard: 46
- weakness: 34
- hidden: 4

#### Outlier Analysis
Top-3 returns: +17.34%, +20.09%, +42.69%
Bottom-3 returns: -35.66%, -15.06%, -8.65%
Mean without top-3: +2.00%

#### Rationale
HHI=0.109 < 0.30 ✅; Drop-top2: +2.88% → +2.19% ✅; Bootstrap 95% CI [+1.15%, +4.68%] > 0 ✅; Bonferroni hit p=0.0097, mean p=0.4414 — one passes ⚠️; 2022: 14/84 (17%) — well distributed ✅; Direction asymmetry: pattern is bottom-driven

---


## Summary

| Candidate | Claim | n | Hit | Mean | Bonf (hit/mean) | HHI | Verdict |
|-----------|-------|---|-----|------|----------------|-----|---------|
| F5 | subtype=standard + lower_relation=leading + lower_cycle=in_cycle | 31 | 83.9% | +3.55% | 0.046/0.014 | 0.126 | ⚠️ Edge |
| F6 | lower_relation=leading + lower_cycle=in_cycle + higher_relation=opposing | 27 | 88.9% | +4.43% | 0.012/0.004 | 0.130 | ⚠️ Edge |
| F7 | direction=bottom + higher_relation=opposing + higher_cycle=in_cycle | 36 | 80.6% | +6.72% | 0.074/0.001 | 0.116 | ⚠️ Edge |
| F8 | direction=bottom + subtype=weakness | 123 | 68.3% | +2.63% | 0.014/0.011 | 0.118 | ✅ Survives |
| F9 | lower_relation=leading (single dimension) | 84 | 72.6% | +2.88% | 0.010/0.441 | 0.109 | ⚠️ Edge |

---

## Policy Recommendations

- **F5** `subtype=standard + lower_relation=leading + lower_cycle=in_cycle` → **EDGE — optional cautious add** (weight 1.05, monitor)
- **F6** `lower_relation=leading + lower_cycle=in_cycle + higher_relation=opposing` → **EDGE — optional cautious add** (weight 1.05, monitor)
- **F7** `direction=bottom + higher_relation=opposing + higher_cycle=in_cycle` → **EDGE — optional cautious add** (weight 1.05, monitor)
- **F8** `direction=bottom + subtype=weakness` → **ADD TO POLICY** (weight 1.10)
- **F9** `lower_relation=leading (single dimension)` → **EDGE — optional cautious add** (weight 1.05, monitor)

### Specific Guidance

- **F7** has highest mean (+6.72%) but 50% of signals from 2022 bear market — requires ongoing validation
- **F8** is the most robust pattern by sample size (n=123) — good as a universal bottom-boost baseline
- **F9 collapses as a direction-agnostic claim** — bottom+leading is real (the #1 bucket in mining), but the unified F9 claim is driven entirely by bottom asymmetry. The top+leading subset (n=37, mean=+0.45%, CI crosses zero) is not significant.
- **F5 and F6** are direction-asymmetric but Bonferroni-significant; their bottom subsets are very strong but overlap substantially with bottom+leading (F2-style) patterns

