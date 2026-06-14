# P3a 端口验证：过度延伸/二次入场 de-weight 在 context_a 活跃 lane 上无显著增益（2026-06-14）

卡片 t_50cb7876 / 修复 t_b186d176（reviewer t_5f320e96）。**机械统计，不打 PASS/FAIL。**

> **v4（t_1f35573f 修复）**：US universe 改为源自 **`score_today.POOLS['US']`（14 symbols，
> 活跃发射口径）**，而非 backtest_context_a_ev.POOLS（10 symbols，漏 XLB/XLE/XLRE/XLU）。
> 加回 XLB 9/XLE 14/XLRE 6（XLU 被 suppress=0）→ **n=169**。
>
> **演进**：v1 n=181（无 suppression）→ v2 n=150（symbol suppression）→ v3 n=140（+US regime 门）
> → **v4 n=169（+ score_today 全 US universe）**。population = 活跃发射 lane：路由经
> `ContextADetector.policy_weight()>0`（h=opposing + symbol suppression US: DIA/SPY/XLU、
> CN_METAL: kq_m_ine_sc）＋ score_today US P2 SPY risk-off regime 门（SPY 缺失则 fail-open）。
> 结论方向四版一致（de-weight 无显著净增益）。

## 为什么做这个
de-weight（`w = w_a(range_vs_avg) × w_b(ordinal)`，bottom 侧）在**研究群**上验证：
`detect_all_divergences`（通用 MACD 背离）bottom×opposing，以 `apply_policy` 为门。但生产
**不发这个群**——活跃 bottom×opposing 走各自 `policy_weight()` 的专用 detector
（`context_a`/`pa_us_60min`/`pa_cn_bond`/`pa_h2`）。接生产前必须先验 edge 是否**移植**。
本卡验 context_a（最近的类比；只 2 条 baseline；US+CN_METAL 两池均已 h=opposing 验证）。

## 口径
复用 context_a lane 回测约定 verbatim（`scan_context_a`/`simulate_trade`：stop=1.5×ATR、
1R:1R:1.5R、max_hold=40、min_gap=10）+ 生产 de-weight 模块（`overext_features` /
`overext_deweight.deweight_factor`，与验证脚本数值 parity）。**universe = `score_today.POOLS`
（US 14 + CN_METAL 4，活跃发射口径）**；**population = 活跃发射 lane**：
`ContextADetector.policy_weight()>0`（h=opposing + symbol suppression）＋ US P2 regime 门
（SPY risk-off）。bootstrap 10k/seed=42。数据走 quant store（`bar_loader`）。

## 结果（n=169，活跃 context_a 发射 lane；US 109 + CN_METAL 60）

| 方案 | n / 有效 n | EV / weighted-EV |
|------|-----------|------------------|
| full（等权） | 169 | **+0.322** |
| 硬 AND（rva≤1.0 ∧ ord==1） | 25 | +0.507 |
| 连续加权（生产 deweight_factor） | eff_n 112.2 | **+0.349** |

- 连续加权 vs 等权 bootstrap：gap **+0.027**，CI **[−0.098, +0.148]**，P(gap>0)=**0.67**
  ——**跨 0，统计上无差异**。
- 分池：US gap +0.039 P=0.69；CN_METAL gap +0.003 P=0.52。两池都跨 0、无信号。
- 硬 AND EV 看似高（+0.507）但 n=25 极小、未 bootstrap，且砍掉 85% 信号。

## 关键：过度延伸轴不移植；二次入场轴弱（均不显著）

**w_a 过度延伸**（range_vs_avg 五分位 EV）：

| rva 区间 | n | EV |
|----------|---|-----|
| [0.43, 0.74] | 34 | +0.274 |
| [0.74, 0.89] | 34 | +0.273 |
| [0.89, 1.06] | 33 | +0.353 |
| [1.06, 1.31] | 34 | +0.372 |
| **[1.31, 2.34]** | 34 | +0.338 |

→ EV **不随棒长下降**（大棒 +0.338 ≈ 中段、并不更差）。研究群的"过度延伸惩罚"在 context_a
**不成立**（降权大棒无依据）。

**w_b 二次入场**（ordinal EV）：

| ordinal | n | EV |
|---------|---|-----|
| 1（首测） | 46 | +0.373 |
| 2（二测） | 58 | +0.326 |
| 3+（三测+） | 65 | +0.282 |

→ 全 US universe 下首测 ≥ 二测 ≥ 三测，**弱单调、方向同研究群**，但梯度很浅（首尾差 ~0.09）
且不足以让组合 de-weight 显著（见上 gap P=0.67）。

时间外（lane K=3）：连续 vs 等权 IS +0.106 vs +0.138、F2 +0.107 vs +0.115 略差，
F1 +0.623 vs +0.457 / F3 +0.494 vs +0.489 略好——无一致方向，整体被 CI 跨 0 覆盖。

## 结论（陈述，非裁决）
在**活跃 context_a 发射 lane（n=169，score_today 全 universe）**上，de-weight **无统计显著
增益**：连续加权把 EV 从 +0.322 抬到 +0.349，gap +0.027 但 CI[−0.098,+0.148] 跨 0、P=0.67。
过度延伸轴**不移植**（EV 不随棒长降，大棒不更差）；二次入场轴呈**弱**研究方向梯度（首测略
>回踩）但浅且不显著。**据此，把该 de-weight 接入 context_a.policy_weight 不被数据支持**
（净效应中性，徒增复杂度）。de-weight 的强 edge 特定于研究用通用背离群。

## 对 P3 的含义
- 研究群（apply_policy 门）在生产里**休眠**（score_today 主环未做 HTF 富化、baseline 由
  detector lane 生成），接 apply_policy 的 de-weight 对现有产物零效果。
- context_a 不移植（中性）。是否再验 `pa_us_60min`/`pa_cn_bond`/`pa_h2`？鉴于 context_a 干净
  非移植，跨结构差异更大 detector 概率低。
- 倾向：把 de-weight 作为**研究结论**留档（对通用背离群成立），**暂不接生产**。

## 局限
单 lane（context_a）；n=169 中 hard-AND 仅 25；context_a 自身 IS 段偏弱（+0.138）。
universe 取自 `score_today.POOLS`（US 14 含 XLB/XLE/XLRE/XLU + CN_METAL 4）= 活跃发射口径。
注：`backtest_full_stack._lane_context_a`（baseline 生成口径）另对 context_a 额外剔除
`US_LONG_BOND_SUPPRESS`（tlt 等）且**不**应用 regime 门——两口径差异是已知 lane/baseline
nuance，不影响"无显著增益"的结论方向。regime 门 fail-open（SPY 缺失时不剔），本次 SPY 可用。
脚本 `scripts/analyze_context_a_deweight.py`；工件 `src/data/review/context_a_deweight.json`
（gitignore，命令重生）。复现：
`python3 scripts/analyze_context_a_deweight.py --out data/review/context_a_deweight.json`。
相关：[[deweight-curve-2026-06-13]]、[[combined-gate-design-2026-06-13]]、[[pa-hypotheses-sweep-2026-06-13]]。
