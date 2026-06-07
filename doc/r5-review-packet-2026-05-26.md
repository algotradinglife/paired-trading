# Codex R5 Review Packet — CN-top-supp-fade rule status post deep-data backtest

**Date**: 2026-05-26
**Trigger**: Today's qveris backfill extended CN intraday from 1-2y to 14y. Re-running B-topology backtest with deep data (4.3x sample) shows R4 verdict claims may have been window artifacts. Before changing production policy, need rigorous review.

---

## 1. Context

### 1.1 R4 verdict (2026-05-24, on 2.4y backtest sample n=233 signals)

Three CN-futures policy rules landed based on R4:

- `CN-top-supp-fade` (weight 0.80): top + higher_relation=supporting → de-weight 0.80
  - **Basis**: n=74 signals, mean signed_return -1.59%, 95% CI [-3.40%, +0.02%] — CI just touches zero (marginal, not cleanly significant)
- `F8-cn-no-boost` (weight 1.00): bottom + subtype=weakness → pass-through, no boost
  - **Basis**: n=56, mean +3.81%, CI [+1.76%, +6.22%] (most robust positive in R4)
- `CN1-top-passthrough` (weight 1.00): top residual after CN-top-supp-fade → no de-weight
  - **Basis**: residual (n=29), mean +0.29%, CI [-2.83%, +3.08%] (crosses zero)

R4 conclusion: CN-top-supp-fade was the only statistically defensible top de-weight. Pooled top de-weight not supported (CI crosses zero).

### 1.2 v1 vs v2 sample

| Metric | v1 (R4 source) | v2 (today, deep) | Δ |
|---|---|---|---|
| Source script | `backtest_cn_b_topology.py` (no change) | same | identical |
| Symbols | 19 CN futures (4 CFFEX index + 15 commodity) | 19 (same) | identical |
| Date range | 2023-11-12 → 2026-04-21 (2.4y) | 2016-01-21 → 2026-04-21 (10y) | 4.2x window |
| Total rows | 699 | 3024 | 4.3x |
| Unique signals at h=20 | 233 | 1008 | 4.3x |

Caveat: 4 CZCE symbols (TA/MA/CF/SR) still use TqSdk shallow data because qveris THS subscription doesn't expose CZCE intraday. Other 15 symbols got 14y qveris backfill. CZCE shares ~10% of v2 signal pool.

### 1.3 R4 key cells: v1 vs v2 (h=20, bootstrap 95% CI seed=42, n_resample=5000)

| Cell | v1: n / mean / hit / CI | v2: n / mean / hit / CI |
|---|---|---|
| top pooled | 103 / **-1.06%** / 48.5% / [-2.54%, +0.39%] | 506 / **+0.34%** / 52.8% / [-0.32%, +1.02%] |
| bottom pooled | 130 / +2.58% / 60.0% / [+1.19%, +4.22%] | 502 / +1.50% / 57.2% / [+0.80%, +2.22%] |
| **top + higher=supporting** | 74 / **-1.59%** / 43.2% / **[-3.32%, +0.02%]** | 324 / **-0.10%** / 48.8% / **[-0.99%, +0.82%]** |
| F8 = bottom + subtype=weakness | 56 / +3.81% / 76.8% / [+1.74%, +6.38%] | 306 / +1.19% / 57.5% / [+0.26%, +2.14%] |
| CN-B1 = top + higher=opposing | 20 / +2.51% / 80.0% / [-1.14%, +5.34%] | 147 / +1.12% / 59.9% / [-0.03%, +2.33%] |

### 1.4 Walk-forward K=3 on v2 deep data (signal-count chunks)

Chunk dates:
- chunk[0]: 2016-05 → 2019-12 (n=336)
- chunk[1]: 2019-12 → 2023-07 (n=336)
- chunk[2]: 2023-08 → 2026-04 (n=336)

| Cell | fold1 (train ch0 / test ch1) | fold2 (train ch0+1 / test ch2) | Both folds pass +10pp uplift? |
|---|---|---|---|
| top+supporting | train +0.62% / test +0.26% (positive — opposite of rule expectation) | train +0.42% / test -1.02% | **NO** |
| F8 (bot+weakness) | train +1.67% / **test -0.30%** | train +0.59% / **test +2.85%** (71% hit) | **NO** (fold2-only) |
| CN-B1 (top+higher_opposing) | train +1.00% / test +0.79% | train +0.91% / test +1.94% | **NO** (uplift <+10pp) |
| top all | train +0.91% / test +0.34% | train +0.63% / test -0.25% | NO |
| bottom all | train +2.03% / test +0.34% | train +1.18% / test +2.11% | NO (uplift <+10pp) |

**Walk-forward stable cells: 0** (same as v1, despite 4.3x sample).

---

## 2. Policy decision under review

### 2.1 CN-top-supp-fade (weight 0.80)

The basis statistic on v1 was n=74, mean -1.59%, CI [-3.40%, +0.02%] — CI just barely excluded zero, marginally statistically significant.

On v2: n=324 (4.4x sample), mean **-0.10%**, CI **[-0.99%, +0.82%]** — CI fully straddles zero by a wide margin.

Three options:

- **D1**: Remove rule (revert top+supporting to pass-through weight 1.00). Rationale: the v2 95% CI is symmetric around -0.10% with both bounds well clear of -1.59%. The original basis is gone. Bayesian updating with a 4x larger sample puts the posterior firmly near zero.

- **D2**: Reduce weight 0.80 → 0.95. Compromise: deep data shows mean still slightly negative direction-wise; some of the v1 effect may be real but small. 0.95 weight preserves a soft prior against this configuration without claiming statistical significance.

- **D3**: Keep 0.80, document as regime-conditional. Bet that v1's 2024-2026 regime is more representative of future regimes than the 2016-2023 sample. Walk-forward fold2 (post-Aug 2023) is -1.02% which loosely matches v1 magnitude.

### 2.2 F8-cn-no-boost (weight 1.00, no change)

v1 +3.81% → v2 +1.19%. Weakened 3x but CI still excludes zero. The rule weight is 1.00 (pass-through), so technically nothing to change. But the **description / reason fields** in code reference the v1 +3.81% magnitude, which is now inaccurate.

Suggested update: refresh docstring to cite v2 magnitude (+1.19%, CI [+0.26%, +2.14%]) and note the v1 figure was sample-window-restricted.

### 2.3 CN1-top-passthrough (weight 1.00, no change)

Unchanged conclusion. The pooled top residual still has CI crossing zero in both v1 and v2.

---

## 3. Specific questions for Codex review

Please evaluate each carefully:

**Q1 — Statistical interpretation**: Given v1 (n=74, mean -1.59%, CI just touches +0.02%) and v2 (n=324, mean -0.10%, CI [-0.99%, +0.82%]), is it correct to conclude that the v1 effect was substantially driven by sample-window selection and the rule's statistical basis is no longer defensible? Or is there an alternative interpretation (e.g., the v2 sample dilutes a real recent-regime effect by including older inapplicable history)?

**Q2 — Policy recommendation**: Which of D1/D2/D3 is statistically + operationally most defensible?
- D1 (remove): pure statistical interpretation
- D2 (0.95): hybrid Bayesian
- D3 (keep 0.80): regime-bet
Or do you recommend a fourth option (e.g., D4: condition the rule on a regime indicator)?

**Q3 — Walk-forward verdict consistency**: v2 walk-forward shows 0 cells pass both folds. fold2 (post-Aug 2023) does show top+supporting -1.02% (close to v1's -1.59%). Is "this rule works only when regime resembles post-2023" a usable hypothesis, or is the fold1-vs-fold2 asymmetry just noise at this sample size?

**Q4 — F8-cn weakening**: F8-cn went +3.81% → +1.19%. CI on v2 still excludes zero ([+0.26, +2.14]). Is "F8 is still real but R4 overstated magnitude" the right conclusion? Should we add a confidence weight reduction (e.g., 1.10 → 1.05 boost) to F8 in policy, or leave at 1.00?

**Q5 — Walk-forward as ceiling**: 4.3x sample didn't move walk-forward stable cells from 0 → anything. This suggests new detector types are needed (per `doc/exhaustion-detector-spec-2026-05-26.md`). Do you concur that filter tuning has hit a structural ceiling on this engine?

**Q6 — CZCE caveat impact**: 4 CZCE symbols still use shallow TqSdk data in v2. Could the v1→v2 magnitude reductions be partly due to CZCE-specific patterns becoming a larger or smaller share of the pool?

**Q7 — Anything else worth flagging** before policy change ships.

---

## 4. Expected output format

```markdown
# Codex R5 verdict

## Per-question
Q1 (statistical interpretation): <answer + reasoning>
Q2 (D1/D2/D3 recommendation): <choice + reasoning>
Q3 (walk-forward regime usage): <answer>
Q4 (F8 weakening): <answer>
Q5 (filter-tuning ceiling): <answer>
Q6 (CZCE impact): <answer>
Q7 (additional): <flags>

## Recommended policy changes
- ...

## Methodology flags
- ...
```

Save to `doc/codex-r5-verdict-2026-05-26.md`. I'll integrate verdict into policy on receipt.

---

## 5. Reference data

- `src/data/review/cn_b_topology_signals_all_v1.csv` — 699 rows (2.4y, R4 source)
- `src/data/review/cn_b_topology_signals_all_v2.csv` — 3024 rows (10y deep)
- `doc/cn-b-topology-deep-2026-05-26.md` — full re-run report
- `doc/r4-review-2026-05-24.md` — original R4 verdict
- `src/engine/divergence/downstream_policies.py::_apply_cn_futures` — current policy code
