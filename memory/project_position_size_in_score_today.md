---
name: project_position_size_in_score_today
description: score_today 已集成仓位管理建议列 position_size，逻辑与回测仿真对齐
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

score_today 的信号表新增 `pos` 列（full/half/light/watch），通过 `_position_size(r)` 计算。

规则（按顺序应用）：
1. 基础分层：score 4→full, 3→half, 2→light, 1→watch
2. PA 相位限制：TR/TR_FORMING 时最高 half（full→half）；BEAR/UNCLEAR 直接 watch
3. 15m 确认降级：pa_15m_confirmed=False → 降一级（仅 CN_METAL PA H2 适用；None 不影响）

**Why:** 回测仿真已有相位分配（TR=0.5×）和止损保护，但 score_today 只有信号分层，仓位管理缺口通过此字段填补，让实盘执行与回测假设对齐。

**How to apply:** 下游执行系统直接读取 `position_size` 字段，不需要重新推算。JSON 输出也包含此字段（已写入 scored 列表）。

提交：c4168a57（2026-06-04）
