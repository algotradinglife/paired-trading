# SPEC-001 忠实 EV（philosopher 复刻语料，2026-06-14）

卡片 t_0da3b750。philosopher 交付忠实复刻语料后的**真实 SPEC-001 EV**（不再是 proxy）。
语料：`trade-philosopher/runs/_replica/pa_dataset_rb_claude.jsonl`（120 条，label_source=replica_claude）。
**机械统计，不打 PASS/FAIL。** 复现：`cd src && python3 scripts/eval_spec001_corpus.py --corpus <jsonl> --out data/review/spec001_faithful_ev.json`。
philosopher 源路径由 `_resolve_tp_src()` 自动解析（env `TP_PA_SRC` → 仓库同级 sibling → 绝对路径
`/home/drwho1985/workspace/quant/strats/trade-philosopher/src`）；HOME 异常的 Hermes/Kanban worker 下
无需手动指定（reviewer t_a0af6bc4）；非标准布局可加 `--philosopher-src <path>` 覆盖。

## 口径
SPEC-001 = 突破买 stop 做多（order_type=突破单, direction=做多）= **43 单**（另 5 限价做多/5 做空/67 不下单，不计入）。
按 philosopher 要求**独立重跑 researcher 的 `simulate_order`**（在复刻 E/S/T 上、单合约前向 K 线、
出场=触目标即止盈、同根 stop-first），不直接采信语料内嵌 outcome。bootstrap 10k/seed=42。

## 结果（忠实，n=43）

| 指标 | 值 |
|---|---|
| 胜率 | **67.4%** |
| 毛 EV | **+0.773R**，95% CI **[+0.380, +1.165]**，P(>0)=**1.00** |
| 中位 R | **+1.30** |
| 净 EV | +0.673@0.1R / **+0.573@0.2R** / +0.473@0.3R |
| max R | **+3.50**（无肥尾/异常值；proxy 曾有 +277R） |

**截尾稳健**：capped@5R 与剔除 |R|≥10 均 = +0.773（0 个异常），即这条 EV **不靠肥尾**，与 proxy 截然不同。

## 关键对比：选择性 = alpha

| | 确定性 proxy（机械全候选） | 忠实复刻（replica 选择性） |
|---|---|---|
| n（rb） | 1148 | 43 |
| 胜率 | 20.4% | **67.4%** |
| 毛 EV | +0.456 | +0.773 |
| **截尾@5R 稳健 EV** | **−0.044**（≈持平/负） | **+0.773**（CI 排除 0） |
| 形态 | 低胜率肥尾彩票 | 高胜率、稳健、无异常 |

复刻体把 1152 候选筛到 ~43 单（~1:27），用**交易者方程判断**（win_rate_est + 上下文）替代了
机械规则——把 proxy 那条扣成本即归零的肥尾彩票，转成 **67% 胜率、CI 排除 0 的稳健正 EV**。
**这定量证明：SPEC-001 的 alpha 在复刻体的选择性/克制，不在机械形态本身。** 与 P1 pilot 早期信号
一致（n=3 复刻全否决、3 笔确定性 outcome 均 −1R → 否决正确）。

## 四个必须记录的 caveat
1. **语料内嵌 outcome 被高估**（已证 philosopher 的换月跳变警告）：43 单里我重跑与内嵌不一致 30 单——
   其中 **21 单内嵌"target"R 大于 payoff**（让赢家跑过目标/换月跳空虚增 R）。researcher 口径**触目标即
   止盈**（gross_r==payoff，29/29 核验一致），是忠实 SPEC-001 出场。→ **EV 用本文 researcher 口径，
   勿用内嵌 outcome**。
2. **复刻体实际交易 payoff<2 的单**（30/43 低于写定的 §5「payoff≥2」硬门）：median payoff 1.67。
   即复刻跑的是**完整交易者方程权衡**（高胜率补偿较低盈亏比），而非硬 ≥2 门。严格 ≥2 子集 n=13：
   win 46%、mean +0.63、median −1（小样本）。→ **写定 spec §5 的硬门 ≠ 复刻真实行为**（给 philosopher 的反馈）。
3. **9 单与内嵌符号相反**（target↔stop）：源于前向数据口径差异（我用单合约到期序列、philosopher 可能用
   换月拼接连续合约），临近到期对近价 setup 敏感。单合约口径更保守/干净。
4. **不建模入场前失效（exit-engine-only）——可能偏乐观**（reviewer t_9ef7dc76）：simulate_order 让挂单
   一直挂到触发，**不**在触发前按失效条件作废。rb2607 实例入场前最低探到 3334（< 止损 3365、< 复刻失效
   线 3352）——按任何入场前失效判据该单都应作废。故本 EV 假设「无入场前失效」，若复刻真实意图是触发前
   按 `invalidation_condition` 作废，则部分"触发"单应被剔除、EV 会变化。**是否建模入场前失效是待 philosopher
   钉死的约定**；当前 n=43 EV 在「无入场前失效」假设下成立。

## 局限
n=43 偏小、仅 rb、仅多单；CI 虽排除 0 但宽（[+0.38,+1.17]）。philosopher 可扩 ag/au/cu 放大样本
（已表示可继续扇）。payoff<2 占多数 → 若按写定硬门筛则样本更小、EV 更弱，需澄清"SPEC-001"以
复刻实际行为（交易者方程）还是写定硬门为准。
脚本 `scripts/eval_spec001_corpus.py`；工件 `data/review/spec001_faithful_ev.json`（gitignore）。
相关：[[spec001-ev-eval]]、doc/spec-001-proxy-ev-2026-06-14.md、doc/spec-001-ev-readiness-2026-06-14.md。
