# macd-momentum 信号回测结果审查报告 — 2026-05-23

## 方法论审计总结

### 代码审计：Lookahead 与数据泄漏

#### ① higher_tf (weekly) Lookahead 分析
**判定：无泄漏（安全）**

`enrich_with_higher_tf` 使用 `_state_at_signal(bars, signal_t, grace=0)` 来切片：
```python
cutoff = signal_t + grace  # grace=0 for higher_tf
sliced = bars[bars["timestamp"] <= cutoff]
```

关键发现：Polygon 的 1W 周线 bar 的 timestamp 是 **Sunday 04:00 UTC**（美国东部时间周日 00:00，即周线收盘日）。而日线信号的 signal_t 总是在 **周一到周五** 的工作日。因此：

- 当前周（含 signal 的那一周）的周线 timestamp = 周日 > 周五 > signal_t → **被排除**
- 上一周（已完成的完整周）的周线 timestamp = 上周日 < signal_t → **被包含**

结论：`compute_level_state` 始终使用上一周的完整周线数据，不存在未来数据泄漏。代码注释也正确反映了这一点（"the most recent weekly bar reflects what was knowable then"）。

#### ② lower_tf (60min) Grace Window 分析
**判定：轻度泄漏（已知且可接受）**

`enrich_with_lower_tf` 使用 `intraday_grace_minutes=30`。若信号在 14:35 触发，则 `cutoff = 14:35 + 30min = 15:05`，会包含 14:00-15:00 的 60min 这根未收盘的 bar。该 bar 包含从 14:00 到 14:35 的数据（约 58% 的 bar 已收盘），泄漏量约 30 分钟。文档已标注此设计，属于 intentional trade-off。

---

### 各 Finding 验证结果

#### Finding 1 — `top + lower_relation == lagging` 是稳定红区
**原始提法**: top 背离在 60min 已转空时不可靠 (45.5% hit, -0.93% avg / h=20)。更高一级的条件 `top+lagging+opposing(weekly)` 更差 (41.7%, -1.47%, n=36)。

**验证结果: ✅ SURVIVES（但统计显著性较弱）**

| 检查项 | 结果 |
|--------|------|
| Per-symbol count | 10 symbols 均有分布，无显著集中 (HHI=0.128) |
| Quarter distribution | 分散在 14 个季度，无暴风骤雨式集中 |
| Bootstrap 95% CI (opposing) | [-3.20%, +0.18%] — 包含零但偏负 |
| P(mean < 0) | 95.9% — 边缘显著 |
| Bonferroni (hit-rate≥50%) | p=0.878 → 不通过 |
| T-test (mean ≠ 0) | p=0.105 → 不通过 |

**判定理由**：模式方向正确（负收益），但统计上无法排除偶然性。作为一种规则性观察仍成立（红区确实偏负），但不属于高置信度发现。

---

#### Finding 2 — `bottom + leading + opposing` 是甜区
**原始提法**: 60min 仍空 + 周线仍空 + 日线底部背离 → 极高胜率 (n=15, 93.3% hit, +8.52% avg / h=20)

**验证结果: ✅ SURVIVES**

| 检查项 | 结果 |
|--------|------|
| Symbol breakdown | 10 symbols 均有分布 (HHI=0.120) |
| Year breakdown | 2022: 5次 (80% hit) / 2023: 3次 / 2024: 3次 / 2025: 3次 / 2026: 1次 |
| Drop top-2 winners | 从 +8.52% 降至 +6.95% — 仍强劲 |
| Median vs Mean | 7.22% vs 8.52% — 中等右偏，非极端 outlier 驱动 |
| Winsorize 5% | 从 8.52%→8.64%（无显著变化） |
| Winsorize hit-rate | 93.3%→93.3% |
| Bootstrap 95% CI | [5.40%, 11.67%] — 远高于零 |
| Bonferroni hit-rate test | p=0.000488 → **通过** |
| Bonferroni t-test | p=0.000126 → **通过** |

**判定理由**：所有稳健性检查均通过。即使去掉 top-2 winners、winsorize 极端值，信号模式依然强劲。Bonferroni 校正后仍然显著。n=15 偏小，但方向一致性和统计显著性足以支撑该发现。

---

#### Finding 3 — `candidate (conf 0.65-0.80) × opposing weekly` 100% hit
**原始提法**: 置信区间 0.65-0.80 + 周线反向 → 14/14 全胜 (100% hit, +6.13% avg)

**验证结果: ✅ SURVIVES（高度可疑但统计上成立）**

| 检查项 | 结果 |
|--------|------|
| Per-symbol | 8 symbols (HHI=0.143) |
| 相邻性检查 | 14 条全部是唯一 (symbol, week) 对 — 无 temporal clustering |
| De-dup (1/symbol-month) | 仍为 14 条 — 无冗余 |
| Winsorize avg | 从 6.13%→5.92% |
| Winsorize hit-rate | 100%→100% |
| Bonferroni hit-rate test | p=0.000061 → **通过** |
| Bonferroni t-test | p=0.000239 → **通过** |

**判定理由**：统计上极其显著（100% × 14 = p=0.000061），且通过所有稳健性检查。但 14/14 完美胜率本身在 alpha 挖掘中属于危险的完美信号（overfitting 风险）。n=14 仍偏小。结论：该模式真实存在但应随着数据增加重新验证。

---

#### Finding 4 — `top + leading + opposing` 效果意外不错
**原始提法**: 强多头（60m 多 + 周线多）中的日线顶背离 → 72% hit (h=20), 但 avg +0.91% 偏弱

**验证结果: ❌ COLLAPSES**

| 检查项 | 结果 |
|--------|------|
| Subtype 分布 | 全部为 `standard` (direction_gate 已过滤掉 hidden) |
| Return 分布 | min=-35.66%, p25=-0.87%, median=2.67%, p75=3.55%, max=12.80% |
| 小赢 (<2%) | 11/25 |
| 大赢 (>5%) | 3/25 |
| Winsorize avg | 从 +0.91% 变为 +2.06%（说明极端负值拉低了均值） |
| Bonferroni hit-rate | p=0.022 → 不通过 |
| T-test mean ≠ 0 | p=0.599 → **完全不显著** |
| 平均收益来源 | 收益均值受一只极端亏损 (-35.66%) 严重拖累；winsorize 后均值翻倍 |

**判定理由**：虽然 hit-rate 72% 看起来不错，但 (a) 不通过 Bonferroni 校正，(b) t-test 显示平均收益与零无显著差异，(c) 分布存在巨大的负偏 tail（-35.66% 的亏损）。这个盈利结构是高频小赢 + 偶尔巨亏，不构成可交易的信号模式。

---

### 五问 Codex 的答案摘要

#### Q1: higher_tf context 的 Lookahead
**答案：无泄漏。** 如上所述，周线 bar 的 timestamp 是 Sunday（收盘日），日线信号在工作日触发，已完成的上一周被正确使用。当前正在形成的周线 bar 不满足 `timestamp <= signal_t` 条件，被排除。

#### Q2: Winsorize 上下 5% 后的影响
**答案：强 findings (#2, #3) 不受影响。** Finding 2 从 8.52%→8.64%，Finding 3 从 6.13%→5.92%。Finding 1a（负收益）从 -1.47%→-1.22%（轻微改善）。Finding 4 从 0.91%→2.06%（说明负 tail 拉低了均值，winsorize 后反而改善）。

#### Q3: Herfindahl Index — 符号集中度
**答案：所有关注的 bucket 均无集中问题。** HHI 统一在 0.1058-0.1429 之间，接近完全均匀分布（10 符号均匀 HHI=0.100）。所有 bucket 都覆盖 8-10 个符号。Finding 2 即使 n=15 也覆盖了全部 10 个符号。

#### Q4: Bonferroni 校正 (α=0.05/30≈0.0017)
**答案：** Finding 2 和 Finding 3 通过 Bonferroni 校正（hit-rate 检验 + t-test 均通过）。Finding 1 和 Finding 4 不通过。具体：
- F2 h=20 hit: p=0.000488 ✅ | F2 mean≠0: p=0.000126 ✅
- F3 h=20 hit: p=0.000061 ✅ | F3 mean≠0: p=0.000239 ✅
- F1 hit: p=0.774 ❌ | F1 mean≠0: p=0.297 ❌
- F1a hit: p=0.878 ❌ | F1a mean≠0: p=0.105 ❌
- F4 hit: p=0.022 ❌ | F4 mean≠0: p=0.599 ❌

#### Q5: Direction_gate 校准 Cross-Check
**答案：方向门在当前数据集上表现正常。** 方向门的假设（顶部信号比底部差）在当前数据上保持一致：
- 顶部整体 hit-rate: 52.9% vs 底部 69.3%
- 顶部平均收益: -0.27% vs 底部 +3.17%
- 顶部低置信度 (<0.5): 73.6% (64/87) vs 底部 22.9% (41/179)
- 方向门对 hidden subtype 的 0 倍惩罚正确（当前数据中所有信号的 subtype 为 standard 或 weakness，无 hidden）

未检测到需要重新拟合的分布偏移。

---

### 代码中发现的其他方法论漏洞

1. **`compute_level_state` 使用 `iloc[-1]` 可能带偏** — 当 bars 被切片后（比如只到 signal_t），取最后一根 bar 的 `trend_side` 是正确的。但如果 `_state_at_signal` 返回了空数据（`len(sliced) < min_bars`），信号直接无标注通过，可能会导致数据不对称（早期信号无上下文，晚期信号有上下文）。

2. **60min lower_tf 的 30 分钟 grace window** — 会引入最多 30 分钟的轻度未来数据。如果一个信号在 14:35 触发，它会看到 14:00-14:35 的 60min bar 状态（该 bar 通常 14:00-15:00）。这是设计上可接受的折衷，但文档建议在 `higher_tf` 中检查，而不是 `lower_tf`。

3. **Finding 4 的 -35.66% 极端亏损** — 应检查这条信号是否来自异常市场事件（如 COVID/崩盘）。这个单点就能完全摧毁 Finding 4 的均值。

4. **信号独立性** — n=15 和 n=14 虽然通过覆盖度检查，但同一 symbol 的连续信号（比如 2022 年 SPY 的多个底部信号）可能存在序列相关性，降低有效样本量。建议使用 HAC (Newey-West) 标准误做进一步验证。

---

### 最终判定汇总

| Finding | 原始 Claim | 判定 | 置信度 |
|---------|-----------|------|--------|
| F1: top+lagging red zone | 45.5% hit, -0.93% avg | ✅ Survives | 中等（方向正确但统计弱） |
| F2: bottom+leading+opposing | 93.3% hit, +8.52% avg | ✅ Survives | 高（所有检查通过） |
| F3: candidate×opposing 100% | 100% hit (14/14), +6.13% | ✅ Survives | 高但需警惕完美胜率 |
| F4: top+leading+opposing OK | 72% hit, +0.91% avg | ❌ Collapses | 均值不显著，尾部风险主导 |

**结论**：Claude Code 的四个发现中，两个强模式（F2, F3）通过了所有验证检查且大幅超越 Bonferroni 阈值。F1 方向正确但统计边缘。F4 随着深入分析而崩塌。整体方法论扎实，没有发现未标注的泄漏问题。
