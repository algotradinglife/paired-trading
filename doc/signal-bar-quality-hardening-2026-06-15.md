# 信号棒质量 = 突破 setup 的正交硬化 filter（2026-06-15）

setup 空间已 EXHAUSTED（进场机制层：突破止损是唯一 edge，fade/回踩/反转全负——R006/R008/R009）。
本研究问**正交维度**：突破 setup 内部，**信号棒质量**（body_frac 实体占比、close_pos 收盘位置、
range_vs_avg 棒长/均值）是否分层 EV？是 → 质量 filter 可硬化 setup 而不改进场机制。
对齐 researcher 既有 swing-quality 发现（tight|wick 独立、range_vs_avg 棒长惩罚是 PA-sweep 唯一正交正向）。

工具 `scripts/analyze_signal_bar_quality.py`（复用 canonical `evaluate()`，按 id join features_det，
中位分层；质量方向 orientation：body_frac/close_pos 高=好，range 惩罚低=好，close_pos 随多空翻转；
覆盖率诚实警告）。**机械统计，研究性/样本内中位分层，不打 PASS/FAIL。** reviewer t_ba0ba553 已审核通过。

## 结果 A：rb-only（philosopher 原始 labels，仅 rb 带 features_det，n=43）
复现：`cd src && TP=/home/drwho1985/workspace/quant/strats/trade-philosopher/runs/_replica`
`python3 scripts/analyze_signal_bar_quality.py --corpus $TP/pa_dataset_rb_claude.jsonl $TP/labels_cu.jsonl $TP/labels_au.jsonl`
（cu/au 原始 labels 缺 bar 几何 → 45/88 单无 features，strata 仅 rb n=43，baseline +0.773R）

## 结果 B：pooled rb+cu+au（P3 合并数据集，全品种带 features_det，n=88）⭐
复现：`cd src && python3 scripts/analyze_signal_bar_quality.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`
（P3 数据集 pa_dataset_rbcuau.labeled.jsonl 对全 3512 候选有确定性 features_det + 330 复刻决策 rb120/cu120/au90
→ **全品种 features 覆盖，解除 A 的 rb-only caveat**）

| 指标（做多，n=88，baseline +0.731R） | 好半 | 差半 | Δ(好−差) |
|---|---|---|---|
| **body_frac** | +1.002R（n=45，胜率71%，CI[0.56,1.46]） | +0.447R（n=43，CI[0.06,0.83]） | **+0.555R** |
| **close_pos** | +1.000R（n=45，CI[0.57,1.47]） | +0.448R（n=43，CI[0.06,0.82]） | **+0.552R** |
| range_vs_avg（棒长惩罚，低=好） | +0.856R（n=44） | +0.605R（n=44） | **+0.251R** |
| bar_range（绝对幅度惩罚，低=好） | +0.672R | +0.786R | −0.114R（不一致，弃） |

## 结论
- **body_frac（大实体）+ close_pos（收极值）是稳健正交硬化 filter**：好半 ~+1.0R（CI 排除 0）vs 差半 ~+0.45R，
  **pooled Δ≈+0.55R**，跨 rb+cu+au 成立，且 pooled 比 rb-only 略强（A：Δ+0.52/+0.51；B：Δ+0.555/+0.552）。
  即 Brooks 强信号棒 + researcher swing-quality 迁移到忠实复刻突破语料成立。
- **range_vs_avg 棒长惩罚 pooled 证实**（Δ+0.25R，短/正常棒优于过长棒）——与 PA-sweep 既有结论一致。
- **bar_range（绝对幅度）无一致 edge**（pooled Δ−0.11）→ 弃；质量看相对几何（实体占比/收盘位置/相对棒长）非绝对幅度。
- 短边 n=13 太小（baseline 甚至 −0.08，与 SPEC-003 labels_short n=16 +0.50 不同语料）→ 不可读，方向同但 CI 巨大。

## 结果 C：组合 filter 交集（body_frac 高 AND close_pos 高，pooled n=88）—**研究性候选，非已证叠加**
复现：`cd src && python3 scripts/analyze_signal_bar_quality.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`
（输出末段 COMBINED + 2x2 cells + marginal contrasts）

| 子集 | n | 留存 | 毛 EV | 胜率 | 95% CI |
|---|---|---|---|---|---|
| pass（双强交集） | 33/88 | 37.5% | +1.284R | 78.8% | [0.784, 1.814] |
| fail（其余） | 55/88 | — | +0.399R | — | [0.060, 0.736] |

**2x2 分区（A=body_frac 强，B=close_pos 强）**：A&B n=33 EV **+1.284**；A_only n=12 EV **+0.227**；
B_only n=12 EV **+0.221**；neither n=31 EV **+0.534**。
**边际对比（disjoint within-condition，统计有效——codex 纠正：交集 ⊂ 单 filter pass，嵌套重采样无效）**：
A&B − A_only（body 强下加 close 的边际）Δ**+1.056** CI **[0.149, 1.951]**（排除 0）；
A&B − B_only（close 强下加 body 的边际）Δ**+1.063** CI **[0.166, 1.946]**（排除 0）。

- **诚实结论（reviewer t_aa7cf0a6 + codex 双纠错）**：这**不是"两信号独立可叠加"**，而是**交互/合取（conjunction）**：
  **A_only/B_only（+0.22）EV 低于 neither（+0.53）**——只满足单个信号反而更差；唯有**双强交集**才好（+1.28R）。
  within-condition 边际（A&B vs 单 only）+1.06R 且 **CI 排除 0**（有效 disjoint 检验；reviewer 的嵌套 AB−A_pass +0.28/CI 跨 0
  被交集稀释而失真）→ **合取效应统计上成立**，但**建立在小 cell（A_only/B_only 各 n=12）上**。
- **部署含义**：**monotone full/half/light 仓位分层被 2x2 证伪**（单强档反而差）；合理的候选是**二元闸门**（双强=进/否则不进），
  非分层。但仍是**样本内、小 cell**，**落地前须 OOS/留出验证**。
- 既往（已撤回）措辞"近翻倍""独立可叠加""full/half/light 分层"均**降级**：保留"双强交集 +1.28R 候选"+"合取效应"。

## 局限 & 下一步
- 中位分层粗、样本内、未多重校正；short 欠功率；合取效应建立在小 cell（n=12）；二元闸门未 OOS 验证。
- **下一步（researcher）**：(a) 双强交集=样本内合取候选，待 OOS/留出才能称 edge；(b) **若落地 score_today，
  用二元质量闸门（双强进场加权）而非 full/half/light 分层**（2x2 已证伪 monotone 分层）；(c) 短边补样本；
  (d) 暂不落地生产，先补 OOS 统计证据。
工件 signal_bar_quality.json / signal_bar_quality_pooled.json（data/review gitignore）。
相关：[[spec001-ev-eval]]、[[swing-quality-hypothesis-validated]]、[[pa-hypotheses-sweep]]。
