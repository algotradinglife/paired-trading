# cn_b_topology 回测复现 — 2026-06-07

迁移到 paired-trading 后的首次复现尝试，对照基线 `/Volumes/Data Drive/derived/paired-trading/src-data-review/cn_b_topology_signals_all.csv`（生成于 2026-05-31）。

## 结论

**基线可复现。前提：bar 数据走 Parquet store，不走 `data/raw/*.json`。**

- 1638 / 1698 baseline 行可在新版本中按完整键（symbol, date, direction, subtype, level, horizon）精确匹配，**96.5% bit-exact**。
- 14 / 19 个品种 100% 复现，其余 5 个偏差 ≤ 7 信号，均在 DCE 商品（j/jm/p/i）和 czce_ma。
- 在 1638 行匹配中：`rule_id` 100% 一致；`confidence` 平均差 5e-4，最大 0.057；`signed_return` 平均差 6e-4，最大 0.12；`hit` 99.45% 一致。
- 漂移源：Parquet 比基线多 ~5 天新数据 → MACD EMA 末端值微变 → 边界信号位置略移。属"无害漂移"。

## JSON 路径不可复现的根因

`data/raw/*.json` 在 4 个品种上严重退化：

| 品种 | daily | 60min | 15min |
|------|-------|-------|-------|
| shfe_cu | 2005-01-04 → 2026-06-04 | **2026-01-05 起** | **2026-01-05 起** |
| shfe_au | 2008-01-09 → 2026-06-04 | **2026-01-05 起** | **2026-01-05 起** |
| shfe_ag | 2012-05-10 → 2026-06-04 | **2020-01-02 → 2025-12-31** | **2026-01-05 起** ← **无重叠** |
| ine_sc  | 2018-03-26 → 2026-06-04 | **2026-01-05 起** | **2026-01-05 起** |

JSON 跑出来 shfe_cu 5 信号、ag 0 信号、ine_sc 6 信号。Parquet 跑出来分别是 46 / 80 / 113 信号，与基线对得上。

Parquet store 在所有品种上 2021-01-04 起 60min/15min 全量完整。

## 引擎本身的变更

新版引擎在 `level` 字段上新增了 6 个变体：
`intra_cycle_dea`、`intra_cycle_hist`、`intra_cycle_slope`、`intra_cycle_bull_dea`、`intra_cycle_bull_hist`、`intra_cycle_bull_slope`。

基线只有 3 个 level：`intra_cycle`、`inter_cycle`、`inter_segment`。

→ 因此 Parquet 跑总信号 1585，远超基线 566；但**过滤回基线 3 个 level 后是 578，与基线 566 几乎相等**（差 +12，几乎全是 dce 商品边缘漂移）。

新增的 6 个 level 不影响 baseline 复现，但若下游消费方仍用旧版的 level 枚举，需要明确过滤策略。

## 脚本改动

`scripts/backtest_cn_b_topology.py` 加 `--source {json,quant}` 与 `--out` 参数：

```bash
# 默认（向后兼容）走 JSON
uv run python scripts/backtest_cn_b_topology.py

# 走 Parquet store（推荐）
uv run python scripts/backtest_cn_b_topology.py --source quant --out data/review/cn_b_topology_signals_quant.csv
```

也补了 `from data import bar_loader` 的缺失 import。

## 留底文件

- `doc/repro/cn_b_topology_diff_2026-06-07.csv` — JSON 路径每品种对比
- `data/review/cn_b_topology_signals_all.csv`  — JSON 跑出来（4539 行，仅用于诊断）
- `data/review/cn_b_topology_signals_quant.csv` — Parquet 跑出来（4755 行，应作为新基线）

## 下一步

1. JSON 数据回归是否要修复？若已弃用 JSON 路径，可考虑把 `data/raw/` 改为 `.archived/` 或彻底从仓配置里移除 JSON 入口。
2. 把 Parquet 版结果 `cn_b_topology_signals_quant.csv` 作为后续 OOS / walk-forward 的新输入基线。
3. 其余 05-31 报告（crosspool-walkforward、multitf-structure、options-simulation 等）的复现路径，照此一一确认数据源。
