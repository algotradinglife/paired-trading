---
name: project-signal-source
description: "paired-trading project's strategic direction — switching off DIF-based signal classification toward Price Action (PA)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

paired-trading 未来的信号体系**全面走 Price Action (PA)，DIF 全退役**（2026-06-08 用户原话"DIF 全退役"）。这条规则覆盖：
- 6 个 `intra_cycle_*` 变体（HICD / DIFSR / DEAD ± bull）—— 已经在源码里加 DEPRECATED banner
- 3 个 classical DIF 检测器（`intra_cycle` / `inter_cycle` / `inter_segment`）—— 源码未加 banner 但生产层已退役

**Why:** 用户两次明确判断 DIF 不是好的信号划分维度（先 6 个变体，再扩展到 classical 3）。之前 baseline 报告失效的根因——detector 加了 6 个变体导致样本爆炸 2.4–10x 并稀释 EV——是 DIF 路径副作用。代码里已有 `CN2-bottom-weak-sublevel-disabled` gate 内部承认 `intra_cycle_dea` / `intra_cycle_slope` 在 CN 商品 bottom × opposing 下 OOS 是负的。`scripts/score_today.py` 在 2026-06-08 commit `6936170` 起默认过滤 6 个 deprecated；commit `<next>` 扩展到 9 个，flag `--include-dif-detectors` opt-in。

**How to apply:**
- 不要再深挖任何 DIF 检测器（含 classical 3）的 isolation / 调参 / 性能分析
- 不要为 hopp_stability / crosspool_walkforward / crosspool_merge / multitf_structure / strategy_report 这些以 DIF 信号为底的旧报告做"恢复信号源"努力——它们的叙事在新数据下已经塌了，未来用 PA 体系重新建立 baseline
- 新功能 / 新回测优先走 `engine/divergence/pa_*` 与 `scripts/backtest_pa_*` 系列（pa_detector、pa_context_classifier、pa_structure、pa_swing、pa_us_k3 等已经在仓里）
- 生产 scorecard 默认无 DIF 记录；只有历史 CSV 回放或 A/B 对比需要时才 `--include-dif-detectors`
- 仅当用户主动说"看一下 DIF 那块"时，再进 DIF 代码

相关：[[project-repro-status]]（如果以后写）记录 8 份 2026-05-31 报告复现矩阵；[[user-preferences]]（如果以后写）记录用户判断风格。
