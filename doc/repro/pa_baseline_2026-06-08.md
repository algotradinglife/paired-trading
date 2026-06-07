# PA 体系首份 baseline — 2026-06-08

paired-trading 不再投入 DIF 路径，转 PA。本份建立 PA 体系在新数据下的第一份 baseline，验证引擎 docstring 里的策略权重声明。

## 引擎家底

3 个模块：
- `engine/divergence/pa_detector.py` — H2 底部检测器（Brooks-style，独立于 MACD）
- `engine/divergence/pa_context_classifier.py` — Context A / B1 分类器
- `engine/divergence/pa_structure.py` — BULL / TR / BEAR / UNCLEAR phase 与 structural stop

10 个 backtest 脚本，分 6 类：Entry 验证 / Stop+仓位 / Phase gate / Recall 验证 / Hybrid w/ MACD / Intraday confirm（详见 conversation log）。

## 验证矩阵

| 引擎 docstring 声明 | 重跑结果 | 结论 |
|---------------------|---------|------|
| `us_equity` uptrend+h=opp **weight 0.80** | EV +0.384R (n=56), F1+0.625 F2+0.708 | ✅ 强支持 |
| `us_equity` legs=1 bonus → 0.90 | EV +0.595R (n=21), hit 62% | ✅ 方向成立，n 仍小 |
| `cn_metal_futures` h=opp **weight 0.75** | EV +0.524R (n=46), F1+0.591 F2+1.045 F3+0.255 | ✅ Parquet 路径下 fully supported |
| `cn_futures` h=opp 0.55 | 未验证（pa_swing 默认无 CN_COMMODITY dataset） | — |
| `czce/cn_agri` 0.0 suppressed | 未验证 | — |

## US 60min 全表（`backtest_pa_swing.py --dataset us_60min`）

### Trend × h=opposing

| trend × h=opp | n | EV | hit% | IS | F1 | F2 |
|---|---|---|---|---|---|---|
| **uptrend** | 56 | **+0.384R** | 52% | -0.150 (n=20) | +0.625 (n=12) | +0.708 (n=24) |
| ranging | 62 | +0.161R | 42% | +0.115 | +0.625 | -0.150 |
| downtrend | 94 | -0.032R | 32% | +0.056 | -0.177 | +0.017 |

### Per-symbol (uptrend + h=opp)

强：nvda +1.200R / gdx +1.000R / spy +0.929R / xlf +0.417R
弱：gld -0.167R / iwm -0.167R / tlt +0.100R / xlk +0.000R

### legs_count_down (uptrend + h=opp)

| legs | n | EV | hit% |
|------|---|----|------|
| 0 | 34 | +0.221R | 44% |
| **1** | 21 | **+0.595R** | **62%** |
| 2 | 0 | — | — |
| 3 | 1 | +1.500R (噪声) | 100% |

## CN_METAL daily（`backtest_pa_cn_structural.py`）

⚠️ **必须先修 Parquet 路径**：脚本原版默认 `data/raw/` JSON，遇到 ag/au/cu/sc 的 60min JSON 截断到 2026-01-05 仅 5 个月，h=opposing 几乎都判不出来。本份 baseline 把 `load_bars` 改成走 `bar_loader.load_bars_quant` 优先。

### Parquet 之后的对比

| 设置 | n (JSON→Parquet) | EV (JSON→Parquet) |
|------|------------------|------------------|
| ALL h=opp | 11 → **46** | **-0.186R → +0.524R** |
| DIF<0 h=opp | 6 → 21 | +0.493R → +0.476R |
| DIF>0 h=opp | 5 → 25 | n/a → **+0.565R** |

3 fold 全正：IS — / F1 +0.591R / F2 +1.045R / F3 +0.255R。

### Phase 切片（h=opp + Parquet）

| Phase | n | EV | F1 | F2 | F3 |
|-------|---|----|----|----|----|
| **TR** | 38 | **+0.666R** | +1.143R | +1.250R | +0.229R |
| BULL | 7 | -0.026R | -0.375R | — | +0.439R |
| BEAR | 1 | — | — | -1.000R | — |

**核心发现**：CN_METAL PA H2 在 TR phase 极强，BULL phase 反而失效——验证了 `backtest_pa_cn_phasefilter` 假设"排除 BULL phase 改善 EV"。

### Structural vs ATR stop

ATR 整体 EV +0.524R 略好于 Struct +0.413R；DIF<0 子集 Struct 反超 (+0.549R vs +0.476R)。median 止损距离 ATR 3.4% vs Struct 5.9%（Struct 更宽）。

## 工程注记

`scripts/backtest_pa_cn_structural.py` 已 patch：`load_bars` 改为优先走 BarStore（Parquet），失败才落回 JSON。这条 patch 应该应用到所有读 `data/raw/_60`、`_15` 的脚本上——因为这些 intraday JSON 都有截断风险。

## 下一步建议

1. **稳定线**：US uptrend+h=opp + legs=1 + CN_METAL TR-phase h=opp 是当前可立刻用的两条最稳子集
2. **n 缺口**：US uptrend+h=opp F2 n=24，距 production threshold (n≥50/fold) 还差一倍；可考虑加 60min 数据扩样
3. **未覆盖**：`cn_futures` 0.55 与 `czce/cn_agri` 0.0 weight 还没数据验证，对应 `backtest_pa_cn_phasefilter` 或新建 dataset
4. **PA 之外**：Context A/B1 (`pa_context_classifier`) 和 Incremental recall (`backtest_pa_incremental`) 是 PA 真正的"扩 recall"工具，没在本 baseline 跑

## 代码

- `scripts/backtest_pa_swing.py` (US 60min + CN_METAL daily, 入口)
- `scripts/backtest_pa_cn_structural.py` (CN_METAL daily, 已 Parquet 化)
- 输入：JSON `data/raw/spy_60.json` 等（US 健全）+ Parquet `data/quant/SHFE/AU0/60min/` 等（CN 健全）
- 输出：`/tmp/pa_swing_us_60min.csv`、`/tmp/pa_swing_cn_metal_daily.csv`、`/tmp/pa_cn_structural.csv`
