# SPEC-001 跨品种忠实 EV：selectivity=alpha 是否泛化（2026-06-15）

卡片 t_48c8d795（philosopher 扩语料）。researcher 用 eval_spec001_corpus 对 philosopher 复刻
E/S/T 重跑 simulate_order + bootstrap CI（philosopher 给毛值，researcher 给严谨 CI/稳健）。
**机械统计，不打 PASS/FAIL。** 复现：`cd src && python3 scripts/eval_spec001_corpus.py --corpus
<labels_{product}.jsonl> --out data/review/spec001_faithful_ev_{product}.json`。

## 结果（忠实 EV，researcher 重导，突破单+做多）

| 品种 | n | 胜率 | 毛 EV | 95% CI | P(>0) | max R |
|---|---|---|---|---|---|---|
| **rb**（螺纹/黑色） | 43 | 67.4% | **+0.773R** | **[+0.380, +1.165]** | **1.00** | +3.5 |
| **au**（黄金/贵金属） | 8 | 50.0% | +0.287R | **[−0.649, +1.265]** | 0.72 | +2.5 |

（au pilot 40 候选：突破做多 9，本工具解析 8 resolved；另 5 限价做多/3 做空/23 不下单。）

## 解读（陈述）
- **selectivity=alpha 在 au 上方向一致为正**（+0.287R、胜率 50%、无肥尾），即复刻的选择性 edge
  不是 rb 独有、**符号上跨品种泛化**。
- **但 au 不显著**：CI [−0.65,+1.27] 跨 0、P=0.72、**n=8 太小**——尚不能定论。且 au 明显**弱于 rb**
  （50% vs 67%、+0.29 vs +0.77R）。与假设一致：edge 在**黑色/趋势品种更强、贵金属/震荡偏弱**。
- 语料内嵌 outcome 仍偏高（au 4/8 与 researcher 重导不一致；philosopher 毛 +0.37 vs researcher
  +0.287）——继续用 researcher 触目标即止盈口径。

## 结论 + 下一步
**跨品种『方向性』确认（au 正），但『统计显著性』未确认（au 欠功率）。** 要硬化「selectivity=alpha
是复刻的普遍性质而非 rb 偶然」，需：
1. au 补到 **≥30–50 突破做多单**（philosopher 估 ~10M+ token）；
2. 加 **cu（工业金属）**第三点 → 黑色/贵金属/工业三品种三角，看 edge 强弱是否与品种性质（趋势 vs 震荡）相关。
成本敏感（philosopher 在控配额）→ 是否扩需用户/lead 拍板（已 flag 用户）。

## 局限
au n=8 极小、CI 宽；单 pilot；限价/做空未计入（order-type 仅突破做多）；au 5min 经 cn_data(SHFE)。
工件 spec001_faithful_ev_{rb,au}.json（gitignore）。相关：[[spec001-ev-eval]]、doc/spec-001-faithful-ev-2026-06-14.md。
