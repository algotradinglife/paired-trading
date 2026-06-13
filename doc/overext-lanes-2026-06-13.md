# 过度延伸惩罚跨 lane 推广验证（P1a，2026-06-13）

卡片 t_bd5f8b71（epic t_d6dccbab）。**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 问题

range_vs_avg（信号棒过度延伸/棒长惩罚）在 bottom×opposing 过资格关（t_6c3f043a）。
本卡验它是否**通用原则**：在 direction × higher_relation 的 6 个 lane 上跑同一套 gate
验证（阈值扫描 + gate@1.0 bootstrap + nested walk-forward），看惩罚是跨 lane 普遍、还是
bottom×opposing 特有。

## 口径

**全 CN+US**（CN_BOND + CN_METAL + US_EQUITY）。US 日线在 t_45d3ed8b 修复后恢复（pre-2006
不再被日历下界丢，延至 1999；bottom×opp 受 60min HTF 覆盖限制止于 ~2016）。n_total=792。

## 方法

每 symbol 一次 detect+enrich，按 (direction, h_rel) 分桶到 6 lane，逐信号按其方向
simulate_trade。raw 信号群（未过 policy gate，隔离过度延伸效应）。复用 analyze_range_gate
聚合。脚本 + 4 单测（含 monkeypatch 验单次 detect+enrich / 6-lane 分桶 / 方向化 simulate）。
复现（无 uv 用 python3；CN_METAL/US 各约数分钟，可分池）：
`python3 scripts/analyze_overext_lanes.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/overext_lanes.json`
工件 `src/data/review/overext_lanes.json`（gitignore 派生）。

## 各 lane gate@1.0（kept = range_vs_avg≤1.0，dropped = 过度延伸）

| lane | n | full_ev | kept_ev | dropped_ev | gap | bootstrap95 | P | nested OOS improve |
|------|---|---------|---------|-----------|-----|-------------|---|--------------------|
| **bottom×opposing** | 312 | +0.069 | +0.385 | −0.134 | **+0.519** | [+0.264, +0.762] | **1.000** | **+0.159** |
| bottom×neutral | 61 | +0.207 | +0.533 | −0.232 | **+0.765** | [+0.224, +1.267] | **0.998** | **+0.171** |
| bottom×supporting | 231 | +0.313 | +0.319 | +0.303 | +0.016 | [−0.292, +0.322] | 0.54 | −0.016 |
| top×opposing | 58 | +0.525 | +0.347 | +0.991 | **−0.644** | [−1.199, −0.025] | 0.021* | −0.119 |
| top×supporting | 117 | +0.007 | −0.132 | +0.130 | −0.262 | [−0.657, +0.131] | 0.10 | 0.0 |
| top×neutral | 13 | −0.127 | +0.300 | −0.317 | +0.616 | [−0.689, +1.928] | 0.81 | 噪声(n=13) |

\* top×opposing 的 P=0.021 是**反向**（dropped/过度延伸 > kept，CI 整段<0）——过度延伸的
大 bar 反而是更好的空头，与 bottom 侧惩罚相反。

## 中性观察（不裁决）

1. **过度延伸惩罚是 bottom 侧现象，非通用**：在 **bottom×opposing**（+0.519, P=1.000）和
   **bottom×neutral**（+0.765, P=0.998, n=61）显著且 **nested OOS 均为正**（+0.159 / +0.171）；
   bottom×supporting 几乎为零、不显著（gap +0.016, P=0.54）。
2. **top 侧不成立、甚至反向**：top×opposing 反向且 **CI 整段<0**（过度延伸的大 bar 反而是
   更好的空头，gap −0.644 P=0.021，n=58；但 6-lane Bonferroni 后 0.021×6≈0.13 不过——视为
   强提示非结论）；top×supporting 反向不显著（P=0.10）；top×neutral n=13 噪声。
3. **时间外**：bottom×opposing 与 bottom×neutral 的 nested OOS 都为正（+0.159 / +0.171），
   方向 OOS 稳；其余 lane OOS ~0 或负。各 lane OOS 子样本仍偏小，强度待更多样本。
4. **统计画面（描述，不裁决）**：过度延伸/棒长惩罚的显著性集中在 **bottom × (opposing|neutral)**，
   bottom×supporting 无效，**top 侧不成立、top×opposing 方向相反**。即该惩罚是 bottom-side
   现象、非跨 6-lane 通用。（是否、如何用于 gate/productionize 由下游/Hermes 裁决，本文件不给建议。）
5. 局限：raw 群非生产门控群；单 cutoff 1.0；6 lane 多重检验（top×opp 的 0.021 过校正后 ~0.13 不过）；
   bottom×opp 受 60min HTF 覆盖限制，样本止于 ~2016（US 日线虽延至 1999，HTF 仍是瓶颈）。
