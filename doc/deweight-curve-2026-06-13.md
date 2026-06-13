# 连续 de-weight 曲线标定（P2.5，2026-06-13）

卡片 t_d257eb33（epic t_d6dccbab，P3 备料）。**机械统计 + 标定，不打 PASS/FAIL；
P3 接生产 policy/confidence 仍需 Hermes 签字。** 本文件给 P3 一套可落地的连续权重函数 +
"连续 vs 硬 AND" 的保信号量证据。

## 背景

P2 综合设计建议连续 de-weight（w_A×w_B）而非硬 AND（硬筛只留 11% 信号），但 Phase 1
只验了二值 cutoff。本卡标定连续权重的 EV-vs-feature 形状。bottom×opposing，n=312（CN+US）。
复用 analyze_combined_gate 事件（range_vs_avg + ordinal + realized_r + date，确定性）。

## w_A 形状（range_vs_avg 五分位箱 EV）

| range_vs_avg 区间 | n | EV(R) | w_a(中点) |
|-------------------|---|-------|-----------|
| [0.36, 0.77] | 63 | +0.398 | 1.00 |
| [0.77, 1.01] | 62 | +0.345 | 1.00 |
| [1.01, 1.21] | 62 | **−0.134** | 0.89 |
| [1.21, 1.53] | 62 | **−0.192** | 0.63 |
| [1.53, 4.46] | 63 | −0.077 | 0.20 |

**EV 在 ~1.0 处由正翻负**——cut=1.0 位置得到独立确认；越过度延伸 EV 越差（尾部小回升
是噪声）。连续降权函数 `w_a = clip((1.0 − rva)/1.0 + 1, 0.2, 1)`（≤1.0 满权、之上线性
降到下限 0.2）与该形状吻合。

## w_B 形状（ordinal）

| ordinal | n | EV(R) | w_b |
|---------|---|-------|-----|
| 1（首测） | 85 | +0.364 | 1.00 |
| 2（二测） | 97 | −0.149 | 0.20 |
| 3+（三测+） | 130 | +0.038 | 0.20 |

首测独占正 EV；二测负、三测+近零 → w_b 对 2nd+ 重降权（`clip(ev_ord/ev_first, 0.2, 1)`）。

## 三方案对比（同一 n=312 事件群）

| 方案 | n / 有效 n | EV / weighted-EV |
|------|-----------|------------------|
| full（等权） | 312 | +0.069 |
| 硬 AND（rva≤1.0 ∧ ord==1） | **35** | +0.665 |
| **连续加权（w_a×w_b）** | **eff_n 156.7** | **+0.275** |

- 硬 AND EV 最高（+0.665）但**砍掉 89% 信号**（n=35）。
- **连续加权把 EV 从 +0.069 抬到 +0.275（≈4×），同时保住约一半有效信号量（eff_n 157 vs 35）**
  ——P2 "连续优于硬筛" 的量化支撑。
- 连续加权 vs 等权 bootstrap：gap **+0.206**，CI **[+0.080, +0.330]**，P=**0.999**（显著）。

## 无前视：IS 标定 w_b → OOS 应用

IS（≤2025-06-30）标定 w_b（ord2→0.2, ord3→0.73），用于 OOS：
- OOS 等权 EV −0.225 → OOS 连续加权 weighted-EV −0.106，**weighted−equal = +0.119**（eff_n 51.8）。
- OOS 段整体负（regime 偏弱），但连续加权仍把 EV 相对抬高 +0.119——方向 OOS 一致。

## 给 P3 的可落地件（不裁决，供 Hermes）

- 权重函数：`w = w_a(range_vs_avg) × w_b(ordinal)`，w_a/w_b 形如上（参数 cut=1.0、
  scale=1.0、w_min=0.2，可在 P3 再微调）。
- 接法：作 downstream_policies 现有权重的**乘法因子**（限 bottom×opposing/neutral），
  不替换 lane 路由；连续降权保信号量、避免硬 AND 的 89% 信号损失。
- 待 Hermes 定：w_min 下限、是否对 w_a 也用 IS 标定（本卡 w_a 用固定形状、仅 w_b 做了
  IS→OOS）、与现有 policy weight 的联合增量回测口径。

## 局限

w_a 用固定形状（未 IS 标定，仅 w_b 做无前视）；bottom×opp 限 60min HTF 覆盖（~2016 起）；
OOS 段整体负 regime；五分位箱 EV 单点。脚本 scripts/analyze_deweight_curve.py + 4 单测；
工件 src/data/review/deweight_curve.json（gitignore，命令重生）。
复现：`python3 scripts/analyze_deweight_curve.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/deweight_curve.json`。
