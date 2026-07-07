# SPEC-003 阻力突破做空 — 忠实 EV（多/空对称，2026-06-15）

卡片 t_debfccf3（philosopher 交付 SPEC-003，补做多偏盲区）。researcher 用 eval_spec001_corpus
（新增 --direction 做空：sell-stop 进场——low≤entry 触发、stop 在上、target 在下；simulate_order 已支持）
对复刻 E/S/T 重跑 + bootstrap CI。语料 labels_short.jsonl（rb+cu）。**机械统计，不打 PASS/FAIL。**
复现：
```
cd src && TP=/home/drwho1985/workspace/quant/strats/trade-philosopher/runs/_replica
python3 scripts/eval_spec001_corpus.py --corpus $TP/labels_short.jsonl --direction 做空 --out data/review/spec003_faithful_ev.json
```

## 结果（突破单 × 做空，rb+cu）
| 指标 | 值 |
|---|---|
| n | 16 |
| 胜率 | 56.3% |
| 毛 EV | **+0.501R**，95% CI **[−0.185, +1.187]**，P(>0)=**0.92** |
| 中位 / max | +0.99 / +2.69；capped@5R +0.501（无肥尾） |

corroborates philosopher +0.44R/52%(n=19)（researcher 触目标止盈、内嵌 9/16 偏高用我口径；n 因 resolved 略异）。

## 多/空对称：方向性成立，短边欠功率
- 空头 +0.50R、56% 与多头同量级（SPEC-001 反转 +0.67 / SPEC-002 趋势 +0.90 / au +0.29）→ **selectivity=alpha
  方向性多/空对称**：复刻的选择性 edge 在做空侧也为正、量级相当。
- **但短边不显著**：CI[−0.185,+1.187] 跨 0、P=0.92、**n=16 太小**（同 au n=8 欠功率）。结论是**方向性对称**，
  统计显著性待补短边样本（≥30-50 空头单）。

## 多/空独立可叠加
做多 vs 做空 = **相反方向**→ 必然落在不同交易/bar、结构性互斥 → **独立且可叠加**（组合 long+short =
全方向覆盖，不互相蚕食）。叠加上 SPEC-001/002（按 cycle 互斥）→ 形成 (方向 × regime) 的正交 setup 矩阵。

## 空头候选闸门是否 researcher 化
现为 philosopher `tp.pa.short_proxy`（镜像 long proxy）。EV 评估直接消费复刻 labels、不依赖 researcher
重建闸门，故**非阻塞**。若后续要做确定性大样本短边回测（如 long 侧 backtest_spec001_proxy），可镜像
researcher 化——列为可选 follow-up，非当前必需。

## 局限
n=16 小、CI 跨 0（短边欠功率，结论=方向性对称非显著）；per-cycle 更小（philosopher broad_channel n7 +0.53、
trading_range n4 +1.06，n 太小不出 CI）；限价做空未忠实仿真（simulate_order 止损进场语义；采信 philosopher）；
内嵌 outcome 偏高（用 researcher 触目标止盈）。工件 spec003_faithful_ev.json（gitignore）。
相关：[[spec001-ev-eval]]、doc/spec-002-trendtr-breakout-ev-2026-06-15.md。
