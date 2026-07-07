---
name: us-premium-lane-harness-ready
description: US 期权 premium lane harness 已就绪（OCC 精确到期选约 + 排除规则），SPY 冒烟通过（仅管道验证）；信号验证等 GLD/GDX 数据（t_6eae7583）
metadata: 
  node_type: memory
  type: project
  originSessionId: bfb52110-df3c-4deb-b492-f1526868a5c8
---

2026-06-13（t_aa79fb13 完成）：eval_tbreak_premium 支持 US lane。

- 符号路由：CN 短代码 vs US ticker（scan US 池白名单），US 走 `scan --pool US`（us_equity 校准在 scan 侧）
- 排除：`US_EXCLUDED_BROAD_DEFENSIVE = {SPY, DIA, XLU, XLP, XLV}` 默认拒绝信号 lane（[[broad-market-defensive-h2-suppress]]）；`--allow-excluded-us` 仅冒烟放行且记入 report params
- US 选约：`_pick_us_contract_for_event` 用 OCC 精确到期（`select_expiry_exact`，>=14d 最近到期，同月 weekly 可区分）；CN 月规则不适用 US（codex P2 教训）
- option_store US OCC seam（data-engineer t_e7fb18c9）已交付：catalog/coverage/load_contract_daily + `load_contract_greeks()`（仅 SPY 有 greeks 伴生文件）
- SPY 冒烟：11 事件全评估 0 skip，tick 实测 0.01——**仅管道验证，SPY 仍在信号 lane 排除名单，不得引用其 EV 作信号证据**

下一步：GLD/GDX 期权数据交付（t_6eae7583）后跑真正的 US put 信号验证；review 卡 t_71b0beb1。
相关：[[project_put_side_xiao_direction]]
