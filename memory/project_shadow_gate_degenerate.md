---
name: project_shadow_gate_degenerate
description: 影子信号棒质量闸门发布阈值曾退化(100%通过)；已冻结到验证中位 0.80/0.95(commit 50374717)真二分；晋升 active sizing 仍欠 OOS 数据
metadata: 
  node_type: memory
  type: project
  originSessionId: 005f43a7-d4cf-4949-a157-a5988754a6ae
---

`score_today` 中 shadow 落地的 advisory 信号棒质量闸门（`_signal_bar_quality` 的 `double_strong`，commit 057c81f / t_ffffa8fd）**部署阈值退化为 no-op**。

OOS/部署评估（2026-06-15, `scripts/eval_shadow_gate_oos.py`, doc/shadow-gate-oos-eval-2026-06-15.md）裁决：
- **Q1 退化**：发布固定阈值 body_frac>=0.5 / close_pos>=0.66 对 n=88 已结突破做多 trade **100% 通过**。全 3512 候选 **最小 body_frac=0.500、最小 close_pos=0.667**——阈值落在分布**地板**。突破候选生成器已强制该几何，故 `double_strong` 对每条候选恒 True，**零分辨力**。源发现用的是**中位分层** 0.8/1.0（分区 44.7/49/32.1%）才测到 +1.28R 合取效应。
- **Q2 无 OOS**：88 条已结 trade 全在 split=train；val/test 已结 trade=0/0。语料内无 OOS 伙伴，+1.28R 合取仍纯样本内（小 cell n=12）。

**Why**：固定绝对阈值天然不可移植（[[feedback_regime_gate_not_portable]]），且这里恰好被候选过滤条件包含 → 重测了已保证的条件。

**How to apply**：晋升 active sizing 前两步——(a) **已修复（commit 50374717）**：阈值冻结到验证中位 `body_frac>=0.80 / close_pos>=0.95`（close 用 0.95 非 1.0：样本内 close_pos 双峰，[0.95,1.0) 为空，0.95 对 live 收在最高价下一 tick 更鲁棒）；Q1 复跑 pass_rate 0.375、double_strong EV +1.284R 复现验证 cell。(b) **仍欠 OOS**：取 OOS 数据（score_today live 前向 shadow 累积，或建 data-engineer 卡补新品种/时段突破语料）再验证合取，方可入仓位。修阈值后 shadow 字段现真二分、有信息量，可累积前向证据；但仍样本内拟合，保持 ADVISORY。

源发现见 [[project_spec001_ev_eval]]；信号棒质量硬化 doc/signal-bar-quality-hardening-2026-06-15.md。
