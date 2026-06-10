---
name: regime-gate-not-portable
description: regime gate 不是普适工具，bottom-reversal lane 不能套 trend filter（实测 SMA200 gate 对 pa_h2 CN_METAL 净 -10 to -19R）
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

不要假设 regime gate（SPY/SMA200/realized-vol 类）可以从一个 lane 移植到另一个 lane。**Bottom-reversal lanes 与 trend filter 互斥**。

**Why:** 2026-06-09 测试三种 regime gate 套到 pa_h2 CN_METAL 想救 2022 -1.77R 副作用：
- SPY-based gate（直接套现有 us_regime_gate）：救 2022 +2.38R but 2025 -2.60R，净 +1.35R 但 unstable
- CN composite SMA200：**净 -19.17R**，2024 (lane best year) 被砍 30%
- Per-symbol 200dma：**净 -10.16R**，2024 砍半

3 种都失败。**根因**：pa_h2 是 bottom-reversal signal——它 by design 在 price 低于 trend 时 fire。用 "below SMA200" filter 等于关掉 lane。SPY-gate 救 US H2 family 是因为 US lanes (context_a, pa_us_60min) 是 ≤5 天 short reversal，2022 bear 中 high false-positive，不是同种 lane。

**How to apply:**
- 用户问"能不能给 X lane 加 regime gate"时，先问：
  - X lane 是 reversal 还是 trend-following？reversal lanes 慎用 trend filter
  - X lane 的好年份 trades 集中在什么 regime？看 by-year breakdown 在 risk_off 期 的 sum——如果好年份 trades 落在 risk_off 期，gate 会砍掉它们
- 不同 lane 在同 regime 反应不同：pa_us_dif_pos 2022 +0.94R（DIF>0+h=opp 自带 filter），pa_us_60min 2022 -9.5R——同样市场，不同 lane 体感相反
- "regime gate" 只在 sustained chop / multi-week panic 场景上才有 ROI（US 2022 stuck 全年 risk_off），不要为单 year 单 lane 的 -1.77R 引入复杂度
- 跨市场 portable 的 signal 极少；CN_METAL / US / CN_BOND 各自需要不同 regime detector，不要复用
- 相关：[[broad-market-defensive-h2-suppress]] 是反例（structural 排除）；this lesson 是 procedural（gate timing）
