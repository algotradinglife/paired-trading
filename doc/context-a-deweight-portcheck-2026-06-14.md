# P3a 端口验证：过度延伸/二次入场 de-weight 在 context_a 活跃 lane 上不可移植（2026-06-14）

卡片 t_50cb7876（epic t_d6dccbab，P3）。**机械统计，不打 PASS/FAIL。**

## 为什么做这个
de-weight（`w = w_a(range_vs_avg) × w_b(ordinal)`，bottom 侧）是在**研究群**上验证的：
`detect_all_divergences`（通用 MACD 背离）bottom×opposing，以 `apply_policy` 为门
（backtest_rr_pool）。但生产**不发这个群**——活跃 bottom×opposing 走的是各自带
`policy_weight()` 的专用 detector：`context_a`（DIF>0 上升回踩）、`pa_us_60min`、
`pa_cn_bond`、`pa_h2`。接生产前必须先验 edge 是否**移植**到这些 lane。本卡验 context_a
（最近的类比；只 2 条 baseline；US+CN_METAL 两池均已 h=opposing 验证）。

## 口径
复用 context_a lane 回测约定 verbatim（`scan_context_a`/`simulate_trade`：stop=1.5×ATR、
1R:1R:1.5R、max_hold=40、min_gap=10）+ 生产 de-weight 模块（`overext_features` /
`overext_deweight.deweight_factor`，与验证脚本数值 parity）。限 h=opposing（活跃门）。
bootstrap 10k/seed=42。数据走 quant store（`bar_loader`）。

## 结果（n=181，context_a × opposing；US 105 + CN_METAL 76）

| 方案 | n / 有效 n | EV / weighted-EV |
|------|-----------|------------------|
| full（等权） | 181 | **+0.201** |
| 硬 AND（rva≤1.0 ∧ ord==1） | 32 | +0.172 |
| 连续加权（生产 deweight_factor） | eff_n 121.5 | **+0.192** |

- 连续加权 vs 等权 bootstrap：gap **−0.009**，CI **[−0.124, +0.106]**，P(gap>0)=**0.44**。
- 分池：US gap +0.004 CI[−0.151,+0.160] P=0.52；CN_METAL gap −0.023 CI[−0.193,+0.152] P=0.40。
  两池都跨 0、无信号。

## 关键：两条 gate 在 context_a 上都**反向**（非仅 null）

**w_a 过度延伸**（range_vs_avg 五分位 EV）：

| rva 区间 | n | EV |
|----------|---|-----|
| [0.43, 0.75] | 36 | +0.252 |
| [0.75, 0.89] | 36 | +0.014 |
| [0.89, 1.02] | 36 | +0.199 |
| [1.02, 1.29] | 36 | +0.254 |
| **[1.29, 2.34]** | 37 | **+0.284** |

→ context_a 上**最大棒 EV 最高**，与研究群"过度延伸惩罚"相反。降权大棒是错的。

**w_b 二次入场**（ordinal EV）：

| ordinal | n | EV |
|---------|---|-----|
| 1（首测） | 54 | +0.185 |
| **2（二测）** | 60 | **+0.373** |
| 3+（三测+） | 67 | +0.059 |

→ context_a 上**二测 EV 最高**，与研究群"首测>二测"相反。降权回踩是错的。

时间外（lane K=3）：连续 vs 等权 IS −0.110 vs +0.016、F2 −0.001 vs +0.065 反而更差，
F1/F3 略好——无一致方向。

## 结论（陈述，非裁决）
过度延伸/二次入场 de-weight 的 edge **特定于研究用通用背离群**，**不移植**到 context_a
detector（DIF>0 回踩）——在 context_a 上两轴均**轻微反向**，连续加权把 EV 从 +0.201
压到 +0.192（统计上等于无差）。**据此，把该 de-weight 接入 context_a.policy_weight 不被
数据支持**（会轻微拖累）。

## 对 P3 的含义
- 研究群（apply_policy 门）在生产里是**休眠**的（score_today 主环未做 higher-TF 富化、
  baseline 由 detector lane 生成），所以接 apply_policy 的 de-weight 对现有产物零效果。
- context_a 不移植。是否值得再验 `pa_us_60min` / `pa_cn_bond` / `pa_h2`？鉴于 context_a
  是**干净的非移植 + 反向**，跨到结构差异更大的 detector 移植概率低。
- 倾向：把 de-weight 作为**研究结论**留档（对通用背离群成立），**暂不接生产**；除非用户要
  我把端口验证扩到其余 lane。

## 局限
单 lane（context_a）；n=181 中 hard-AND 仅 32；context_a 自身 OOS 段 EV 偏弱（IS+0.016）。
脚本 `scripts/analyze_context_a_deweight.py`；工件 `src/data/review/context_a_deweight.json`
（gitignore，命令重生）。复现：
`python3 scripts/analyze_context_a_deweight.py --out data/review/context_a_deweight.json`。
相关：[[deweight-curve-2026-06-13]]、[[combined-gate-design-2026-06-13]]、[[pa-hypotheses-sweep-2026-06-13]]。
