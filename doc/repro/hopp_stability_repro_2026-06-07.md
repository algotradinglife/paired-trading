# hopp-stability-crosspool 复现 — 2026-06-07

对照 `doc/legacy/hopp-stability-crosspool-report-2026-05-31.html`。

## 结论

**bit-exact 不可复现** —— 报告依赖的 `rr_b_*.csv` 在 2026-06-01 ~ 06-02 之间被新一轮回测覆盖，最早可获取版本均晚于报告 1–2 天，原始数据已永久丢失。

**用 2026-06-07 重新跑出的 baseline 检验报告结构性结论：只剩一半成立。**

## §1 年度 lift 对比

| Year | 报告 n_opp / Lift | 重跑 n_opp / Lift | 框架是否保留 |
|------|------------------|-------------------|--------------|
| 2021 | 20 / +0.471R PASS | 116 / **-0.031R** | ❌ 翻转 |
| 2022 | 24 / +0.818R PASS | 240 / **+0.026R** | ❌ lift 归零 |
| 2023 | 10 / +0.753R PASS | 162 / +0.182R | ✅ 减半但仍 PASS |
| 2024 | 21 / -0.107R FAIL | 184 / -0.183R | ✅ 仍 FAIL |
| 2025 | 21 / +0.791R PASS | 155 / +0.093R | ✅ 减弱但仍 PASS |
| 2026 YTD | 6 / -0.123R | 51 / -0.267R | ✅ 仍负 |

报告"4/6 PASS"叙事不成立：新数据下 2021/2022 不再清晰 PASS。

## §2 2024 分池

| Pool | 报告 Lift | 重跑 Lift | 是否保留方向 |
|------|----------|-----------|-------------|
| CN_METAL | -0.981R | **-0.511R** | ✅ 保留 |
| CN_AGRI | -1.250R | +0.437R | ❌ 翻转 |
| CN_INDEX | -0.150R | +0.682R | ❌ 翻转 |
| US_EQUITY | +0.167R | -0.068R | △ 接近零 |
| US_MACRO | +0.875R | **+0.510R** | ✅ 保留 |

报告"2024 = CN 商品拖累 + US 抗压"二选一成立：CN_METAL 仍负、US_MACRO 仍正；但 CN_AGRI 完全翻转。

## 样本数为什么变了 5–10 倍

引擎新增 6 个 `intra_cycle_*` level 变体（参考 `cn_b_topology_repro_2026-06-07.md`）。
报告时每年 ~20 opp 信号的窄基底，在新检测器下扩展为 ~150–240。

## 数据来源

- 5 池 baseline CSV: `data/review/rr_b_{cn_metal,cn_agri,cn_index,us_equity,us_macro}.csv`
  （通过 `scripts/backtest_rr_pool.py --pool <POOL>` 重生成，源 bar 数据走 Parquet 默认路径）
- 聚合脚本: `tools/repro_hopp_stability.py`

## 留底

新 baseline 应作为后续策略评估的起点。原报告留作历史参照——结论不要照搬。
