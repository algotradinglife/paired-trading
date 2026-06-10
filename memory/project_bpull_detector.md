---
name: project_bpull_detector
description: BPullDetector shipped — DIF>0 EMA20 pullback for CN_METAL in-cycle recall; full-pool WF K=2 results
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

BPullDetector (Bullish Pullback) implemented 2026-06-02 as recall-expansion detector for DIF>0 in-cycle swings invisible to divergence detectors.

**Pattern**: daily DIF>0 + bar low touches EMA20 (within 0.5%) + HTF DIF<0 (opposing)

**Full-pool WF results (backtest_bpull.py, gap-fixed 2026-06-02)**:
- CN_METAL h=opposing K=2: IS=+0.171R(n=92), F1=+0.121R(n=71), F2=+0.419R(n=93)
- CN_METAL h=opposing K=3: IS=+0.171R(n=92), F1=+0.121R(n=71), F2=+0.348R(n=48), **F3=+0.495R(n=45)**
  - **K=3 STRONG PASS**, monotone F1→F3 — upgraded to production-grade
  - Drivers: au=+0.542R, cu=+0.242R, ag=+0.240R, sc=+0.149R
  - **rb EXCLUDED**: IS=+0.218R but OOS1=-0.448R/OOS2=-0.252R/OOS3=-0.240R; 56% stop rate; policy-driven
- CN_COMMODITY full pool: DCE agri drags (y=-0.292R, jm=-0.217R) — NOT actionable

**Policy routing**: cn_metal_futures h=opposing → **0.75** (K=3 production-grade); all others → 0.0

**rb 排除实现**：`policy_weight(sig, "cn_metal_futures", symbol="kq_m_shfe_rb")` 返回 0.0。模块级 `_BPULL_EXCLUDED_CN_METAL = frozenset({"kq_m_shfe_rb"})` 守门。不传 symbol 时向后兼容，调用方需自行过滤 rb。

**Files**: `engine/divergence/bpull_detector.py`, `scripts/backtest_bpull.py`

**Why:** DCE agri fundamentally rejects this pattern (price-support regime vs. technical); CN_METAL is technically driven — EMA20 pullbacks in bullish MACD are real setups.

**CN_BOND BPull test (2026-06-03, REJECTED)**: K=2 marginal pass (F1=+0.653R n=47, F2=+0.134R n=65), but K=3 F2=−0.064R fails. More critically: h=opposing provides no uplift in bonds (h=supporting EV actually higher). 10yr T-bond (t) negative in both sub-folds. Do not integrate; revisit when more data available.

**How to apply**: BPull is a CN_METAL-only detector. Do not route to cn_futures, cn_bond, or czce. Target expansion: retest CN_BOND K=3 when next OOS fold available.

[[project_pa_standalone_detector]]
[[project_missed_swing_analysis]]
