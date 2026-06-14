# P3a 端口验证：过度延伸/二次入场 de-weight 在 context_a 活跃 lane 上无显著增益（2026-06-14）

卡片 t_50cb7876 / 修复 t_b186d176（reviewer t_5f320e96）。**机械统计，不打 PASS/FAIL。**

> **v3（t_b186d176 修复，含 codex P2）**：population = 真实**活跃发射 lane**——路由经
> `ContextADetector.policy_weight()>0`（h=opposing + 生产 symbol suppression US: DIA/SPY/XLU、
> CN_METAL: kq_m_ine_sc）**＋ score_today 的 US P2 regime 门**（SPY risk-off 日 US context_a
> 不发；SPY 缺失则 fail-open）。样本：v1 n=181（无 suppression）→ symbol suppression 后 n=150
> （剔 SPY 10/DIA 5/sc 16）→ 再加 regime 门后 **n=140**（US 90→80）。结论方向三版一致。

## 为什么做这个
de-weight（`w = w_a(range_vs_avg) × w_b(ordinal)`，bottom 侧）在**研究群**上验证：
`detect_all_divergences`（通用 MACD 背离）bottom×opposing，以 `apply_policy` 为门。但生产
**不发这个群**——活跃 bottom×opposing 走各自 `policy_weight()` 的专用 detector
（`context_a`/`pa_us_60min`/`pa_cn_bond`/`pa_h2`）。接生产前必须先验 edge 是否**移植**。
本卡验 context_a（最近的类比；只 2 条 baseline；US+CN_METAL 两池均已 h=opposing 验证）。

## 口径
复用 context_a lane 回测约定 verbatim（`scan_context_a`/`simulate_trade`：stop=1.5×ATR、
1R:1R:1.5R、max_hold=40、min_gap=10）+ 生产 de-weight 模块（`overext_features` /
`overext_deweight.deweight_factor`，与验证脚本数值 parity）。**population = 活跃发射 lane**：
`ContextADetector.policy_weight()>0`（h=opposing + symbol suppression）＋ US P2 regime 门
（SPY risk-off）。bootstrap 10k/seed=42。数据走 quant store（`bar_loader`）。

## 结果（n=140，活跃 context_a 发射 lane；US 80 + CN_METAL 60）

| 方案 | n / 有效 n | EV / weighted-EV |
|------|-----------|------------------|
| full（等权） | 140 | **+0.310** |
| 硬 AND（rva≤1.0 ∧ ord==1） | 21 | +0.452 |
| 连续加权（生产 deweight_factor） | eff_n 93.3 | **+0.335** |

- 连续加权 vs 等权 bootstrap：gap **+0.023**，CI **[−0.113, +0.157]**，P(gap>0)=**0.64**
  ——**跨 0，统计上无差异**。
- 分池：US gap +0.039 CI[−0.140,+0.217] P=0.68；CN_METAL gap +0.003 CI[−0.199,+0.202] P=0.52。
  两池都跨 0、无信号。
- 硬 AND EV 看似高（+0.452）但 n=21 极小、未 bootstrap，且砍掉 85% 信号。

## 关键：两条 gate 在 context_a 上都**不移植**

**w_a 过度延伸**（range_vs_avg 五分位 EV）：

| rva 区间 | n | EV |
|----------|---|-----|
| [0.43, 0.76] | 28 | +0.092 |
| [0.76, 0.89] | 28 | +0.268 |
| [0.89, 1.06] | 28 | +0.470 |
| [1.06, 1.31] | 28 | +0.362 |
| **[1.31, 2.34]** | 28 | +0.357 |

→ EV 不随棒长单调下降（最小棒反而最低 +0.092、大棒 ~+0.36）。研究群的"过度延伸惩罚"在
context_a 不成立（降权大棒无依据）。

**w_b 二次入场**（ordinal EV）：

| ordinal | n | EV |
|---------|---|-----|
| 1（首测） | 39 | +0.372 |
| **2（二测）** | 49 | **+0.457** |
| 3+（三测+） | 52 | +0.124 |

→ **二测 EV 最高、≥ 首测**。研究群的"首测>二测"在 context_a 不成立（降权回踩无依据）。

时间外（lane K=3）：连续 vs 等权 IS +0.106 vs +0.138、F2 +0.051 vs +0.100 略差，
F1 +0.623 vs +0.457 / F3 +0.534 vs +0.503 略好——无一致方向，整体被 CI 跨 0 覆盖。

## 结论（陈述，非裁决）
在**活跃 context_a 发射 lane（n=140）**上，de-weight **无统计显著增益**：连续加权把 EV
从 +0.310 抬到 +0.335，gap +0.023 但 CI[−0.113,+0.157] 跨 0、P=0.64。两条组件 gate 都
**不移植**——过度延伸惩罚在 context_a 上随棒长 EV 不降（大棒 ~+0.36、最小棒最低 +0.092），
二次入场上二测 ≥ 首测。**据此，把该 de-weight 接入 context_a.policy_weight 不被数据支持**
（中性，徒增复杂度）。de-weight edge 特定于研究用通用背离群。

## 对 P3 的含义
- 研究群（apply_policy 门）在生产里**休眠**（score_today 主环未做 HTF 富化、baseline 由
  detector lane 生成），接 apply_policy 的 de-weight 对现有产物零效果。
- context_a 不移植（中性）。是否再验 `pa_us_60min`/`pa_cn_bond`/`pa_h2`？鉴于 context_a 干净
  非移植，跨结构差异更大 detector 概率低。
- 倾向：把 de-weight 作为**研究结论**留档（对通用背离群成立），**暂不接生产**。

## 局限
单 lane（context_a）；n=140 中 hard-AND 仅 21；context_a 自身 IS 段偏弱（+0.138）。
注：本卡按 score_today 活跃发射口径（`ContextADetector.policy_weight` + US P2 SPY regime 门）
统计；`backtest_full_stack._lane_context_a`（baseline 生成口径）另对 context_a 额外剔除
`US_LONG_BOND_SUPPRESS`（tlt 等，2 事件）且**不**应用 regime 门——两口径差异是已知 lane/
baseline nuance，不影响"无显著增益+不移植"的结论方向。regime 门 fail-open（SPY 缺失时不剔），
本次 SPY 可用故 US 80（90−10 risk-off）。
脚本 `scripts/analyze_context_a_deweight.py`；工件 `src/data/review/context_a_deweight.json`
（gitignore，命令重生）。复现：
`python3 scripts/analyze_context_a_deweight.py --out data/review/context_a_deweight.json`。
相关：[[deweight-curve-2026-06-13]]、[[combined-gate-design-2026-06-13]]、[[pa-hypotheses-sweep-2026-06-13]]。
