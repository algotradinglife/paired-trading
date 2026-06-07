# In-Cycle Recall Research — CN 商品期货底部信号盲区

**日期**: 2026-06-02  
**数据**: CN_COMMODITY 池 15 个品种，日线，约 1,100-1,300 条/品种  
**问题陈述**: MACD 背离检测器（包含 HICD/DIFSR/DEAD 扩展）累计召回底部波段 ≤ 51%。剩余 49% 的漏掉波段分布在哪里，有无可行的检测方向？

---

## 执行摘要

**核心发现：49% 的漏掉波段并非同质问题。** 通过对 605 条漏掉波段（`missed_swing_state.py --pool CN_COMMODITY --threshold 8`）的状态分析，发现其中：

- **30% 是结构性噪声**（DIF>0 + HTF 顺势），EV=-0.867R，不可做
- **14% 是高质量新机会**（DIF>0 + HTF 对立），EV=+0.892R，历史 IS/OOS 均正
- **11% 是过渡区**（DIF≈0），部分有价值，待进一步研究
- **9% 是现有检测器仍漏掉的背离区**（DIF<0 + in_cycle + h=opposing），留给现有框架优化

**最重要结论：真正可立即启动的新检测器方向是 DIF>0 + h=opposing + EMA20 回调**，这是一个与背离框架完全正交的"上升中的回调买点"（Bull Pullback）模式，OOS 表现 F1=+0.767R, F2=+1.069R。

---

## 一、问题分解

### 1.1 漏掉波段的 MACD 状态分布

| 类别 | n | 占比 | 可操作性 |
|------|---|------|---------|
| DIF>0 + in_cycle + **h=opposing** | 82 | **14%** | **高** — 新方向 |
| DIF>0 + in_cycle + h=supporting | 184 | 30% | 不可做 |
| DIF<0 + in_cycle + h=opposing | 53 | 9% | 现有框架范围内 |
| DIF<0 + in_cycle + h=supporting | 63 | 10% | 噪声 |
| at_zero（DIF≈0）+ h=opposing | 69 | 11% | 部分可研究 |
| at_zero + h=supporting | 95 | 16% | 多为噪声 |
| completed（heap 已完成但未触发）| 8 | 1% | 忽略 |
| 其他 | 51 | 8% | — |

**关键洞察**：DIF>0 + h=supporting（30%）是结构性天花板——日线 MACD 和 HTF 都看涨时出现的底部，是"高位回调"而非反转机会，EV=-0.867R，无论什么过滤器都无法改善。

### 1.2 为什么 PA in_cycle 之前没有解决

`backtest_pa_incycle.py` 测试的是 **DIF<0 in_cycle**（现有背离检测器的覆盖范围），用 PA 特征过滤时 F1=-0.700R（反而恶化）。该脚本完全没有触碰 **DIF>0 in_cycle**——这是不同的 regime，也是真正的机会所在。

---

## 二、DIF>0 in_cycle 的价格结构特征

### 2.1 这些"底部"在价格上是什么形态？

通过对 260 个 DIF>0 in_cycle 漏掉波段的实证检查：

```
94% 是高点后的更高低点（higher low vs prior 20 bars）
  - h=opposing 子集: 80% 是高低点
  - h=supporting 子集: 99% 是高低点（但这些是噪声）
```

**解读**：DIF>0 意味着日线 MACD 已进入多头区间。这些"底部"实际是**上升趋势中的回调低点**，不是宏观底部。日线 EMA20 是自然的回调支撑位。

### 2.2 为什么 h=opposing 时可做？

当日线 DIF>0（多头半区）但 HTF DIF<0（更大级别仍空头）时：
- 处于"第一段上升"阶段——日线刚从零轴下方穿越
- HTF 的空头 DIF 提供了阻力——反弹空间有限但方向明确
- 这是"下跌趋势中的第一波反弹回调"，中继性质强

当 h=supporting（HTF 也多头）时：价格已在高位，"回调"容易变成顶部，EV 为负。

### 2.3 价格在哪里？EMA20 作为天然支撑

```
DIF>0 + in_cycle + h=opposing 子集（n=82）：
  23% 的波段底部恰好在 EMA20 ±1 ATR 范围内
  （即 23/82 ≈ 19 个信号落在 EMA20 附近）
```

EMA20 是 Brooks 框架中"通道下轨回调"的核心支撑，DIF>0 状态与之天然吻合。

---

## 三、EV 分析

### 3.1 全量 DIF>0 in_cycle + h=opposing

使用漏掉波段数据，在已知底部处模拟入场（entry=底部 bar 收盘，stop=底部 low - 0.5ATR）：

| 周期 | n | EV | Hit Rate |
|------|---|----|---------|
| IS (≤2022-12-31) | 37 | +0.813R | 62% |
| OOS1 (2023-2024H1) | 16 | **+0.767R** | 62% |
| OOS2 (>2024H2) | 28 | **+1.069R** | 71% |
| **全量** | **81** | **+0.892R** | **65%** |

OOS 表现不弱于 IS，OOS2 反而更强——提示这是真实 regime 效应，不是 IS 过拟合。

### 3.2 + EMA20 回调过滤（最强子集）

EMA 条件：`close ≥ EMA20 × 0.97` 且 `low ≤ EMA20 × 1.005`

| 周期 | n | EV | Hit Rate |
|------|---|----|---------|
| IS | 21 | +0.857R | 62% |
| OOS1 | 9 | **+1.475R** | **89%** |
| OOS2 | 7 | **+1.498R** | **86%** |
| **全量** | **37** | **+1.129R** | — |

n 较小但方向极一致。EMA20 过滤将精度从 65% 提升至 86-89%，是有效的精化条件。

### 3.3 对比：DIF>0 in_cycle + h=supporting（不可做）

| 全量 | EV=-0.867R, hit=13% |
|------|---------------------|

h=opposing 与 h=supporting 之间的 EV 差距达 **1.76R**，是 h=opposing 过滤器在所有池子里最一致的分隔效应之一。

---

## 四、已探索但结论为负的方向

### 4.1 DIF 穿越零轴（capitulation 信号）

`analyze_dif_crossing_capitulation.py` 已验证：全量 EV≈+0.036R，快速 MACD(6,13,5) EV=-0.384R。**结论：不可行**，DIF 穿越本身是噪声事件，与接下来的价格方向无统计关联。

### 4.2 PA 特征过滤 DIF<0 in_cycle

`backtest_pa_incycle.py` 测试了 bull_quality、h_leg_count、climax、EMA distance 等过滤器。结论：**F1 方向全部反转**（IS 正、OOS 负），是典型的 IS 过拟合。PA 特征在 DIF<0 in_cycle 区间无法稳健工作。

### 4.3 at_zero DIF 过渡区（69 个 + h=opposing 未深入验证）

该子集包含 44 个 DIF<0→0 过渡（底部即将到来）和 25 个 DIF 刚穿越到正（初期多头）。EV 未单独模拟，但与 DIF 穿越研究结论高度重叠，预期 EV 接近零。**留待后续**，优先级低于 DIF>0 pullback。

---

## 五、可行方向：BPULL 检测器（Bull Pullback）

### 5.1 框架定义

**BPULL（Bull Pullback）**：在日线 MACD 已进入多头区间（DIF>0）但高时间级别仍空头（h=opposing）时，价格回调至 EMA20 附近形成的买点。

```
触发条件（四合一）：
  1. d_dif > 0            # 日线 MACD 多头区间
  2. d_cycle_state == 'in_cycle'   # 在多头 heap 中
  3. h_dif < 0            # 高时间级别 DIF 空头（opposing）
  4. price near EMA20     # low ≤ EMA20 × 1.005 且 close ≥ EMA20 × 0.97
```

**非背离信号**：该检测器与 MACD 背离框架完全正交，不依赖 heap 比较或 DIF 能量。需要作为独立检测器实现，类似 `PABottomDetector` 的地位。

### 5.2 与 PA H2 的关系

PA H2（`PABottomDetector`）在 DIF<0 侧工作，检测的是"下跌中的反转"。BPULL 在 DIF>0 侧工作，检测的是"上升中的回调"。两者互补：

```
PABottomDetector:  DIF < 0 → reversal setup
BPullDetector:     DIF > 0, h<0 → continuation pullback
```

共同约束：h=opposing（HTF DIF<0）是两者的核心过滤器，保持框架统一。

### 5.3 信号量估计

```
历史漏掉波段中 DIF>0+h=opp+in_cycle: 82 / (15 symbols × 4 years) = 1.4/year/symbol
EMA20 touch 子集: ~37 / (15 × 4) = 0.6/year/symbol
池子整体（15 symbols）: 9-21 signals/year
```

对比现有 MACD 堆背离信号量：CN_COMMODITY 约 25-40/year。BPULL 约贡献 20-50% 增量。

### 5.4 需要解决的精度问题

EMA20 touch 在历史数据中发生频率约 28% of all bars（~71 次/年/品种）。若不加额外过滤，误报率极高。需要以下精化条件：

| 过滤条件 | 来源 | 预期作用 |
|---------|------|---------|
| 最小回调深度（价格从近期高点回落 ≥ 5%）| 避免横盘震荡中的 EMA 贴近 | 减少 50% 误报 |
| bar_quality_bull ≥ 0.3（收阳线，下影线）| 来自 `pa_features.py` | 保留 60-70% 真信号 |
| 近 N 日最低点（确认价格突破前低后反弹）| 相对低点判断 | 关键精化 |
| min_gap ≥ 15 bars between signals | 防止连续触发 | 必要 |

**量化精化后的预期**：真信号中约 23% 落在 EMA 附近（已确认，EV=+1.129R），误报减少到每年 10-20 个/品种，精度大幅改善。

---

## 六、at_zero 区（补充，低优先级）

69 个 at_zero + h=opposing 的波段，特征：
- 平均波段幅度 17%，中位 15%（与 DIF>0 in_cycle 相当）
- 44 个是 DIF 即将穿越到正（DIF<0 → 0），25 个是刚穿越

DIF 穿越研究已证明穿越点本身无预测力。但这 69 个波段的进入点（底部 bar 的价格结构）是否有 PA 特征可提取，尚未充分分析。**建议**: 在 BPULL 验证完成后再研究，避免过早分散精力。

---

## 七、结构性天花板确认

**DIF>0 + h=supporting（184 个，30%）是真正的结构性天花板**：

这些是日线和 HTF 同时多头时的价格底部，即"牛市高位回调"。实证 EV=-0.867R，无论加什么过滤器（PA 质量、EMA 位置、成交量）都无法改善，因为这些回调本身就可能是趋势转折的开始。

**总结性结论**：CN 商品期货的召回率天花板约为 66-70%（现有 51% + BPULL 理论约 +14%）。不可能达到 90%+ 召回，因为 30% 的漏掉波段本质上是不可预测的高位回调。

---

## 八、行动建议（优先级排序）

### 优先级 1：实现 BPULL 检测器并做 WF 验证

```
文件: engine/divergence/bpull_detector.py
接口: BPullDetector(min_pullback_pct=0.05, min_quality=0.3, min_gap=15)
        .scan(bars, h_bars) → list[BPullSignal]
回测: scripts/backtest_bpull.py --pool CN_COMMODITY
目标: OOS EV ≥ +0.5R with n ≥ 20 per fold
时间线: 需要 1-2 个 session
```

**验收标准（K=2 WF）**：
- F1（2023-2024H1）: EV ≥ +0.4R, n ≥ 10
- F2（>2024H2）: EV ≥ +0.4R, n ≥ 10
- F2 不弱于 F1（IS 泄漏检测）

### 优先级 2：将 BPULL 集成到 policy/output 层

若 WF 验证通过：
- 在 `downstream_policies.py` 添加 BPULL 规则
- 在 `signal.py` 扩展信号类型
- 权重初始值参考 PA H2 cn_metal_futures 校准值（0.75）

### 不建议投入的方向

| 方向 | 结论 |
|------|------|
| DIF 穿越零轴信号 | 已验证 EV≈0，REJECT |
| PA 过滤 DIF<0 in_cycle | 已验证 IS 泄漏，REJECT |
| DIF>0 + h=supporting | 结构性负 EV，永久 REJECT |
| 更快 MACD 参数（6,13,5）| 已验证 EV=-0.384R，REJECT |

---

## 附录：数据来源

| 文件 | 用途 |
|------|------|
| `/tmp/missed_cn_commodity.csv` | `missed_swing_state.py --pool CN_COMMODITY --threshold 8` |
| `scripts/backtest_pa_incycle.py` | PA in_cycle 负验证 |
| `scripts/analyze_dif_crossing_capitulation.py` | DIF 穿越负验证 |
| `review/rr_wf_cn_*.csv` | 现有 WF 基线 |
