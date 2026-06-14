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
