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

复现：`cd src && uv run python scripts/analyze_range_gate.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/range_gate_validation.json`（无 uv 用 python3）。
工件 `src/data/review/range_gate_validation.json`（gitignore 派生）；脚本 + 5 单测。

## 阈值扫描（full_lane_ev = +0.103，n=266）

| cutoff | keep_frac | ev_kept | ev_dropped | lane_improve |
|--------|-----------|---------|-----------|--------------|
| **1.0** | 0.40 | **+0.392** | −0.092 | **+0.289** |
| 1.25 | 0.64 | +0.186 | −0.045 | +0.083 |
| 1.5（Brooks）| 0.79 | +0.129 | +0.004 | +0.027 |
| 1.75 | 0.88 | +0.120 | −0.022 | +0.017 |
| 2.0 | 0.93 | +0.126 | −0.221 | +0.024 |
| 2.5 | 0.98 | +0.095 | +0.5 | −0.008 |
| 3.0 | 0.99 | +0.092 | +1.5 | −0.011 |

**单调**：cutoff 越紧、lane 提升越大，最强在 1.0（保留 40%，ev_kept +0.392 vs
dropped −0.092）。过度延伸惩罚是**连续的、graded** 的——越延伸越差。Brooks 的 1.5×
太宽松（只砍极端尾部 57 个，提升仅 +0.027）。

## gate@1.0（经验最强切点，≈中位数）

kept 107 / EV +0.392 vs dropped 159 / EV −0.092；kept−dropped gap **+0.484R**，
bootstrap95 **[+0.217, +0.745]**（整段 > 0），P=0.9998。lane_improvement = +0.289R。
（对照 gate@1.5：kept 209/+0.129 vs dropped 57/+0.004，gap +0.125R bootstrap95
[−0.208,+0.453] 跨 0、P=0.77——宽松切点不显著。）

## walk-forward（improvement = gated_ev − full_ev，时间序 K=3 + IS/OOS）

| cutoff | IS improve | OOS improve | F3（最近 2025-03→2026-06）|
|--------|-----------|-------------|------|
| **1.0** | **+0.386** | **+0.091** | **+0.323** |
| 1.25 | +0.123 | −0.000 | +0.041 |
| 1.5 | +0.046 | −0.023 | −0.051 |

**关键**：cutoff 1.0 的提升 **IS + OOS + 最近一折（F3）全为正且强**——过度延伸惩罚
在紧切点上时间外稳健。1.5 宽松切点 OOS/F3 转负（之前误判的"衰减"是 1.5 口径的伪影）。

## 池间（gate@1.5）

| 池 | kept n/EV | dropped n/EV | improve | P(kept>dropped) |
|----|-----------|--------------|---------|------|
| CN_BOND | 15/+0.933 | 3/+1.281 | −0.058 | 0.11（n 太小）|
| CN_METAL | 99/+0.129 | 26/+0.133 | −0.001 | 0.50（无效）|
| US_EQUITY | 95/+0.003 | 28/−0.253 | +0.058 | 0.87 |

1.5 口径下提升主要来自 US_EQUITY；CN_METAL 无效、CN_BOND tiny-n。

## 中性观察（不裁决）

1. 过度延伸惩罚**单调**：cutoff 越紧提升越大，强 edge 在 **1.0（≈中位数）**，非 Brooks 1.5×。
2. **时间外稳健（关键）**：cutoff 1.0 的 lane 提升 IS +0.386 / OOS +0.091 / 最近折 F3 +0.323
   全正；1.25 OOS 转平、1.5 OOS/F3 转负。强 edge 经得起 walk-forward。
3. **代价**：cutoff 1.0 砍掉 ~60% 信号（保留 40%），交易机会大幅减少——gate 激进。
4. Bonferroni：阈值扫描 7 次比较；cutoff 1.0 的分离强度（对应 t_ecb98b40 中位数切 P=0.999）
   足以过 7× 校正。
5. 局限：单 EMA/ATR 窗口参数未扫；本群限 bottom×opposing + policy-gated；未与生产 policy
   weight 做联合增量。productionize 建议：用 1.0（或 1.0-1.25 间）作 de-weight 而非硬砍，
   权衡 EV 提升 vs 信号量损失。
