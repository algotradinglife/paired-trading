# 过度延伸惩罚跨 lane 推广验证（P1a，2026-06-13）

卡片 t_bd5f8b71（epic t_d6dccbab）。**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 问题

range_vs_avg（信号棒过度延伸/棒长惩罚）在 bottom×opposing 过资格关（t_6c3f043a）。
本卡验它是否**通用原则**：在 direction × higher_relation 的 6 个 lane 上跑同一套 gate
验证（阈值扫描 + gate@1.0 bootstrap + nested walk-forward），看惩罚是跨 lane 普遍、还是
bottom×opposing 特有。

## ⚠ 数据限制（关键）

跑时 **US 日线数据不可用**（loader 取 US daily 返回 None，60min/15min 仍在；今日早些
US 正常、之后回归——已建 data-engineer 卡 t_873b2d72）。本结果**仅 CN_BOND + CN_METAL**。
US（曾在 t_6c3f043a 驱动 bottom×opp 的 +0.60 by-pool）**缺失**，US 侧推广待数据恢复后补。
故 bottom×opposing 此处 n=189（CN-only，raw）vs t_6c3f043a 的 266（含 US，gated）。

## 方法

每 symbol 一次 detect+enrich，按 (direction, h_rel) 分桶到 6 lane，逐信号按其方向
simulate_trade。raw 信号群（未过 policy gate，隔离过度延伸效应）。复用 analyze_range_gate
聚合。脚本 + 3 单测。复现：`python3 scripts/analyze_overext_lanes.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/overext_lanes.json`（US 当前产 0 行）。

## 各 lane gate@1.0（kept = range_vs_avg≤1.0，dropped = 过度延伸）

| lane | n | full_ev | kept_ev | dropped_ev | gap | bootstrap95 | P | nested OOS improve |
|------|---|---------|---------|-----------|-----|-------------|---|--------------------|
| **bottom×opposing** | 189 | +0.149 | +0.380 | −0.027 | **+0.407** | [+0.096, +0.717] | **0.996** | **+0.104** |
| bottom×neutral | 40 | +0.186 | +0.529 | −0.386 | **+0.914** | [+0.325, +1.480] | **0.999** | −0.033 |
| bottom×supporting | 129 | +0.318 | +0.388 | +0.224 | +0.165 | [−0.226, +0.549] | 0.80 | −0.042 |
| top×opposing | 37 | +0.319 | +0.111 | +0.812 | **−0.701** | [−1.426, +0.109] | 0.043* | −0.423 |
| top×supporting | 84 | −0.075 | −0.118 | −0.014 | −0.105 | [−0.575, +0.363] | 0.34 | 0.0 |
| top×neutral | 8 | −0.457 | −0.101 | −0.670 | +0.570 | [−0.593, +2.170] | 0.77 | 噪声(n=8) |

\* top×opposing 的 P=0.043 是**反向**（dropped/过度延伸 > kept），非支持惩罚。

## 中性观察（不裁决）

1. **过度延伸惩罚是 bottom 侧现象，非通用**：在 **bottom×opposing**（+0.407, P=0.996）和
   **bottom×neutral**（+0.914, P=0.999, n=40 小）显著；bottom×supporting 弱、不显著（P=0.80）。
2. **top 侧不成立、甚至反向**：top×opposing 反向（过度延伸的大 bar 反而是更好的空头，
   gap −0.701 P=0.043，n=37 小，过 6-lane Bonferroni 不成立——视为提示非结论）；
   top×supporting 无效（且该 lane full_ev 本身负）；top×neutral n=8 噪声。
3. **CN-only 交叉验证**：bottom×opposing 在 **CN 单独**（无 US）仍显著（+0.407, P=0.996），
   说明惩罚不只靠 US；但强度低于含 US 的 t_6c3f043a（+0.484）——US 确曾加成。
4. **时间外**：仅 bottom×opposing 的 nested OOS 为正（+0.104）；其余 lane OOS 负或样本太小。
   各 lane OOS 子样本均偏小，OOS 显著性普遍不足。
5. **净结论**：过度延伸/棒长惩罚是**底部 long-reversal 入场质量特征**（bottom×opposing 最稳、
   bottom×neutral 提示），**不是市场级通用 gate**；top 侧不适用甚至反向。productionize 范围
   应限 bottom 侧（尤其 ×opposing）。US 侧推广 + 各 lane OOS 功效待数据（t_873b2d72）。
6. 局限：US 缺失；raw 群非生产门控群；单 cutoff 1.0；6 lane 多重检验（top×opp 的 0.043 不过校正）。
