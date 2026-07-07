# range_vs_avg gate 验证 — 阈值扫描 + walk-forward（2026-06-13）

卡片 t_6c3f043a（t_ecb98b40 follow-up）。**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 背景

t_ecb98b40 发现 range_vs_avg（信号棒过度延伸/棒长惩罚）是 bottom×opposing 上唯一
正交且显著的 Brooks 特征（中位数切 gap +0.43R，CI 整段为正）。本卡补 productionize
前的验证关：把它当 gate filter（drop range_vs_avg > cutoff = 剔除过度延伸入场），验
阈值稳健性 + 时间外样本。

## 方法

复用 analyze_signalbar_quality.run_symbol（policy-gated bottom×opposing 行，含
range_vs_avg + realized_r + date），n=266（CN_BOND/CN_METAL/US_EQUITY）。
gate = 保留 range_vs_avg ≤ cutoff。bootstrap 10k/seed=42。

复现（在 `src/` 下；**无 uv 用 python3 直跑**，脚本自带 sys.path 注入）：
```
# 全量（~6.4min wall 本机；reviewer 慢机可能近 600s，建议改走分池）
python3 scripts/analyze_range_gate.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/range_gate_validation.json
# 有界分池复现（CN_METAL 深历史是 ~5min 大头，其余秒级；结果 seed=42 确定性，可分池核对）
python3 scripts/analyze_range_gate.py --pools CN_BOND --out /tmp/rg_bond.json     # 快
python3 scripts/analyze_range_gate.py --pools US_EQUITY --out /tmp/rg_us.json      # 快
python3 scripts/analyze_range_gate.py --pools CN_METAL --out /tmp/rg_metal.json    # ~5min
```
进度：逐 symbol 打 stderr（`scanning <pool>/<sym>`）。运行时已优化（复用的
analyze_signalbar_quality.run_symbol 移除未用的 enrich_with_lower_tf，输出不变、
n=266 一致，reviewer t_5e088d7c）。工件 `src/data/review/range_gate_validation.json`
（gitignore 派生，doc 内嵌全部数字）；脚本 + 7 单测。

## 阈值扫描（full_lane_ev = +0.103，n=266）

| cutoff | keep_frac | n_dropped | ev_kept | ev_dropped | lane_improve |
|--------|-----------|-----------|---------|-----------|--------------|
| **1.0** | 0.40 | 159 | **+0.392** | −0.092 | **+0.289** |
| 1.25 | 0.64 | 96 | +0.186 | −0.045 | +0.083 |
| 1.5（Brooks）| 0.79 | 57 | +0.129 | +0.004 | +0.027 |
| 1.75 | 0.88 | 32 | +0.120 | −0.022 | +0.017 |
| 2.0 | 0.93 | 18 | +0.126 | −0.221 | +0.024 |
| 2.5 | 0.98 | 5 | +0.095 | +0.5 | −0.008 |
| 3.0 | 0.99 | 2 | +0.092 | +1.5 | −0.011 |

**紧切点占优，但非严格单调**：lane 提升随 cutoff 收紧总体上升、在 **1.0 远超其余**
（+0.289 vs 次高 +0.083），但中段有抖动（1.75 +0.017 < 2.0 +0.024）。松切点尾部
n_dropped 极小（18/5/2）、ev_dropped 是 1-2 个样本的噪声（2.5 的 +0.5、3.0 的 +1.5 各仅
5/2 个），不可解读为"剔除有害"。结论应表述为**"紧切点 1.0 主导、尾部噪声"**，而非连续单调。
Brooks 的 1.5× 太宽松（只砍 57 个，提升仅 +0.027）。

## gate@1.0（经验最强切点，≈中位数）

kept 107 / EV +0.392 vs dropped 159 / EV −0.092；kept−dropped gap **+0.484R**，
bootstrap95 **[+0.217, +0.745]**（整段 > 0），P=0.9998。lane_improvement = +0.289R。
（对照 gate@1.5：kept 209/+0.129 vs dropped 57/+0.004，gap +0.125R bootstrap95
[−0.208,+0.453] 跨 0、P=0.77——宽松切点不显著。）

## 固定 cutoff 时间序折 + IS/OOS sensitivity（improvement = gated − full）

**注：这不是嵌套 walk-forward**（cutoff 非在 train 上选，是固定各 cutoff 看每折稳定性）。

| cutoff | IS improve | OOS improve | F3（最近 2025-03→2026-06）|
|--------|-----------|-------------|------|
| **1.0** | **+0.386** | **+0.091** | **+0.323** |
| 1.25 | +0.123 | −0.000 | +0.041 |
| 1.5 | +0.046 | −0.023 | −0.051 |

紧切点 1.0 的提升 IS + OOS + 最近折 F3 全为正；1.5 宽松切点 OOS/F3 转负（之前误判的
"衰减"是 1.5 口径的伪影）。

## 嵌套 train-select-test（nested walk-forward，无前视调参）

IS（≤2025-06-30）上扫 GRID 选 lane_improvement 最大的 cutoff，再用该 cutoff 在 OOS 评估：
- IS 选出 cutoff = **1.0**（IS improve +0.386，GRID 内最大）；
- 用 1.0 在 OOS 评估：lane improve **+0.091**（OOS gated +0.026 vs full −0.065，方向一致为正）；
- **但** OOS kept-vs-dropped bootstrap gap +0.193，CI [−0.369, +0.744]，**P=0.75 跨 0**——
  OOS 样本（n=57，kept 30）太小，OOS 单独的 gap 不显著。

即：只用历史调阈值选到 1.0、在未来仍是**方向性为正**的提升，但 OOS 样本量不足以让该
提升单独达到统计显著。full-sample 的 gate@1.0 显著（P=0.9998），OOS 子样本则只够看方向。

## 池间（gate@1.5）

| 池 | kept n/EV | dropped n/EV | improve | P(kept>dropped) |
|----|-----------|--------------|---------|------|
| CN_BOND | 15/+0.933 | 3/+1.281 | −0.058 | 0.11（n 太小）|
| CN_METAL | 99/+0.129 | 26/+0.133 | −0.001 | 0.50（无效）|
| US_EQUITY | 95/+0.003 | 28/−0.253 | +0.058 | 0.87 |

1.5 口径下提升主要来自 US_EQUITY；CN_METAL 无效、CN_BOND tiny-n。

## 中性观察（不裁决）

1. 过度延伸惩罚**紧切点主导（非严格单调）**：强 edge 在 **cutoff 1.0（≈中位数）**，
   远超其余；尾部松切点噪声大。非 Brooks 1.5×。
2. **full-sample 显著**：gate@1.0 kept−dropped gap +0.484R，CI[+0.217,+0.745] 整段>0，P=0.9998。
3. **时间外：方向一致为正，但 OOS 样本不足以单独显著**。固定 cutoff 1.0 的 IS/OOS/F3
   提升全正；嵌套 train-select-test（IS 选 1.0）OOS lane improve +0.091，但 OOS 子样本
   （n=57）的 kept-vs-dropped gap CI 跨 0（P=0.75）。即 edge 方向 OOS 稳，强度待更多 OOS 样本确认。
4. **代价**：cutoff 1.0 砍掉 ~60% 信号（保留 40%），交易机会大幅减少——gate 激进。
6. Bonferroni：阈值扫描 7 次比较；cutoff 1.0 的 full-sample 分离强度（P=0.9998）足以过 7× 校正。
7. 局限：单 EMA/ATR 窗口参数未扫；本群限 bottom×opposing + policy-gated；未与生产 policy
   weight 做联合增量。productionize 建议：用 1.0（或 1.0-1.25 间）作 de-weight 而非硬砍，
   权衡 EV 提升 vs 信号量损失。
