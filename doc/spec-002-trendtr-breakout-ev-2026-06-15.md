# SPEC-002 趋势区间顺势突破做多 — 忠实 EV 评估（2026-06-15）

卡片 t_55d30164（philosopher 交付 SPEC-002）。researcher 用 eval_spec001_corpus（新增 --cycle
+ 多 corpus）对复刻 E/S/T 重跑 simulate_order + bootstrap CI。语料 rb+cu+au。
**机械统计，不打 PASS/FAIL。** 复现（copy-paste-safe，绝对路径；`TP` 指 philosopher 复刻语料目录）：
```
cd src && TP=/home/drwho1985/workspace/quant/strats/trade-philosopher/runs/_replica
# SPEC-002（趋势顺势突破做多）
python3 scripts/eval_spec001_corpus.py --corpus $TP/pa_dataset_rb_claude.jsonl $TP/labels_cu.jsonl $TP/labels_au.jsonl --cycle trending_tr --out data/review/spec002_faithful_ev.json
# SPEC-001（反转族突破做多）
python3 scripts/eval_spec001_corpus.py --corpus $TP/pa_dataset_rb_claude.jsonl $TP/labels_cu.jsonl $TP/labels_au.jsonl --cycle broad_channel trading_range
```

## SPEC-002 忠实 EV（trending_tr × 突破单 × 做多，rb+cu+au 合并）
| 指标 | 值 |
|---|---|
| n | 24 |
| 胜率 | 66.7% |
| 毛 EV | **+0.901R**，95% CI **[+0.254, +1.609]**，P(>0)=**0.998**（显著） |
| 中位 / max | +1.15 / +6.43；capped@5R +0.841（无肥尾异常） |

corroborates philosopher 的 +0.98R（researcher 触目标即止盈口径略低、保守；内嵌 17/24 偏高，用 researcher 口径）。

## SPEC-001 vs SPEC-002：独立且可叠加
按 cycle 切分 breakout-long（rb+cu+au），**均用 eval_spec001_corpus --cycle 重算（可复现）**：

| setup | --cycle | n | 胜率 | 毛 EV | 95% CI | P(>0) |
|---|---|---|---|---|---|---|
| **SPEC-002** | `trending_tr` | 24 | 67% | **+0.901** | [+0.254,+1.609] | 0.998 |
| **SPEC-001** | `broad_channel trading_range` | 62 | 65% | **+0.674** | [+0.342,+0.999] | 1.000 |

（SPEC-001=反转族两 cycle 合并；spike/extreme_tr/normal_channel 等小样本/非反转-突破语境排除，不计入。
更正：早先表中 n=56/+0.64 及 broad_channel/trading_range 分行来自 ad-hoc inline 口径、与脚本不一致，reviewer
t_5f95925e 抓出——本表全部改为 eval_spec001_corpus 当前脚本逐 cycle 实算值。）

- **独立**：两者按 cycle **互斥**（trending_tr vs broad_channel/trading_range）→ 落在**不同 bar**、结构性不重叠。
- **可叠加**：两子集各自显著 +EV（CI 均排除 0）→ 同属『突破止损做多』大族、按 regime 拆分；叠加 = 非重叠
  信号集的并，扩大 regime 覆盖、不互相蚕食。SPEC-002（顺势延续 +0.90）略强于 SPEC-001（反转 +0.67）。

## R006（进场类型）确认
突破单（止损进场）跨 cycle 稳健 **+0.64~0.90R、胜率 62~67%**；限价单（回踩 fade）philosopher 实测
**+0.12R/30%(n=13)**——注：researcher 的 simulate_order 仅支持止损/突破进场语义，**限价进场无法忠实仿真**
（同 mine_pa_samples 限制），故限价数采信 philosopher。结论一致：**进场优先突破止损、限价 fade 降权**（SPEC-002 §5 已采纳）。

## 顺带：跨品种 selectivity=alpha（重要）
philosopher 为 SPEC-002 挖掘已产出 labels_cu(120)+labels_au(90)——**跨品种语料现已存在**。合并 rb+cu+au 的
breakout-long 在**两个 regime 族上都显著**（反转 n=62 +0.674 P=1.0、趋势 n=24 +0.901 P=0.998）→ **selectivity=alpha
跨品种（pooled rb/cu/au）成立且显著**。即先前『需 ~10M token 扩 au+cu 才能验跨品种』**已被 SPEC-002 副产
语料大体满足**（无需额外大额）。注：per-instrument au 单独仍欠功率（n=8 不显著），结论是 **pooled 显著**；
如需 per-instrument 各自显著仍需补样本。

## 局限
n=24 中等、per-cycle 子样本小（broad_channel n=11 CI 触 0）；限价进场未忠实仿真（采信 philosopher）；
pooled 跨品种假设 edge 品种间同质；内嵌 outcome 偏高（用 researcher 触目标止盈）。
工件 spec002_faithful_ev.json（gitignore）。相关：[[spec001-ev-eval]]、doc/spec-001-cross-instrument-ev-2026-06-15.md、
doc/spec-001-faithful-ev-2026-06-14.md。
