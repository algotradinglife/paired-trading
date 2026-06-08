# PA tlt h=opposing 异常诊断 — 2026-06-08

Followup to `pa_policy_validation_2026-06-08.md`：US daily 池 10 个 symbol 里 tlt 在 `h_rel=opposing` 上 n=27 EV **-0.519R**，是同池最低。其他 ETF h=opp 全部 ≥ -0.20R。本份判定：单一 regime artifact 还是结构性失效？

数据来自 `/tmp/pa_us_k3.csv`（pa_us_k3, US daily, 996 trades, K=3 fold）。

## 一句话总结

**结构性失效**：4 个 fold 全负、5 个 cohort 年里 4 个全负、stop-out 占比 74%。建议在 `pa_detector.policy_weight()` 里把 `tlt` 显式 suppression 到 weight 0。

## tlt h=opp 总览

| 指标 | 值 |
|------|---|
| n | 27 |
| EV | **-0.519R** |
| hit% | 15% |
| -1R stop-out 占比 | 20/27 = **74%** |
| 正 R 单 | 4/27（4 个 +1.5R 全部在 2021 / 2024 / 2026 单点） |
| 时间跨度 | 2021-08 至 2026-04 |

## 1. 年度分布（regime 检查）

| year | n | EV | hit |
|------|---|----|-----|
| 2021 | 3 | +0.167 | 33% |
| 2022 | 5 | **-1.000** | 0% |
| 2023 | 7 | **-0.857** | 0% |
| 2024 | 3 | -0.167 | 33% |
| 2025 | 7 | **-0.500** | 14% |
| 2026 | 2 | +0.250 | 50% |

2022/2023/2025 三年全部为深度负 EV、零或近零命中。**不是单一 regime artifact**——2022 加息周期 + 2023 收益率冲高 + 2025 继续负 EV 跨越了至少 3 个不同的宏观环境。

## 2. K=3 fold 分布（OOS 检查）

| period | n | EV | hit |
|--------|---|----|-----|
| IS    | 8 | -0.562 | 12% |
| OOS1  | 7 | **-0.857** | 0% |
| OOS2  | 3 | -0.167 | 33% |
| OOS3  | 9 | -0.333 | 22% |

**全 4 fold 负 EV，无单 fold 救场**。OOS1 极端（n=7 全亏），即便去掉 OOS1，剩余 20 单 EV 仍 -0.400R。

## 3. DIF 极性切片

| dif_pos | n | EV | hit |
|---------|---|----|-----|
| DIF<=0 | 18 | -0.667 | 11% |
| DIF>0  |  9 | -0.222 | 22% |

DIF>0 子集稍好但仍负；DIF<=0 是主要拖累。无法靠 DIF 极性救。

## 4. weekly_up 切片

| weekly_up | n | EV | hit |
|-----------|---|----|-----|
| False | 17 | -0.50 | 18% |
| True  | 10 | -0.55 | 10% |

周线方向无信息——both 负。

## 5. confidence × bar_quality_bull

- confidence × r 相关：**+0.03**（无信号）
- bar_quality_bull × r 相关：+0.12（弱）
- conf >0.7 子集 n=2 EV -1.0；conf 0.5-0.7 子集 EV -0.227（仍负）
- bar_quality_bull 三档 EV 全部 < -0.44

**高 confidence / 高 bar quality 没有救回 EV**——证明 PA H2 在 tlt 上不只是 noise，是 systematically miscalibrated。

## 结论与建议

| 检查 | 结果 |
|------|------|
| 年度全负？ | 2022/23/25 全 ≤ -0.5R，仅 2021/24/26 (n=3+3+2) 微正/低单量 |
| Fold 全负？ | ✅ 4/4 fold 负 |
| 单一 regime？ | ❌ 跨利率上行(22)、债市震荡(23)、降息周期(25) 均负 |
| confidence 救场？ | ❌ corr=0.03 |
| 子集救场？ | ❌ DIF / weekly_up / bar_quality 均无可分割正 cell |

**Verdict: kill_lane**。tlt 在 PA H2 体系下 5 年内 4 fold 全负、跨多个宏观 regime 仍稳定 -0.5R、74% 触发结构止损，属于策略层面的不适配（长债 microstructure 与 PA H2 的 swing-bottom 信号假设冲突）。

## 推荐 Phase B 改动

在 `pa_detector.policy_weight()` 里添加 `tlt` 显式 suppression：

```python
# us_equity 池里，tlt 长债 PA H2 失效，n=27 EV-0.519R 4/4 fold 负
if symbol == "tlt":
    return 0.0
```

或更通用：把所有 US 长债 ETF（tlt / tlh / iei / ief / shy）放进 suppress list，等价于 `czce/cn_agri` 0.0 那条规则。

## 代码

- 输入：`/tmp/pa_us_k3.csv`（pa_us_k3，US daily，996 trades）
- 分析：`pandas` ad-hoc（27 行 tlt × opposing 子集）
- 输出：本文件
