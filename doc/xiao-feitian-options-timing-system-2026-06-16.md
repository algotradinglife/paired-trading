# 肖淳心《飞天期权择时》体系 — 操作逻辑与思路（2026-06-16）

**整理者**：researcher · **目标读者**：philosopher
**用途**：在现有 PA 复刻体系（标的信号层）之上，发展出一整套**期权决策链**并在权利金空间测试。
**配套阅读**：`doc/design/xiao_options_timing_design_2026-06-08.md`（工程模块设计稿）、
`doc/design/paired_options_direction_2026-06-10.md`（方向性盘点）、
memory `project_put_side_xiao_direction` / `project_ag_options_swing_findings` / `project_ddline_options_findings` / `project_options_entry_timing`。

> **可信度标注**：本文区分三类内容——
> ✅ **已确认/已实现**（repo 有代码或回测证据）；
> 🟡 **用户口述/设计推断**（2026-06 用户披露，待肖的视频/实盘截图最终确认）；
> ⬛ **黑盒**（机制存在但未形式化，需机制提取）。
> philosopher 设计决策链时请按标注分配「直接用 / 先验证 / 先提取」。

---

## 0. 一句话定位

> 用**标的分析**找潜在顶/底，用对应的**浅虚（shallow-OTM）naked call/put** 入场出场，
> 靠**期权凸性**获取相对标的腿的超额收益。方向依据来自肖老师（CN 期货实战，**偏重 put**）。

⚠️ 这是**方向性期权择时**（directional option timing），**不是 Delta 中性配对交易**。
风险靠**期权权利金 stop/take** 管理，不靠底层期货对冲，无组合 delta 汇总、无对冲腿、无动态再平衡。

---

## 1. 核心哲学：凸性赔付 + tick 级权利金止损（整个体系的命门）

肖式打法的本质不是"预测准"，而是**风险几何**：

- **单笔风险极小**：止损只有期权 K 线上**几个 tick**（"一滴不剩"），单笔风险 ≈ 5–10% 权利金。✅(ag swing 模拟佐证)
- **赔付靠凸性**：一次急涨/急跌的 naked option 多倍赔付，覆盖一长串小止损。
- **胜率可以很低**：低胜率 + 高盈亏比，盈亏比驱动 EV，不是胜率驱动。

**→ 由此推出本体系最重要的方法论结论（philosopher 必须内化）：**

> **一个在「标的 R 空间」负 EV 的信号，在「tick 级权利金止损 + 凸性赔付」空间完全可以正 EV。**
> 标的 R 空间回测（结构止损、−1R full stop、TP1/TP2）从**结构上测不到**这种 edge。
> **验证肖式期权策略必须直接在期权权利金空间建归因 harness，用肖式风险几何做实验设计；
> 再用标的 R 空间回测去否决它，是方法论错误。**

这条直接解释了一个表面矛盾（见 §6）：repo 里 PA top 三机制 K=3 全 REJECT，但肖的 put 成功——
两者不矛盾，因为否决发生在标的 R 空间，肖的 put 活在权利金空间。

---

## 2. 四层机制链（核心结构）

肖的口述链路（🟡 待截图确认）：
> 标的 MACD 顶/底背离作为信号（配合自定义 1B/2B/3B 走势结构划分）→ DD 线左侧交易 + 破趋势线右侧交易 → 浅虚 naked call/put。

| 层 | 肖的做法 | 状态 | repo 现状 |
|---|---|---|---|
| **① 信号层** | 标的 **MACD 顶/底背离** | 🟡 | ✅ classical divergence detector（`detect_all_divergences`，本堆/邻堆/隔堆，**原生支持 top 方向**；生产里 DIF 家族退役 + bottom-only gate） |
| **② 结构层** | 自定义 **1B/2B/3B 走势结构**划分 | ⬛ **完全黑盒** | ❌ 疑似类缠论一二三类买卖点分级（**猜测，待证实**） |
| **③ 执行层·左侧** | **DD 线**（期权 K 线上跌势低点连线） | 🟡 / ✅近似 | ✅ 近似 = 期权 K 线 W 底回踩（反弹≥10% → 回踩初始低点 ±3 tick → 止损几 tick），`analyze_ag_options_ddline.py` |
| **③ 执行层·右侧** | **标的破趋势线** | 🟡 | ❌ 引擎无趋势线检测，全新组件 |
| **④ 期权腿** | **浅虚 naked call/put** | ✅(call) | call selector 已有（ag/au）；**put selector 无** |

### 2.1 三个关键架构认知

**(a) 信号层是 alert，不是交易信号。**
背离只负责"开始盯这个品种"，**低精度可接受**（符合 memory `signals_are_posterior`）。
真正的风险几何由**执行层**提供（DD 回踩 tick 止损 / 趋势线破位确认）。
→ 退役的 divergence 机器在肖体系里**复活**，但角色从"emit lane 交易信号"变为"alert"；**top 方向 gate 需解开**。

**(b) 左侧与右侧画在两张不同的图上。**
- **DD 线**画在**期权自身 K 线**上 → 需要期权 15min/更细数据（tick 级止损在日线上糊掉）。
- **趋势线**画在**标的 K 线**上 → 只需标的数据 + 趋势线算法，**不依赖期权数据回填，可先动工**。

**(c) 1B/2B/3B 是唯一完全黑盒、且最高优先级的提取项**（见 §7 清单）。背离必须发生在哪个 B 才有效、在哪个级别划分、put/call 是否对称——全未知。

---

## 3. 操作规则与参数（已知部分）

### 3.1 期权腿选择（浅虚）
- **"浅虚"本质 = delta ≈ 0.30–0.40**，不是固定 %OTM（固定 %OTM 在不同 IV/DTE 下 delta 漂移大）。🟡
- repo 现有 OTM 阶梯（ag）：Rank1 ≈ +1.71%、Rank2 ≈ +2.93%、Rank3 ≈ +4.14%（strike 间距 100 元/克）。✅
- **阶梯规则（设计建议，待确认）**：优先 Rank1；若测量位移目标（MM = `B2 + (H1 − B1)`）落在 Rank2 OTM%，用 Rank2；**一般不用 Rank3**，除非 MM ≥ Rank3 OTM%。🟡
- **DTE**：20–60 天；au 有 ≥25 天下限、月末到期惯例。✅
- 合约命名（SHFE ag）：`ag{YYMM}c{strike}`，到期日约每月 17 日（遇周末前移）。✅

### 3.2 止损（两种约定，需 philosopher 厘清）
- **肖正宗（左侧 DD）**：止损 = 期权 K 线上**几个 tick**（"一滴不剩"），单笔风险 ≈ 几 tick 权利金。🟡——这是体系命门，回测必须能模拟（需期权 15min + bid/ask，几 tick 止损与盘口价差同阶）。
- **设计稿替代（标的 4-tick 止损）**：标的反向走 4 tick 即出（`stop = entry − 4·tick`）。legacy 报告：4-tick 标的止损下满止损单只亏 −8.6% 权利金 vs ATR×1.5 的 −51.9%（标的一转，theta+delta 快速复合）。✅(legacy 回测)
- 两者并存于 repo 文档；**正宗肖式是「期权 K 线 tick 级」，标的 4-tick 是可用替代**。philosopher 设计时建议两条都建为可切换的止损 policy 在权利金空间 A/B。

### 3.3 时间标度与分批（legacy 回测口径）✅
- **T = 17 个交易日**最大持有，到 T 强制平仓。
- **TP1 = +1R 卖一半，TP2 = +2R 卖余下**（R 以标的结构止损距离或 ATR 计）。

### 3.4 IV regime（进场成本）
- **核心警讯**：信号触发当天 IV 被推高（ag 约 **16–17%** vs 平时 6–7%）——**信号日就是 IV 贵的日子，系统性在买贵**。✅
- 期权市场**滞后**：成交量在标的信号后 **2–3 天**才放量（市场跟随而非预判）。✅
- **入场时机建议**：信号后 2–3 天确认标的没继续下破再买 Rank1–2；对照 IV 未大幅压缩。✅
- **IV-rank 闸门（设计建议）**：252 日 IV-rank > ~0.70 时拒绝（买便宜时间）。阈值待实证扫描。🟡

---

## 4. 品种逻辑（call 与 put 的主场不重叠）

源自 DD 线跨品种结论（`project_ddline_options_findings`）：✅(call 侧) / 🟡(put 侧推断)

- **call 主场 = 贵金属（ag/au）**：上涨偏态（右尾肥）→ OTM call 凸性兑现；DD 线验证 ag 1.29x / au 1.66x。
- **call 在工业品/黑色（cu/rb）= 负 EV**：缺上涨偏态。
- **put 主场（推断）= 工业品/黑色/化工（cu/rb/i/ta/ma…）**：下行常是急跌（供需冲击、宏观、移仓踩踏），**下跌肥尾**普遍；ag/au 的上涨偏态对 put 反而逆风。
- **→ 两条腿品种池不重叠是合理预期，不是缺陷。**call 池 ⊂ 贵金属，put 池 ⊂ 工业品。

> 注意与 researcher 的「配对凸性 Q2-Phase1」结论（`project_pairing_convexity_q2phase1`）对齐：
> 标的条件右尾 au call-favorable、rb 不、**cu 标的层 call-favorable 却期权 EV−**（差异在期权侧 IV）。
> 即"上涨偏态→call"在标的层成立但**期权 EV 还要过 IV 这关**——philosopher 设计 call 选品判据时须把 IV 纳入。

---

## 5. put 侧的正确打开方式（重点，因为肖偏重 put）

1. **PA top REJECT 与肖 put 成功不矛盾**：否决的是标的 R 空间的顶部反转（慢衰竭、BEAR 样本少）；肖 put 活在 tick 级权利金止损 + 凸性赔付空间。🟡
2. **put 进场机制可能不是"抓顶"**：更可能是**破位加速**或**下跌中继的反抽放空**（A_top 测试里唯一正 EV 的 cell 恰是 BEAR 相位，只是 n 太小）。机制类对了，样本量靠扩品种池解决。🟡
3. **put 验证必须在权利金空间**：直接建期权归因 harness，不要用标的 R 空间回测否决 put。

---

## 6. 与现有 PA 复刻体系的接口（给 philosopher 的搭建起点）

philosopher 已有的 building blocks（标的信号层，**已验证**）：
- ✅ 8 条 live emit lane（pa_h2 / bpull / vflush / context_a / pa_cn_bond / pa_us_60min / …），K=3 走查、baselines drift gate，累计 EV +0.247R in-sample / +0.344R K=3 OOS——**全是 bottom/call 方向**。
- ✅ SPEC-001/002/003 突破 setup（忠实 EV，selectivity=alpha）。
- ✅ classical divergence detector（双向，top gate 待解开）。

**期权决策链应"坐"在这些标的信号之上**（肖：期权只在标的有方向信号时才存在）。建议的决策链骨架：

```
标的信号(alert: 背离/PA bottom 或 顶) 
   → [结构层 1B/2B/3B 确认]        ⬛ 待提取
   → [IV-regime 闸门]              🟡 信号后2-3天 + IV-rank
   → 选浅虚 naked option (delta 0.3-0.4, 20-60DTE)   ✅选约件
   → 执行: 左侧 DD 回踩 tick 止损 | 右侧 趋势线破位     ✅左近似 / ❌右待建
   → 出场: TP1 +1R半 / TP2 +2R / T=17 强平 / tick 止损   ✅口径
```

**已有期权侧零件**（`src/engine/options/`）：cn_ag/au selector（接入 score_today）、option_exit（2x/4x/tick 止损模拟，有测试）、option_price_loader（Black-76，IV 钉常数）、options_emission_replay（归因 harness）、tqsdk_feed（实时报价）。

---

## 7. 黑盒清单 & 待测假设（philosopher 的 decision-chain 设计 + 测试任务）

### 7.1 必须先提取的黑盒（拿到肖视频/截图后，按优先级）
1. ⬛ **1B/2B/3B**（最高优先，唯一全黑盒）：每个 B 的定义、在走势结构什么位置标记、在哪个级别划分、背离须发生在哪个 B、put/call 是否对称。
2. 🟡 **DD 线**：画在期权图还是标的图、"反弹多少后回踩"、回踩容差、止损具体几 tick。
3. 🟡 **趋势线（右侧）**：连哪些摆动点、什么算"破"（收盘破 / N tick / 回抽确认）、破位后立即进还是等回抽。
4. 🟡 **期权腿习惯**：浅虚到多虚（delta）、DTE 偏好、仓位阶梯/加仓、出场倍数 vs 标的结构目标、**put 主做哪些品种**。

### 7.2 待测假设（建在权利金空间）
- **H1（命门验证）**：tick 级权利金止损 + 浅虚 naked，低胜率高盈亏比能否正 EV？先在 ag/au call 上跑通 harness，再扩 put。
- **H2（配对超额）**：建 paired attribution——同一信号同记两腿，`excess = option_R − leverage_k × underlying_R`。若 excess ≤ 0，说明 theta + 进场 IV 吃掉凸性，该优化的是**进场 IV/strike** 而非信号。
- **H3（call 选品 × IV）**：把 §4 的"上涨偏态→call"判据加上 IV 维度（对齐 Q2-Phase1 的 cu 矛盾：标的 call-favorable 但期权 EV−）。
- **H4（put 池）**：工业品/黑色 put 是否因下跌肥尾而正 EV（破位加速/下跌中继反抽机制）。
- **H5（IV-regime 闸门）**：信号后 2–3 天入场 + IV-rank<0.70 是否显著优于信号当天买。

### 7.3 方法论红线（必须遵守）
- **一律在权利金空间验证**，不要用标的 R 空间回测否决期权策略（见 §1）。
- **几 tick 止损必须有 bid/ask**：止损与盘口价差同阶，没有 bid/ask 的回测会自欺（最容易骗自己的地方）。
- **当心 MODEL_DOMINATED**：slice-1 显示 ag 95% / au 79% PnL 来自 Black-76 合成价 + 常数 IV，不是市场价。任何优化做在合成价地基上都是在优化定价假设，不是市场。→ 依赖期权数据补完（全 strike 链 + put 链 + 15min + bid/ask + 扩工业品）。

---

## 8. 数据现状与缺口（指向已有规格）

- ✅ 已有：CN 期权日线（SHFE au/ag/cu/rb ~3078 合约）、ag/au 15min/60min（日期不均）、payoff 矩阵。
- ❌ 缺（put 研究硬需求，详 `paired_options_direction` §5 + `src/docs/data-fill-request.md`）：
  **put 合约链**（现 call-only）、**全 strike 链**、**15min/更细**（tick 止损模拟）、**bid/ask**、**品种扩工业品/黑色/化工**、**真实 emitted strikes 历史**（压低 modeled_fraction）。
- 数据补完在另一台服务器（WSL）进行；缺数据的部分先用 **liquid ATM proxy 归因**。

> 数据事务走 data-engineer 建卡（researcher/philosopher 不碰数据管线）。

---

## 9. 一句话给 philosopher

> 标的信号层你已经有了（PA 复刻 + 背离）。**期权决策链 = 在标的 alert 之上，叠加 [1B/2B/3B 结构(待提取)] →
> [IV 闸门] → [浅虚 naked option 选约] → [tick 级权利金止损 / 趋势线破位执行] → [TP1/TP2/T=17 出场]，
> 全链路在权利金空间归因测试。** 命门是 §1 的风险几何与 §7.3 的方法论红线；最大的未知是 §7.1 的 1B/2B/3B。
> 先用 ag/au call 跑通 H1/H2 harness（数据齐），put 与工业品池等数据补完。
