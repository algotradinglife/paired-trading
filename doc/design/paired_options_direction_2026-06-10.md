# 标的-期权配对交易：问题盘点与方向文档

**日期**: 2026-06-10
**状态**: 方向性文档（迁移到新服务器后作为深度讨论的起点）
**读者**: 迁移后的新 session / 未来的自己
**配套阅读**: `doc/design/xiao_options_timing_design_2026-06-08.md`（肖体系期权 timing 设计稿）、
`doc/repro/options_attribution_2026-06-10.md`（slice-1 归因结论）、`MIGRATION.md`（迁移手册）

---

## 0. 一句话目标

用标的分析寻找潜在顶/底，用对应的**浅虚 naked call/put** 入场出场，获取相对标的腿的超额收益。
方向选择的依据：肖老师（飞天期权）的实战体系——CN 期货为主，**她偏重 put**，其学生可复制此打法。

---

## 1. 现状盘点（2026-06-10 快照）

### 1.1 资产：标的信号侧已扎实

- 8 条 live emit lane（pa_h2 / bpull / vflush / context_a / pa_cn_bond / pa_us_60min /
  pa_us_dif_pos / pa_h2_climax-STALE），K=3 走查验证，baselines/ 11 entries + 每周 drift gate。
- 累计 EV +0.247R in-sample / +0.344R K=3 OOS（见 `STATUS.md`）。
- 全部是 **bottom/call 方向**。

### 1.2 资产：期权侧已有的零件

| 零件 | 位置 | 状态 |
|---|---|---|
| OTM call selector (ag/au) | `src/engine/options/cn_{ag,au}_selector.py` | live，接入 score_today |
| DD 线出场模拟器（2x/4x/tick 止损） | `src/engine/options/option_exit.py` | 有测试 |
| DD 线左侧进场（期权 K 线 W 底回踩） | `src/scripts/analyze_ag_options_ddline.py`、`src/scripts/analyze_au_ddline_deep.py`、`src/scripts/sweep_ddline_options.py` | ag 1.29x / au 1.66x 验证有效；cu/rb 负 EV |
| 市场价/Black-76 调度 | `src/engine/options/option_price_loader.py` | IV 钉死常数（ag 0.13 / au 0.085） |
| 4-emitter 忠实回放 | `src/engine/options/options_emission_replay.py` | 归因 harness 用 |
| TqSdk 实时报价 | `src/engine/options/tqsdk_feed.py` | 凭据缺失时静默降级 |

### 1.3 核心问题清单（按严重度）

**P0 — 期权归因是模型主导的（MODEL_DOMINATED）**
slice-1 结论：ag 95% / au 79% 的 PnL 来自 Black-76 合成价 + 常数 IV，不是市场价。
au 的 PROMOTE/REGIME_ONLY 结论随 IV 假设（0.085 vs 0.20）翻转。
**"期权腿有超额收益"这个命题尚未被市场数据验证过——验证的是定价模型假设。**
任何期权侧策略优化做在这个地基上都是在优化假设而不是市场。
→ 解法依赖新服务器的数据补完（见 §5）。

**P1 — 没有"配对超额收益"的衡量框架**
标的腿（`backtest_full_stack.py`，R 单位）和期权腿（attribution，premium multiple 单位）
是两套独立回测，没有逐信号配对。无法回答关键问题：
**期权赚钱是因为标的信号对（β），还是期权结构本身有增益（α）？**
需要 paired attribution：同一信号同时记录两腿，输出
`excess = option_R − leverage_k × underlying_R`。
若 excess ≤ 0，说明 theta + IV 进场成本吃掉了凸性，该优化的是进场 IV 和 strike，不是信号。
警讯已存在：信号触发日 IV 16-17% vs 平时 6-7%——信号日就是 IV 被推高的日子，
系统性地在买贵。

**P2 — put 侧没有任何代码**，而肖偏重 put（见 §2、§3）。

**P3 — 期权腿执行层粗糙**
- strike 选择是固定 %OTM（ag +1.71/2.93/4.14%），不同 IV/DTE 下 delta 漂移大；
  "浅虚"的本质是 delta ≈ 0.30-0.40，应按 delta 选。
- 无 Greeks、无 IV regime gate（IV-rank 高位买 naked long 是负 carry）。
- 出场与标的完全脱钩：DD 线 2x/4x + 30 天 max_hold 一刀切，
  无标的结构止损/MM 目标穿透，无 theta-aware 时间止损。
- BS 应换 Black-76（SHFE 是 European-on-futures）；ag/au selector 80% 代码重复
  → `BaseOTMSelector`。

**P4 — 期权数据路径不在统一 chokepoint 里**
标的数据有单一接缝（`src/data/store.py::BarStore`，MIGRATION.md §1），
但期权数据是 JSON 散文件（`data/options/cn/{ag,au}/*.json`）+ TqSdk 直连，
`data_dir` 硬编码在 selector / loader 里。迁移 + put 研究的数据量是现在好几倍，
散文件模式撑不住。**建议趁迁移在新 quant-data 里给期权数据定统一 contract**
（如 `OptionStore.load_chain(underlying, date)`）。

---

## 2. 关键认知修正：put 侧的正确打开方式

### 2.1 PA top 的 REJECT 与肖 put 的成功不矛盾

repo 已有结论：PA top 三机制 K=3 全 REJECT
（`doc/repro/pa_atop_wf_2026-06-10.md`、`doc/repro/pa_top_wf_2026-06-08.md`），结构原因：
顶是慢衰竭不是恐慌事件，BEAR regime 样本太少。**这个否决仍然成立，但要看清它否决的
是什么：在标的 R 空间（结构止损、-1R full stop、TP1/TP2）做顶部反转交易。**

肖的 put 是完全不同的风险几何：飞天止损只有期权 K 线上的几个 tick，
单笔风险 = 几个 tick 权利金，赔付靠凸性。胜率可以很低，一次急跌的 put
多倍赔付覆盖一串小止损。**一个在标的 R 空间负 EV 的顶部信号，在
"tick 级权利金止损 + 凸性赔付"空间完全可以正 EV——现有 K=3 harness 从结构上测不到这种 edge。**

→ **方法论结论：put 侧的验证必须直接在期权权利金空间建归因 harness，
用肖式风险几何做实验设计。再用标的 R 空间回测去否决 put 是方法错误。**

### 2.2 品种逻辑反转

cu/rb 期权 call 负 EV 的归因是"缺上涨偏态"（`project_ddline_options_findings`）。
同一事实换到 put 侧是正面证据：CN 工业品/黑色/化工的下行常是急跌
（供需冲击、宏观、移仓踩踏），下跌肥尾比上涨普遍；ag/au 的上涨偏态对 put 反而是逆风。

→ **call 主场在贵金属、put 主场大概率在工业品。两条腿品种池不重叠是合理预期，不是缺陷。**

### 2.3 "顶是慢衰竭"提示 put 进场机制可能不是抓顶

更可能是**破位加速**或**下跌中继的反抽放空**（A_top 测试里唯一 EV 为正的 cell
恰好是 BEAR 相位，只是 n 太小无法验证）。机制类对了，样本量靠品种池扩大解决。

---

## 3. 肖的机制链（2026-06-10 用户口述，待视频/截图确认）

> 肖一般选择 MACD 的顶背离或底背离作为标的发出的信号（配合她自定义的走势结构
> 1B/2B/3B 划分），然后用 DD 线左侧交易 + 破趋势线右侧交易结合。

### 3.1 四层结构 vs 仓库现状

| 层 | 肖的做法 | 仓库现状 |
|---|---|---|
| 信号层 | 标的 MACD 顶/底背离 | ✅ classical divergence detector（`detect_all_divergences`，本堆/邻堆/隔堆，**原生支持 top 方向**；生产里 DIF 家族退役 + bottom-only gate） |
| 结构层 | 1B/2B/3B 走势结构划分 | ❌ 完全黑盒，待视频提取（疑似类缠论一二三类买卖点分级——**猜测，需证实**） |
| 执行层·左侧 | DD 线 | ✅ 近似实现 = 期权 K 线 W 底回踩（反弹≥10% → 回踩低点 ±3 tick → 止损"一滴不剩"几 tick），`analyze_ag_options_ddline.py` |
| 执行层·右侧 | 标的破趋势线 | ❌ 引擎无趋势线检测，全新组件 |
| 期权腿 | 浅虚 naked call/put | call selector 已有（ag/au）；put selector 无 |

### 3.2 两个架构级推论

**退役的背离检测器要复活——但角色变了。**
之前退役 DIF 家族是因为它在标的 R 空间 emit lane 上精度不够、被 PA 碾压。
在肖体系里背离不是交易信号，是 **alert**：只负责"开始盯这个品种"，
真正的风险几何由执行层提供（DD 回踩 tick 止损、趋势线破位确认）。
低精度 alert + 高纪律执行层，整体 EV 可以为正
（符合 memory「signals are posterior inference」）。
→ **迁移时勿删 divergence 机器；put 研究需要解开 top 方向的 gate。**

**左侧和右侧在两张不同的图上。**
DD 线画在**期权自身 K 线**上；趋势线画在**标的 K 线**上。数据需求不同：

- 左侧需要期权 15min 数据（W 底回踩 + tick 止损在日线上糊掉）→ 等数据补完
- 右侧只需标的数据 + 趋势线算法 → **不依赖数据回填，可先动工**

---

## 4. 机制提取清单（拿到视频/实盘截图后逐项核对）

**1B/2B/3B（最优先——唯一完全黑盒的部分）**
- 每个 B 的定义、在什么走势结构位置标记；类缠论买卖点分级的猜测是否成立
- 在哪个级别划分（日线？60min？）；背离必须发生在哪个 B 才有效
- put 和 call 的 B 划分是否对称

**DD 线**
- 实际画在期权图还是标的图上（验证 repo 的 W 底近似是否忠实）
- "反弹多少后回踩"的量化习惯；回踩容差；止损具体几个 tick

**趋势线（右侧）**
- 连接哪些摆动点；什么算"破"（收盘破？N tick？回抽确认？）
- 破位后立刻进还是等回抽

**期权腿习惯**
- 浅虚选到多虚（% OTM 或 delta）；到期月 / DTE 偏好
- 仓位阶梯/加仓规则；出场是倍数还是看标的结构目标
- **她做 put 主要在哪些品种**——直接决定 put 池起点

**材料形态**：带她亲手标注（背离点、B 点、DD 线、趋势线）的截图价值最高——
可直接当机制提取 ground truth + 将来 detector 的验收用例
（算法在该图上必须标出与她一致的点）。每张图配品种+日期即可在本地数据上复现对齐。

---

## 5. 数据补完需求规格（给新服务器的回填任务）

put 研究 + P0 修复对回填数据的硬性要求，漏了会返工：

1. **put 合约链**（现有数据 call-only）
2. **全 strike 链**，不只 ATM 附近（delta-target 选 strike、浅虚定义都需要）
3. **15min 或更细的期权 K 线**（tick 级止损模拟；日线 OHLC 是 slice-1 MODEL_DOMINATED 的根源之一）
4. **bid/ask**（几个 tick 的止损与盘口价差同阶，没有 bid/ask 无法判断可执行性——
   肖式打法回测最容易骗自己的地方）
5. **品种范围扩到工业品/黑色/化工**（rb、i、ta、ma 等），不只 ag/au
6. （P0 修复）emitted strikes 的真实历史，把 modeled_fraction 从 0.95/0.79 压到 <0.3；
   回填不全的部分改用 **liquid ATM proxy 归因**

---

## 6. 路线图

### Phase A — 迁移前 / 数据未到位（本机可做）

- [ ] **趋势线破位检测器**（纯标的数据）：摆动点连线 + 破位判定，
      先在标的数据上跑通"背离 alert → 趋势线破位右侧"链路形态
- [ ] 解开 divergence detector 的 top gate（背离 alert 双向输出，不进 R 空间 emit lane）
- [ ] （工程顺手）`BaseOTMSelector` 合并 ag/au 重复代码；BS → Black-76；
      `_compute_mm_pct` 从 `score_today.py` 抽到 `engine/options/`

### Phase B — 材料到手后（机制提取）

- [ ] 按 §4 清单提取，产出 1B/2B/3B 形式化 spec + DD 线/趋势线参数确认
- [ ] 结构分类器（1B/2B/3B detector）+ 标注图验收用例

### Phase C — 新服务器数据到位后

- [ ] 期权数据统一 contract（`OptionStore`，对齐新 quant-data 格式）——见 §1.3 P4
- [ ] **P0**：真实数据归因，压 modeled_fraction；au IV 敏感性边界报告
- [ ] **P1**：paired attribution 框架（excess = option_R − k × underlying_R）
- [ ] **put selector + 权利金空间归因 harness**：
      DD 线左侧 + 趋势线右侧两路 A/B；品种从肖实际做 put 的池起步（工业品优先）
- [ ] IV regime gate（IV-rank 252d，先试 0.70 阈值）；delta-target 选 strike

### Phase D — 优化层（C 出结论后）

- [ ] 出场升级：标的结构止损/MM 目标穿透期权出场；theta-aware 时间止损
- [ ] 15min 确认升级为期权腿硬 gate（⚠️ 前提：先解决 bar-timestamp session
      语义对齐，否则有 leak 风险——见 memory「multi-TF sweet-spot timing pitfall」）
- [ ] 顶部衰竭信号驱动 **call 提前离场**（退出信号不需要进场级证据强度，独立低成本增益）
- [ ] US 期权扩展评估（pa_us_60min / dif_pos 是验证过的 lane，US 期权数据可得性
      远好于 CN，不会陷入 MODEL_DOMINATED——若 CN 数据回填受阻，这是备选主战场）

---

## 7. 开放问题（迁移后深度讨论的议题）

1. 1B/2B/3B 的精确语义（等材料）
2. put 池的起点品种：肖的实际品种 vs 下跌肥尾筛选（两者交集？）
3. 权利金空间 harness 的验收标准：用什么对标？（没有 R 单位了，
   候选：ev_mult 的 K=3 折、相对 buy-and-hold-premium 的超额、相对标的腿的 paired excess）
4. 左侧 DD 与右侧趋势线破位：肖是二选一还是叠加确认？仓位如何在两路间分配？
5. naked vs spread：IV-rank 高位时是否自动降级为 spread（用户当前偏好 naked，先做 naked）
6. 背离 alert 的级别选择：日线背离 + 60min 执行，还是 60min 背离 + 15min 执行？
   （与 1B/2B/3B 的级别归属绑定）

---

## 8. 本文档的形成脉络（证据链）

- 期权层现状与缺口：explore 全量盘点（2026-06-10 session），关键文件见 §1.2 表
- MODEL_DOMINATED 结论：`doc/repro/options_attribution_2026-06-10.md` +
  `baselines/options_{ag,au}.json`
- PA top REJECT：`doc/repro/pa_atop_wf_2026-06-10.md`（三机制、K=3、全 OOS 负）
- DD 线已有验证：`project_ddline_options_findings`（ag 1.29x / au 1.66x、cu/rb 负）
- 肖机制链：用户口述（2026-06-10），§3 引文；细节待视频/截图确认
- 相关 memory：`put-side-xiao-direction`、`project_options_left_side_entry`、
  `project_signals_are_posterior`、`feedback_multi_tf_sweet_spot_timing_pitfall`
