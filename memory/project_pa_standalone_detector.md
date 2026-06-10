---
name: project-pa-standalone-detector
description: "PA H2 bottom detector — standalone backtest results across CN pools; corrected gap-fix numbers 2026-06-03"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

PA standalone bottom detector shipped 2026-06-02. Tests H2+quality patterns WITHOUT MACD divergence state (recall expansion target).

**Core design**: `engine/divergence/pa_detector.py` — `PABottomDetector` class scans daily bars for Brooks H2 pattern: h_leg_count≥2 + bar_quality_bull≥0.3 + ema_distance<0. Outputs `PASignal` with `higher_tf_relation` and `recent_climax_max_5`.

**Methodology correction (2026-06-03)**: Base scan was using `min_gap=10` — same bug fixed in bpull 2026-06-02. Original K=2 numbers (F1=+1.000R, F2=+0.672R, n=8/14) were inflated by signal undercounting. Corrected methodology uses `min_gap=1` + `_apply_config_filter_with_gap()` post-filter.

**Corrected WF results (backtest_pa_standalone.py, gap-fix, stop=1.5×ATR):**

| Pool | Config | n | IS EV | F1 EV | F2 EV | F3 EV | Verdict |
|------|--------|---|-------|-------|-------|-------|---------|
| CN_METAL | h2+q03\|h=opp | 96 | -0.095R(n=39) | +0.348R(n=23) | +0.373R(n=34) | — | monitoring |
| CN_METAL | K=3 h2+q03\|h=opp | 96 | -0.095R(n=39) | +0.348R(n=23) | +0.682R(n=16) | +0.097R(n=19) | monitoring |
| CN_METAL | h3+q03\|h=opp | 41 | -0.168R(n=16) | +0.818R(n=11) | +0.403R(n=14) | +0.023R(n=9) | marginal |

Per-symbol CN_METAL h2+q03|h=opp: cu=+0.722R(n=18), au=+0.269R(n=18), rb=+0.154R, sc=-0.098R, ag=-0.071R.

**Why PA works for metals but not agri**: Metal futures have cleaner reversal bars (strong bodies, defined ranges). Agricultural commodities have higher noise-to-signal ratio for H2 patterns.

**Integration policy** (in `PABottomDetector.policy_weight()`):
- cn_metal_futures + h=opposing: weight=0.75 (monitoring — OOS all positive but IS negative, F3 marginal)
- cn_futures (mixed): weight=0.55 (not validated)
- czce / cn_agri: weight=0.0 (SUPPRESSED — negative OOS confirmed)

**Why:** All 3 OOS folds positive even after gap-fix correction. IS being negative is acceptable for a monitoring-grade detector. cu and au are the drivers; sc and ag drag.

**How to apply**: Supplementary recall detector for cn_metal_futures bottoms. Do NOT apply to czce or cn_agri. Always route through `PABottomDetector.policy_weight()`. Production promotion criteria: OOS EV ≥ +0.30R per fold with n ≥ 30 — currently borderline (F3=+0.097R).

Relates to [[project-pa-integration-plan]], [[project-cn-metal-pool]], [[project-cn2-gate]].
