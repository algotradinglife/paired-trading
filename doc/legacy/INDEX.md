# doc/legacy/ — 历史报告归档

这个目录收纳了 2026-05-30 和 2026-05-31 产出的 8 份 HTML 报告。它们是
旧版 DIF 检测通道下的产物；DIF 通道在 paired-trading 中已经退役
（commits 88eca10 / 6936170 / b683663 之后 PA 通道成为唯一活跃信号
通道），detector 也在 2026-05-31 之后扩展出 6 个 `intra_cycle_*` level
变体，使样本量整体扩大 2-10×。

这 8 份报告都已在 `doc/repro/*.md` 中以 2026-06-07/08 数据重跑过；
大多数核心叙事在新数据下失效。HTML 本身仍可加载，但应被视为历史快照，
而不是当前可信结论。新读者请先看对应的 repro 文件。

## 报告与复现对照

| 归档 HTML | 对应复现 | 核心叙事是否存活 |
|-----------|----------|------------------|
| `confidence-reversal-report-2026-05-31.html` | `doc/repro/confidence_reversal_repro_2026-06-07.md` | 存活 — "TOP × mid 弱化" 数字逐项复现 |
| `crosspool-merge-report-2026-05-31.html` | `doc/repro/crosspool_merge_repro_2026-06-07.md` | 坍塌 — Portfolio Sharpe 0.860 → 0.143，仅"5 池都为正"保留 |
| `crosspool-walkforward-report-2026-05-31.html` | `doc/repro/crosspool_walkforward_repro_2026-06-07.md` | 降级 — STRONG PASS 降级为基础 PASS，F2 Sharpe 5.11 → 1.29 |
| `hopp-stability-crosspool-report-2026-05-31.html` | `doc/repro/hopp_stability_repro_2026-06-07.md` | 半存活 — bit-exact 不可复现，2021/2022 年 lift 翻转，2023+ 框架仍 PASS |
| `multitf-structure-report-2026-05-31.html` | `doc/repro/multitf_structure_repro_2026-06-07.md` | 坍塌 — 21 条逐品种行只 2 hold/3 drift，10 fail/5 FLIP，立论失败 |
| `options-crossmarket-report-2026-05-31.html` | `doc/repro/options_crossmarket_repro_2026-06-07.md` | 部分存活 — POOLED 在 ±5pp 内，但 CN_METAL 不再是最强池 |
| `options-simulation-report-2026-05-31.html` | `doc/repro/options_simulation_repro_2026-06-07.md` | 坍塌 — 287 → 754 笔后 EV/胜率/出场分布全面下移；Black 仿真脚本已丢失 |
| `strategy-report-2026-05-30.html` | `doc/repro/strategy_report_repro_2026-06-07.md` | 坍塌 — 五大池 h=opp EV 全面下降，执行摘要几乎每个数字都对不上 |

## 注

- 不要从这些 HTML 复制结论到新报告。先确认对应 repro 的最新判定。
- `doc/repro/cn_b_topology_repro_2026-06-07.md` 复现的是 `cn_b_topology_signals_all.csv` 基线（非本目录任何一份 HTML），属于独立基线验证。
- `doc/repro/pa_*.md`（2026-06-08）是 PA 通道的新分析，不依赖本目录任何文件。
