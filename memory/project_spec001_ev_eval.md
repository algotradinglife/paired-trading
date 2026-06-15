---
name: spec001-ev-eval
description: SPEC-001（楔形完成二次入场突破做多）的 EV 评估——philosopher→researcher 交付；现 N=1 不可评估，等批量复刻语料
metadata: 
  node_type: memory
  type: project
  originSessionId: bfb52110-df3c-4deb-b492-f1526868a5c8
---

2026-06-14：philosopher 起了新的 **PA 复刻 → 策略 spec** 管道（仓库
`~/workspace/quant/strats/trade-philosopher`，与 paired-trading 平级）。复刻体 = 逐节点跑
LLM 模仿交易员 PA 决策，确定性闸门 fire 才出单；产出 `runs/_replica/replay_*.json`
（每单 entry/stop/target/direction + reasoning，但**不记实际出场结果**）。

**SPEC-001**（doc/pa-replication/specs/spec-001-wedge-breakout-long.md）：通道下轨/三推下降楔形
完成点 + 强势看涨信号棒（body/range≥0.5、收上1/3）→ 买 stop 突破做多；闸门
payoff≥2:1 AND win_rate_est≥0.5。philosopher 侧保真度已立；**researcher 负责 EV/边缘侧**
（卡 t_0da3b750）。

**我的交付（commit 18ae0282）**：EV harness `src/scripts/eval_spec001_ev.py`（消费 replay JSON
+ philosopher `tp.pa.cn_data` 5min 接口逐K前向仿真出场 → 毛/净 R、胜率、分布）。复现
rb2607 单实例 +2.0R（买stop 3379 于 2025-07-24 13:35 触发、14:45 触 3407 止盈）。10 单测，
4 个 codex P2 修完（数据耗尽≠超时、前向窗口锚定、长单 default、ruff），ruff 通过。

**2026-06-15 全线交付（团队编排）**：
- **跨品种**（doc/spec-001-cross-instrument-ev-2026-06-15）：au pilot n=8 +0.287R CI[−0.65,+1.27] P=0.72
  → selectivity=alpha **符号泛化(au 正)但不显著**(n 小)，弱于 rb；假设 edge 黑色/趋势>贵金属/震荡。
  **硬化需 au→30-50+cu（~10M token）= 待用户成本决策**（researcher 推荐扩、未自烧）。
- **入场前失效 caveat 闭环**（reviewer t_9ef7dc76）：保守下界（入场前触止损即作废）rb 43 单仅 4 作废、
  EV +0.765R CI[+0.336,+1.189] P=1.0 仍显著 → 乐观偏差~0.008R 可忽略；**canonical EV 必落 [+0.765,+0.773]**
  （philosopher 已实现 canonical 约定 tp.pa.backtest.pre_entry_invalidate，t_5a409d23）。selectivity=alpha 稳健。
- **真人裁决→0 端到端**：54 分歧 triage = auto_resolved 26(肥尾假象10+方差止损16，16 stops 经 regime 检查
  确认分散 30%≈33%) + LLM-judge 28(Claude 盲判、禁 outcome 守 fidelity，pa_adjudication_rb_llmjudge.jsonl) +
  human 0。脚本 mine_pa_samples(triage)/eval_spec001_corpus(跨品种)。
- 工具：eval_spec001_corpus.py per-product 通用（labels_{product}.jsonl）；_resolve_tp_src 路径解析。

**SPEC-002 交付（2026-06-15，t_55d30164，doc/spec-002-trendtr-breakout-ev-2026-06-15）**：趋势区间顺势突破做多
（trending_tr×突破单×做多，rb+cu+au）**n=24 win67% +0.901R CI[+0.254,+1.609] P=0.998 显著**（corroborates
philosopher +0.98）。**SPEC-001(非trending反转族,n=56,+0.644R P=1.0) 与 SPEC-002 按 cycle 互斥→独立可叠加**
（不同 bar、扩 regime 覆盖；趋势>反转）。R006：突破止损 +0.64~0.90R 稳健 > 限价 fade(+0.12/30%，我的
simulate_order 止损进场语义无法仿真限价→采信 philosopher)。**跨品种 selectivity=alpha 现已 pooled 显著**
（philosopher 为 SPEC-002 产的 labels_cu/au 副产语料 → rb+cu+au 两 regime 都显著）→ **先前『~10M 扩 au+cu』
大体已达成、不需大额**（per-instrument au n=8 仍欠功率）。eval_spec001_corpus 加 --cycle + 多 corpus（向后兼容）。
**编排教训**：别在 philosopher 还可能投新 spec 时把轮询拉到 max-idle(3600s)——曾因此漏看 SPEC-002 ready 一段时间；
有活跃上游时保持较紧轮询(≤300-600s)。

**SPEC-003 交付（2026-06-15，t_debfccf3，doc/spec-003-resistance-breakdown-short-ev-2026-06-15，commit 2e9b15e6）**：
阻力突破**做空**（补做多偏盲区）。eval_spec001_corpus 加 **--direction 做空**（sell-stop 进场：low≤entry 触发、
stop 在上、target 在下；simulate_order 已支持），且 direction 贯穿过滤/下单/出场/**报告标签**（spec_def/counts
spec_breakout,limit_same_dir/headline faithful_ev_spec/stdout——codex P2：短报告不再误标做多）。语料 labels_short.jsonl
（rb+cu）：**n=16 win56.3% +0.501R CI[-0.185,+1.187] P=0.92**——方向性为正、与多头同量级，但**短边欠功率(n=16 CI跨0)**；
corroborates philosopher +0.44R/52%(n=19)。长边默认未破(n=43 +0.773)。**selectivity=alpha 多/空对称**；多/空相反方向
→结构性互斥→**独立可叠加**，形成(方向×regime)正交 setup 矩阵。短候选闸门(philosopher short_proxy)非阻塞、
researcher 化可选。要硬化短边显著性需 ≥30-50 空头单（已回 philosopher）。
**编排（2026-06-15）**：unblock 了 t_6cf9f9c4（PA 数据集）——其两阻塞依赖（真人裁决/philosopher 增量语料）均已解除
（human=0 via triage+llm-judge；philosopher 交付 rb120/cu120/au90），属 stale block，转 ready 让 data-engineer 跑增量 merge+mine+triage。
**PA 数据集 P3 完结（2026-06-15）**：data-engineer 交付跨品种(rb+cu+au)版本化脊柱 pa_dataset_rbcuau（3512 候选，
train2445/val536/test531，2021-2026）+ 裁决回填 apply_pa_adjudication.py（auto82+rb llm_judge28=110 已裁，human=0，
cu/au 47 pending 待 philosopher verdict=卡 t_b74da0e8）。代码 commit f90dc9e0（researcher 提交+codex 审，11 tests）。
reviewer t_9134a73f **审核通过**（byte-for-byte 可重生、outcome 守恒）。

**R008（philosopher SPEC-004 负面结果，2026-06-15，科学诚实不发卡）**：顺势回踩 MA 进场在 CN 商品 5min **负 EV
(-0.37R/28%/n14)**，复刻取选中的也亏 →**回踩/限价类进场（区间底 fade + 趋势 MA 回踩）均无 edge**，edge 集中在
**突破止损进场**。**corroborates 我的 R006**（突破止损 +0.64~0.90R 稳健 > 限价 fade +0.12/30%）。结论：有效 setup 空间
= 突破止损族（SPEC-001 反转 / SPEC-002 趋势 / SPEC-003 做空），回踩/fade 类不再探。labels_pullback.jsonl 留档（philosopher）。
philosopher 下一轮挖 **SPEC-005 失败突破 fade（假突破反向均值回归）**——注意这是『对突破失败做反向』，与『回踩进场』不同，不被 R008 排除。

**R009 + setup 空间 EXHAUSTED（2026-06-15）**：SPEC-005 失败突破 fade 也**负 EV(-0.38R/27%/n11)**，不发。
连同 R006(限价 fade)/R008(回踩 MA)→**所有均值回归/回踩/fade 进场机制全无 edge**；**PA 本域 alpha 唯一集中于
突破止损@结构边界（SPEC-001 反转 / SPEC-002 趋势 / SPEC-003 做空）**。philosopher 宣告**setup 空间映射完成→EXHAUSTED**。
→ 团队从『setup 发现』阶段转入**consolidation/hardening**：完成数据集全裁(cu/au verdicts t_b74da0e8)、
3 setup 显著性硬化、(方向×regime)正交矩阵→可部署 PA 信号(按 cycle/direction 路由+仓位)。已 commission philosopher 出下阶段改进方案。

**信号棒质量=正交硬化 filter（researcher，2026-06-15，commit 66b1395b，consolidation 首个成果）**：
scripts/analyze_signal_bar_quality.py（复用 canonical evaluate()，按 id join features_det，中位分层）。
pooled rb+cu+au breakout-long（分层在 rb n=43 有 features 子集，baseline +0.773R；cu/au 45 单无 features_det）：
**强信号棒赚正交 EV**——body_frac 好半 +1.017 vs 差半 +0.493（Δ+0.52R）；close_pos 好 +0.963 vs 差 +0.453（Δ+0.51R）；
range_vs_avg(惩罚) +0.90 vs +0.65（Δ+0.25R，**证实棒长惩罚/swing-quality**）；bar_range Δ+0.07 可忽略。差半 CI 触 0、好半稳正。
→ **body_frac + close_pos 是可叠加在突破 setup 上的硬化 filter**（Brooks 强信号棒 + 我的 swing-quality tight|wick/棒长惩罚迁移成立）。
caveat：分层仅 rb n=43（cu/au labels 缺 bar 几何，需 data-engineer/philosopher 补 features 才能 pooled 硬化）；中位分层粗、未多重校正。
close_pos 方向相关（多=收高好/空=收低好，已 direction-aware）。reviewer t_ba0ba553 审核通过。
**pooled 确认（2026-06-15，doc/signal-bar-quality-hardening-2026-06-15）**：rb-only caveat 已解除——**P3 数据集
pa_dataset_rbcuau.labeled.jsonl 对全 3512 候选有 features_det**（不必补数据）。pooled rb+cu+au n=88：body_frac Δ+0.555、
close_pos Δ+0.552（好半 ~+1.0R CI 排除 0 vs 差半 ~+0.45R）、range_vs_avg 棒长惩罚 Δ+0.251（pooled 证实）、
bar_range Δ−0.11 弃（绝对幅度无 edge，质量看相对几何）。pooled 比 rb-only 略强。短边 n=13 太小不可读。
复现：`cd src && python3 scripts/analyze_signal_bar_quality.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`。
**组合 filter 已验证（结果 C，pooled n=88）**：body_frac 高 AND close_pos 高 → **pass +1.284R 胜率79% CI[0.78,1.81]
留存 37.5%(33/88)** vs fail +0.399R；**Δ+0.885R 大于任一单 filter(+0.55) → 两质量信号可叠加**，baseline 0.73→1.28 近翻倍。
= 可落地 score_today 质量闸门（双强→full / 单强→half / 弱→light）。下一步：(b) 落地 score_today 仓位分层；(c) 短边补样本；(d) 三 filter 边际。

**关键发现（卡 BLOCKED 等 philosopher t_3d25c2f5）**：
1. **N=1 不可评估**：现唯一 replay（rb2607）只 2 单，其中 1 单是非 SPEC 做空 → SPEC-001 多单
   语料 N=1。胜率/期望/分布/稳健性全需规模样本。
2. **复刻只记订单不记结果** → EV 必须前向仿真，而出场/失效约定有**保真度敏感**坑：rb2607 入场前
   价格收过 **3362**（低于 spec 文字失效线 3366、也低于止损 3365），若按这两个数判失效则该笔作废、
   无 +2R；唯有按复刻 decision 的 `invalidation_condition`「跌破3352或强势空头信号棒」（自由文本、
   不可机械判定）才有效。=> 约定须 philosopher 敲定（或 replay 直接附实际出场结果）。

**Option A（用户授权，并行规模化 EV，commit fd1f32eb，doc/spec-001-proxy-ev-2026-06-14）**：
自建 SPEC-001 规则**确定性 proxy** `backtest_spec001_proxy.py`，跨 SHFE 5min（ag/au/cu/rb；
cn_data SHFE-only）跑 n=4713 多单。**raw 毛 EV +0.449R（CI[+0.304,+0.635]）、胜率 21.6%**，
但**异常值驱动不稳健**：top1% 交易占 63.6% 毛利、截 +5R 仅 +0.049R（≈毛持平、扣成本负）；
且比复刻 **100× 更宽松**（rb2607 proxy 187 信号 vs 复刻 1 单）。**结论：机械子集非稳健边缘；
复刻的选择性（win_rate_est+PA 上下文）才是 alpha——proxy 不能替代忠实 EV**。贵金属(au/ag)>螺纹(rb)。

**忠实 EV 已交付（2026-06-14，commit da976590，doc/spec-001-faithful-ev-2026-06-14）**：philosopher
交付忠实复刻语料 pa_dataset_rb_claude.jsonl（120 条/43 突破做多），researcher 用 eval_spec001_corpus.py
按'触目标即止盈'重算（不采信内嵌 outcome）。**n=43：win 67.4%、gross +0.773R、95%CI[+0.380,+1.165]
P>0=1.0、净 +0.573R@0.2R、max +3.5R 无肥尾**。对比确定性 proxy（20% win、截@5R −0.044 异常驱动）→
**选择性=alpha：复刻交易者方程判断（43/1152 候选）把扣成本归零的肥尾彩票转成稳健显著正 EV**。
卡 t_0da3b750 已完成；reviewer 卡 t_6c572f92。3 caveat：内嵌 outcome 被换月跳变虚增（21/43，用 exit-at-target）；
复刻实下 payoff<2 单（30/43，跑完整交易者方程而非写定 §5 硬门≥2→已反馈 philosopher 改 §5）；9 单符号翻转(前向数据口径)。
可扩 ag/au/cu 放大样本。

**时区**：复刻节点 `end` 与 cn_data `ts_open` 均 UTC epoch（核对过）。
**纪律**：philosopher 侧 fidelity 优先于 EV——即便某态 EV 负，只要复刻忠实即达标；researcher
不得"优化"掉复刻的选择性/把复刻改得比交易员聪明；需更多语料回 @philosopher 建卡。
已请求：t_3d25c2f5（批量多品种语料 ≥30-50 多单 + 确定性出场约定）。reviewer 卡 t_cf080497。
doc/spec-001-ev-readiness-2026-06-14.md。相关：[[scope-analysis-only]]、[[options-left-side-entry]]。
