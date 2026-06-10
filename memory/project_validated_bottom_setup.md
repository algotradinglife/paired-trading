---
name: project-validated-bottom-setup
description: bottom + lower_relation=leading + higher_relation=opposing 是经 Codex 严格验证的唯一强可交易信号
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**事实**（5y × 10 品种 × 3 TF, n=266, Codex 2026-05-23 严格验证后）：

**F2 (主力甜区)** — `direction=bottom + lower_relation=leading + higher_relation=opposing`:
- n=15, 93.3% 命中 @ h=20, +8.52% 平均收益（中位 +7.22%）
- h=10 上 100% 命中, +6.98% 平均
- 跨 10 品种 HHI=0.120（无集中）
- Drop top-2 winners: +8.52% → +6.95%（**outlier 鲁棒**）
- Bonferroni 通过：hit-rate p=0.0005, mean≠0 p=0.0001

**F3 (高置信度但需持续监控)** — `confidence_band=candidate × higher_relation=opposing`:
- n=14, **100% 完美胜率**, +6.13% 平均
- 14 个独立 (symbol, week)，无时间聚类
- Bonferroni 通过 p=0.00006
- ⚠️ 但 100% 本身是 alpha mining 危险信号，须随数据增长重新验证

**Why**: 60min/weekly 都还在反向 + daily 出 bottom 背离 = 经典"大级别反弹早期"。所有维度都看跌时的逆向背离，是真正捕捉了"动能衰竭+反转启动"的边界。

**How to apply**: 这两条已写入 `src/engine/divergence/downstream_policies.py` v1 策略。F3 带 `monitor_required: True` 标记，下游可选择是否打折。

**对照**：
- F1 `top + lagging` 红区只达边缘显著，soft de-weight 而非 drop
- F4 `top + leading + opposing` **对股票**线性策略崩塌（25 信号里 1 个 -35.66% 拖死 mean，p=0.599），**但对期权严止损策略友好**：去掉那个 outlier 后 24/25 ≈ 96% 小赢，通过 PUT gamma 可放大 10-50×。已写入 policy 作为 `F4-options-asymmetric` 带 `strategy_hints` 标记，weight=1.0 不动 confidence，让下游消费方按 payoff structure 决策。

**F8（Codex Round 2 新增，2026-05-23 验证）** — `direction=bottom + subtype=weakness`:
- n=123（迄今最大样本），68.3% 命中, +2.63% 平均收益
- Bonferroni hit p=0.0145, mean p=0.0115（均通过），Newey-West p=0.000018
- 仅 5% 信号在 2022 熊市（**非 regime 依赖**），与 F2 重叠只 2.4%（独立增量）
- 已写入 policy `F8-bottom-weakness-baseline` weight=1.10，作为通用底部增强基线

**Round 2 edge 候选不入 policy（仅作研究记录）**:
- F5 `standard + leading + in_cycle` (n=31, 83.9% / +3.55%) — 通过 Bonferroni 但方向不对称
- F6 `leading + in_cycle + opposing` (n=27, 88.9% / +4.43%) — F2 方向无关版，与 F2 重叠 33%
- F7 `bottom + opposing + W in_cycle` (n=36, 80.6% / **+6.72%** 最高收益) — Bonferroni hit p=0.074 不过；**50% 信号来自 2022 熊市**，regime 依赖
- F9 `lower_relation=leading` 单维 (n=84) — **方向无关版本崩塌**，只是 bottom asymmetry 再发现

