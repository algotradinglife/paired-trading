# CN B-Topology Backtest — Deep-Data Re-run 2026-05-26

**Bottom line**: R4 codex verdict (2026-05-24) was largely a **2.4-year short-window artifact**. On 10-year deep data (4.3x sample), the headline claims **collapse or reverse**:
- "CN tops are negative -1.06%" → actually **+0.34%** on deep data (sign-flip)
- `CN-top-supp-fade` rule basis (top+supporting -1.59%) → **-0.10%** (mean essentially zero); rule weight 0.80 should be reviewed
- F8-cn (+3.81%) → **+1.19%** (3x weaker but still positive + CI excludes zero)
- Walk-forward verdict unchanged: **0 cells stable across both test folds** — more data alone doesn't fix regime-conditional alpha

Confirms: the path forward is new detector types (exhaustion / first-pullback per `doc/exhaustion-detector-spec-2026-05-26.md`), not policy refit.

---

## 1 · Setup

**Trigger**: qveris backfill extended CN futures 60min/15min from ~1-2 years (TqSdk free-tier 10000-bar cap) to 14 years (2012 onward for major SHFE/DCE/INE/CFFEX symbols).

**Caveat — CZCE 4 symbols (TA/MA/CF/SR)**: qveris THS subscription does NOT support CZCE codes (provider rejects with "input parameters error" even on documented example `SR2509.ZCE`). These 4 symbols still use the TqSdk shallow data (3-4y depth). Their multi_tf_context coverage in v2 is correspondingly thinner — flagged separately in per-symbol stats.

### Data coverage (per `/tmp/agent_b_coverage.log`)

| Symbol | daily bars | 60min start | 60min bars | 15min start | 15min bars |
|---|---|---|---|---|---|
| kq_m_cffex_if/ih/ic | 2519 | 2012-2015 | 10973-14938 | 2012-2015 | 43538-57812 |
| kq_m_cffex_im | 927 (listed 2022-07) | 2022-07 | 3716 | 2022-07 | 14864 |
| kq_m_shfe_rb | 2520 | 2012-01-04 | 16742 | 2012-01-04 | 64612 |
| kq_m_shfe_cu | 2520 | 2012-01-04 | 24200 | 2012-01-04 | 94104 |
| kq_m_shfe_au | 2520 | 2012-01-06 | 21222 | 2012-01-06 | 79158 |
| kq_m_shfe_ag | 2520 | 2012-05-10 | 28446 | 2012-05-10 | 106130 |
| kq_m_dce_m / i / j / jm / p / y | 2520 each | 2012-2013 | 10093-17266 | 2012-2013 | 38036-65202 |
| kq_m_ine_sc | 1978 (listed 2018-03) | 2018-03 | 18904 | 2018-03 | 69968 |
| **kq_m_czce_{ta,ma,cf,sr}** (NOT qveris-backfilled) | 2520 | **2020-06 (TqSdk cap)** | 10000 each | **2024-07 (TqSdk cap)** | 10000 each |

---

## 2 · Signal-count step-function

| Aspect | v1 (2026-05-24 backtest) | **v2 (2026-05-26 deep backfill)** | Δ |
|---|---|---|---|
| Total rows | 699 | **3024** | **4.3x** |
| Unique signals (symbol+date) | 233 | **1008** | **4.3x** |
| Date range | 2023-11-12 → 2026-04-21 (2.4y) | **2016-01-21 → 2026-04-21 (10y)** | **4.2x window** |
| Signals at h=20 | 233 | 1008 | 4.3x |

Per-symbol h=20 signals roughly scale with the depth gain — confirming that v1 was severely sample-starved, NOT regime-special.

---

## 3 · R4 key-cell comparison (horizon=20)

Bootstrap 95% CIs are 5000-resample with seed 42.

| R4 cell | v1 (n / mean / hit / CI) | **v2 (n / mean / hit / CI)** | R4 verdict status |
|---|---|---|---|
| **top pooled** | 103 / **-1.06%** / 48.5% / [-2.54%, +0.39%] | 506 / **+0.34%** / 52.8% / [-0.32%, +1.02%] | **SIGN-FLIPPED**. "CN tops negative" was a 2024-only artifact |
| **bottom pooled** | 130 / +2.58% / 60.0% / [+1.19%, +4.22%] | 502 / +1.50% / 57.2% / [+0.80%, +2.22%] | Holds direction; magnitude halved but still significant |
| **top+higher=supporting** (CN-top-supp-fade trigger) | 74 / **-1.59%** / 43.2% / [-3.32%, +0.02%] | 324 / **-0.10%** / 48.8% / [-0.99%, +0.82%] | **COLLAPSED to ~zero.** Rule weight 0.80 has lost statistical basis |
| **F8 = bottom+weakness** (F8-cn-no-boost basis) | 56 / +3.81% / 76.8% / [+1.74%, +6.38%] | 306 / **+1.19%** / 57.5% / [+0.26%, +2.14%] | Weakened 3x but CI still excludes zero — rule still defensible but at lower magnitude |
| **CN-B1 = top+higher=opposing** (R3 boost candidate) | 20 / +2.51% / 80.0% / [-1.14%, +5.34%] | 147 / +1.12% / 59.9% / [-0.03%, +2.33%] | Sample now adequate (n=147); CI just barely touches zero; weak positive only |

### 3.1 Interpretation

The R4 verdict was derived on a sample that turned out to be:
- 4.3x smaller than today's
- Time-window-restricted to a single bull→bear→bull mini-regime (Nov 2023 → Apr 2026)
- Subject to all the issues that 2.4y backtest windows typically have

Deep data exposes that most R4 magnitudes were inflated by **regime selection** (the 2.4y window happened to overweight regimes where R4 patterns were strongest).

---

## 4 · Walk-forward K=3 on v2 deep data

Three chronological chunks, ~336 signals each at h=20:
- chunk[0]: 2016-05 → 2019-12
- chunk[1]: 2019-12 → 2023-07
- chunk[2]: 2023-08 → 2026-04

| Cell | fold1 (train chunk[0], test chunk[1]) | fold2 (train chunks[0,1], test chunk[2]) | Both folds ≥+10pp? |
|---|---|---|---|
| top+supporting | train +0.62% / test +0.26% (both positive, mean opposite to rule expectation) | train +0.42% / test -1.02% (slight neg) | **NO** |
| F8 (bot+weakness) | train +1.67% / **test -0.30%** (fold1 test fails) | train +0.59% / **test +2.85%** (71% hit, n=82) | **NO** (still fold2-only) |
| CN-B1 (top+higher_opposing) | train +1.00% / test +0.79% | train +0.91% / test +1.94% | **NO** (uplift always <+10pp) |
| top all | train +0.91% / test +0.34% | train +0.63% / test -0.25% | NO |
| bottom all | train +2.03% / test +0.34% | train +1.18% / test +2.11% | NO (uplift <+10pp) |

**Walk-forward verdict**: **0 cells stable across both test folds on deep v2 data.** Identical to v1 walk-forward verdict. *More sample ≠ regime stability.*

This confirms the methodology lesson from the 2026-05-25 walk-forward analysis: **more historical data does NOT convert regime-conditional alpha into durable alpha.** The patterns are regime artifacts; throwing 4.3x sample at them just sharpens the CIs of regime-specific magnitudes.

The implication is **structural**: divergence-only analysis on daily MACD can't escape its regime sensitivity. To find durable alpha, **new detector types** are required (exhaustion / first-pullback per spec).

---

## 5 · Recommended actions

### 5.1 Immediate (low-risk)

**(a)** Update `engine/divergence/downstream_policies.py::_apply_cn_futures` CN-top-supp-fade rule's docstring/reason to reflect deep-data weakening. Add a comment noting v2 (n=324, mean -0.10%) collapses the v1 (n=74, mean -1.59%) basis. The rule weight 0.80 is no longer supported by current evidence.

**(b)** Update `engine/divergence/downstream_policies.py::_apply_cn_futures` F8-cn-no-boost docstring to reference the new v2 stats (n=306, mean +1.19%, CI [+0.26%, +2.14%]) instead of v1's +3.81%.

**(c)** Update memory `project_cn_policy_oos_validated.md` to flag that v1-era OOS validation was on the 2.4y sample; the deep v2 reduces magnitudes substantially.

### 5.2 Policy decision points (need user input — high-impact)

Three choices for CN-top-supp-fade rule:

| Option | Action | Rationale |
|---|---|---|
| **D1** | **Remove rule** (revert to pass-through 1.00 for top+supporting) | Deep data shows mean -0.10%, CI [-0.99, +0.82] — no statistical basis for de-weighting |
| D2 | **Reduce weight 0.80 → 0.95** (mild de-weight, soft signal) | Compromise: deep data shows direction still slightly negative + fold2 mildly negative; keep advisory effect |
| D3 | **Keep 0.80, treat as regime-conditional** | Bet that future regimes will resemble fold2 (post-2023) more than the long average |

Recommendation: **D1** is statistically clean. D2 if you want to "anchor" some priors-based skepticism toward CN tops in supporting trends. D3 is hardest to justify post-deep-data.

F8-cn-no-boost is fine as-is (still positive significant); doesn't need policy weight change but description should be updated.

### 5.3 Strategic implication

This confirms the **detector-vs-filter dichotomy** baked into the recall-first paradigm (memory `project_recall_first_paradigm`):
- The sweet-spot pool finder + R4 / OOS / walk-forward family operates on **filter tuning**
- 4.3x sample didn't move walk-forward stability from 0 → anything
- **The available alpha lives in new detector types** (exhaustion catches 30-35% blind spot; first-pullback catches 67-77%)
- Continued sweet-spot tuning is diminishing returns; detector R&D is the multiplier

---

## 6 · R5 codex review packet (suggested next)

Recommend triggering a Codex R5 review with the following packet:
- `doc/cn-b-topology-deep-2026-05-26.md` (this doc) as primary evidence
- `src/data/review/cn_b_topology_signals_all_v1.csv` and `…_v2.csv` for verification
- Specific questions:
  1. Validate v1 vs v2 sign-flip on top pooled — is this real or methodology artifact?
  2. Confirm CN-top-supp-fade weight 0.80 → 1.00 (D1) recommendation
  3. Validate F8-cn-no-boost magnitude weakening — does it imply weight reduction or maintain 1.00?
  4. Check whether v2 deep-data walk-forward 0 stable cells is itself a sample-size issue or a structural ceiling

---

## 7 · Files

- `src/data/review/cn_b_topology_signals_all_v1.csv` — 699 rows (2.4y, restored from commit `vmqoxwtktvum`)
- `src/data/review/cn_b_topology_signals_all_v2.csv` — 3024 rows (10y, this run)
- `src/data/review/cn_b_topology_signals_all.csv` — current (= v2)
- `/tmp/agent_b_coverage.log` — per-symbol data depth table
- `/tmp/agent_b_v2_backtest.log` — full backtest stdout
