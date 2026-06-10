---
name: project-vflush-detector
description: VFlushDetector — V形急跌底部 K=3 STRONG PASS for CN_METAL; cu/sc 驱动; 与 PA H2 90% 不重叠
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

VFlushDetector (Vertical Flush) 实现于 2026-06-03，针对 PA H2 覆盖盲区：召回缺口分析发现 75% 漏网底部 h_leg<2 且 bar_quality<0.1，是无经典 H2 结构的 V 形急跌后反转。

**Pattern**: DIF<0 + ema_distance_norm < -0.02 (深度低于 EMA20) + selling_climax_score ≥ 0.3（当前 bar，非回溯）+ h_leg_count ≤ 1 + min_gap=10

**关键发现**：lookback-only（回溯最近3bar的高潮）EV=-0.018R，当前bar触发 EV=+0.342R。`lookback_climax_thr` 默认设为 99.0 永久禁用回溯路径。

**WF K=3 结果 (backtest_vflush.py, CN_METAL h=opposing)**:

| 期间 | EV | n |
|------|----|---|
| IS (≤2022) | +0.255R | 32 |
| F1 (2023–2024H1) | +0.684R | 18 |
| F2 (2024H2–2025H1) | +0.101R | 14 |
| F3 (≥2025H2) | +0.341R | 13 |
| 全量 | +0.342R | 77 |

K=3 STRONG PASS — 全部4折正向。

**Per-symbol**: cu=+0.751R（主驱动），sc=+0.427R；ag=-0.015R、au=-0.357R（拖累）

**与 PA H2 重叠**: 仅 9.1%（77 信号中7个），是真正的召回扩展而非重复。

**Policy weight** (`VFlushDetector.policy_weight()`):
- cn_metal_futures + h=opposing → **0.65** (monitoring grade; cu/sc 强，ag/au 弱)
- cn_metal_futures + h=supporting → 0.30
- cn_metal_futures + h=neutral → 0.45
- 其他 instrument_class → 0.0（未验证）

**不排除 rb**（与 BPull 不同）——rb 在 VFlush 测试中没有系统性负值。

**集成状态** (2026-06-03):
- `scripts/score_today.py` ✅ score=3 for h=opposing
- `scripts/scan_portfolio_b.py` ✅ cn_metal_futures 独立于 MACD 早退
- `scripts/backtest_vflush.py` ✅ K=3 完整报告

**Files**: `engine/divergence/vflush_detector.py`, `scripts/backtest_vflush.py`

**Why:** PA H2 的 h_leg+quality 双重门槛屏蔽了真实的 V 形资本耗尽底——这类形态的信号在高潮分数，不在腿数。

**How to apply**: CN_METAL 专用。切勿路由到 czce/cn_agri（未验证，PA 同类在 agri 为负）。生产升级标准：cu/sc 以外再有一个 symbol F3>+0.30R，且整体 n/fold≥20。

[[project_pa_standalone_detector]]
[[project_bpull_detector]]
[[project_recall_first_paradigm]]
