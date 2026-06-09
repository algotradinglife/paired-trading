# CN regime gate for pa_h2 CN_METAL — REJECTED 2026-06-09

回应 max_hold=30 部署后 2022 单年 -1.77R 副作用，测试三种 regime gate 思路是否能消除该代价同时保持其他年份收益。**结论：全部失败，不部署**。

## 动机

max_hold=30 deployment 在 K=3 OOS 累计 +23.39R 改进（已确认）。但 pa_h2 CN_METAL 2022 单年从 -0.84R 恶化到 -2.61R（-1.77R 代价）。希望加 CN-specific regime gate 救回 2022 同时保留其他年份。

## 2022 drag 微观结构

逐 trade 对比 mh20 vs mh30，2022 (n=29) Δsum = -1.77R：

**Per-symbol**：
- kq_m_shfe_cu: mh20 +1.71R → mh30 +2.38R  Δ **+0.67R** ✓ 改善
- kq_m_shfe_au: mh20 +0.18R → mh30 -1.12R  Δ -1.30R ⚠
- kq_m_shfe_ag: mh20 -0.29R → mh30 -1.03R  Δ -0.74R ⚠
- kq_m_ine_sc: mh20 -2.44R → mh30 -2.84R  Δ -0.39R

**根因**：max_hold 延长惩罚的是 au + ag（precious metals），cu 反而受益。**不是 broad CN_METAL bear**——是 2022 Fed 鹰派 → DXY 涨 → 贵金属跌的特定 regime。

## 测试 1：SPY-based gate 移植到 CN_METAL

直接套现有 us_regime_gate（SPY < SMA200 OR vol > 25%）到 pa_h2 CN_METAL：

| Year | n before → after | sum Δ |
|------|-----------------|-------|
| 2022 | 29 → 4 | **+2.38R** ⭐ 救回 |
| 2023 | 14 → 11 | +0.50R |
| 2024 | 13 → 13 | 0 |
| **2025** | 20 → 16 | **-2.60R** ⚠ |
| 2026 | 8 → 6 | +1.07R |

**Net +1.35R but 2025 -2.60R 是显著新问题**。SPY signal 不能 1:1 套到 CN markets——2025 H1 美股 risk_off 期 CN_METAL pa_h2 反而表现好。Mapping 失效。

## 测试 2：CN_METAL composite below SMA200

构造 4 symbol 等权 normalized composite，复算 SMA200：

```
2022 below_sma200: 48.6% of trading days
2023: 5.8%
2024: 14.3%
2025: 0.0%   ← 2025 metals 整年 above SMA200
```

| Year | n before → after | sum Δ |
|------|-----------------|-------|
| 2021 | 18 → 14 | **-4.29R** ⚠ |
| 2022 | 29 → 16 | **-6.44R** ⚠⚠ |
| 2023 | 14 → 12 | -0.50R |
| 2024 | 13 → 7 | **-7.93R** ⚠⚠⚠ |
| 2025 | 20 → 20 | 0 |
| 2026 | 8 → 8 | 0 |

**净 -19.17R 灾难**。最 ironic 是 2022 反而**更差**——composite gate 留下来的 16 笔 trade 比剔掉的更糟（-9.05R）。

## 测试 3：Per-symbol 200dma

每个 symbol 独立看自己的 SMA200：

| Year | n before → after | sum Δ |
|------|-----------------|-------|
| 2021 | 18 → 8 | +2.40R |
| 2022 | 29 → 14 | -0.75R |
| 2023 | 14 → 9 | **-3.33R** ⚠ |
| 2024 | 13 → 7 | **-6.50R** ⚠⚠ |
| 2025 | 20 → 10 | -1.97R |
| 2026 | 8 → 8 | 0 |

**净 -10.16R**。虽然比 composite 好（保住 2021 部分），但 2024 仍然被砍半（13→7），把最强年砍掉一半。

## 为什么所有 SMA200 gate 都失败？

**结构性原因**：pa_h2 **是 bottom-reversal 信号**——它 by design 在 price 低于 trend 时 fire。filtering "below SMA200" 等于过滤掉信号 designed-for 的 setup。

具体证据：
- 2024 是 pa_h2 CN_METAL 最强年（+11.55R）
- 所有 3 种 SMA200-based gate 都把 2024 砍 30-50%
- 这些"被砍"trades 是真正的高 R trades——bottom 在 200dma 下方爆发

**SPY gate 对 US H2 family 工作**因为 US 的 context_a + pa_us_60min 是 short-term 反弹信号 ≤ 5 天 holding；2022 持续 bear 中这种短反弹大量假阳。

**pa_h2 daily 是不同 lane**——更长 holding (avg 19+ bars)，更大 R distribution。它需要 bottom 才能 work，gate 把 bottom 过滤掉就等于关掉 lane。

## 决策

**保持 max_hold=30 全局默认不变**。2022 -1.77R 是真实但可接受代价：
- pa_h2 CN_METAL 全部 K=3 OOS PASS（+2.02R aggregate）
- 2022 -1.77R 跟 2023-2025 累计 +25.6R 比是 < 7%
- 没有 simple 信号能 attribute 2022 损失同时保留其他年份

## 重要 lesson（已 memory）

**不要假设跨市场 / 跨 lane 的 regime gate 可移植**：
- US gate signals (SPY 200dma + realized vol) 拿来套 CN_METAL → 半救半害
- 同 detector class 的 daily 版本（pa_h2 daily）和 60min 版本（pa_us_60min）对 regime 反应根本不同
- "bottom-reversal" lane 的本质要求 below-trend setup，与"trend filter"互斥

**Pattern**：当一条 lane 在某 regime 表现差时，先问"是该 regime 系统性 punishing 这条 lane，还是该 lane 的 winners 恰好分布在该 regime"。前者可 gate，后者不能。

## 累计 P0→P3 vs 本次

| 项目 | Result | Net R |
|------|--------|-------|
| P0 symbol exclusions | DEPLOYED | +25.16R |
| P1c broad-market suppress | DEPLOYED | +2R |
| P2 US regime gate | DEPLOYED | (eliminates -21.4R drag → +0.5R; 2022 救援核心) |
| **P2/A TP1 0.75R** | REJECT | (avoided -6.4R) |
| **P2/C dif_pos regime gate** | REJECT | (avoided -0.44R) |
| P3 max_hold=30 | DEPLOYED + K=3 MARGINAL PASS | +23.39R OOS |
| AGRI_POS dce_p exclude | DOCUMENTED (lane STALE) | scoped |
| **本次 CN regime gate** | **REJECT** | (avoided -10 to -19R) |

3 个 REJECT decision 累计避免 -17R 错误改动。**决策的负面收益 ≈ DEPLOYED 的正面收益**——分析价值与代码价值同等。
