# options-crossmarket 复现 — 2026-06-07

对照 `doc/legacy/options-crossmarket-report-2026-05-31.html`。

## 结论

**部分复现 (partial)**：跨市场 bottom×opposing 信号的样本数与池排序基本保留，POOLED EV 在 ±5pp 以内。
但单池数值存在显著 noise（CN_METAL EV -9.6pp，US_MACRO EV +9.9pp），且 win 率与 tp1_tp2 比例下移。
**报告"跨市场 EV 全部为正"的定性结论保留**，但具体的池排名（CN_METAL 最强）在新数据下变为 US_MACRO 最强。

## 输入与方法

- 输入：`data/review/rr_b_{cn_index,cn_agri,cn_metal,us_equity,us_macro}.csv`
- 信号过滤：`direction=bottom` 且 `higher_relation=opposing`
- 信号 level 过滤：仅保留原始 `{intra_cycle, inter_segment, inter_cycle}`，剔除 2026-05-31 之后新增的 6 个 `intra_cycle_{dea,hist,slope}` + `intra_cycle_bull_{dea,hist,slope}` 变体（否则样本被稀释 9-10 倍）。
- Black 模型期权定价脚本已丢失。改用 companion report `doc/legacy/options-simulation-report-2026-05-31.html` 中明确公布的 per-outcome ATM 期权回报代理：
  - tp1_tp2 → +67.8%，tp1_max → +25.1%，tp1_stop → -48.9%，max_hold → -75.6%
  - full_stop → -8.8% (4tick) / -41.2% (ATR)

## §一 跨市场一致性（ATM 4tick）

| 池 | n (rpt) | n (now) | EV_R (rpt) | EV_R (now) | EV_4tk (rpt) | EV_4tk (now) | win (rpt) | win (now) | 复现 |
|----|--------:|--------:|-----------:|-----------:|-------------:|-------------:|----------:|----------:|------|
| CN_INDEX   | 13 | 14 | +0.643 | +0.564 | +27.5% | +28.4% | 54% | 64% | ✅ EV 几乎对得上 |
| CN_AGRI    | 23 | 26 | +0.814 | +0.811 | +32.8% | +26.5% | 70% | 62% | ⚠️ EV -6pp，win -8pp |
| CN_METAL   | 18 | 22 | +0.836 | +0.836 | +42.1% | +32.5% | 78% | 73% | ❌ EV -10pp（最强池失语） |
| US_EQUITY  | 27 | 20 | +0.889 | +0.750 | +31.3% | +25.7% | 74% | 60% | ⚠️ EV -6pp，win -14pp |
| US_MACRO   | 13 | 10 | +1.125 | +0.772 | +25.8% | +35.7% | 77% | 80% | ⚠️ EV +10pp 反向偏离 |
| **POOLED** | **94** | **92** | — | +0.762 | **+32.5%** | **+29.0%** | 71% | 66% | ✅ 在 ±5pp 内 |

**报告 5 个池全部为正** → 重跑：5 个池仍全部为正（区间 +25.7% .. +35.7%）。✅
**报告 CN_METAL 最强 (+42.1%)** → 重跑 CN_METAL 跌至 +32.5%，最强池变成 US_MACRO (+35.7%)。❌
**报告 "US_MACRO n_fs=0"** → 重跑 US_MACRO 仍有 1 个 full_stop（10 笔），但比例最低。⚠️

## §二 OTM 档位扫描

报告中的 OTM 2/3/4 EV%（+32.5% / +35.6% / +37.8% / +39.9%）来自 Black 模型对 OTM call 在不同 strike 偏移下的 t=17d 定价，依赖 HV20。重跑脚本无法复现该层定价（脚本不存在、HV20 计算路径不全），故 **OTM 扫描部分标记为 unreproducible**。

唯一可验证的是：tp1_tp2 比例与 win 率不应随 OTM 档位改变（报告也明确指出这一点）。我们的 outcome mix 在所有 OTM 档位下是同一组，因此报告的"tp1_tp2 在 66% 跨档位保持不变"假设成立。

## §三 同等资本预算

依赖 §二 的 EV 与权利金估计，**unreproducible**。

## §四 分池 OTM 最优 / §五 4-tick 跨市场效果 / §六 CFFEX 专项

§四与 §五依赖 OTM 重价（同 §二）。§六的 IF/IH/IC 拆分需要 CFFEX 标的的实际 sig_level 列表，可在 `rr_b_cn_index.csv` 中按 symbol 区分：

```
CN_INDEX bottom×opp 重跑：n=14 (IF/IH/IC 合计)
```

逐品种 n 太小（报告说 IF=4, IH=7, IC=2），重跑应该接近但未单独切片。**unreproducible** in granular form。

## Pooled outcome mix

```
tp1_tp2     n=50   54.3%   (报告 63%)
tp1_max     n=11   12.0%   (报告 10%)
tp1_stop    n=13   14.1%   (报告  7%)
full_stop   n=15   16.3%   (报告 15%)
max_hold    n= 3    3.3%   (报告  5%)
```

tp1_stop 比例几乎翻倍（7%→14%），是 POOLED EV 下降 3.5pp 的主因。这与 confidence-reversal 报告复现观察到的 "中等置信度信号在新数据下变弱" 一致。

## All-levels 对照（若不过滤新 6 个 level 变体）

| 池 | n (now, ALL) | EV_4tk |
|----|-------------:|-------:|
| CN_INDEX  |  20 | +22.8% |
| CN_AGRI   | 449 | +16.4% |
| CN_METAL  | 126 | +17.0% |
| US_EQUITY | 192 |  +9.5% |
| US_MACRO  | 121 | +16.5% |
| **POOLED**| **908** | **+15.2%** |

样本数翻 ~10 倍后 EV 全线腰斩，符合 brief 中 "新 level 变体稀释" 的预期，也说明 OTM/ATM 选择的边际收益完全依赖原始 level 集合。

## 复现判定

| 项 | 报告值 | 重跑值 | 判定 |
|----|--------|--------|------|
| POOLED n | 94 | 92 | ✅ |
| POOLED EV (4tk) | +32.5% | +29.0% | ✅ within 5pp |
| 5 个池 EV 全部为正 | 是 | 是 | ✅ |
| CN_METAL 是最强池 | +42.1% | +32.5% | ❌ 失去冠军位 |
| US_MACRO n_fs=0 | n_fs=0 | n_fs=1 | ⚠️ |
| 池排序（CN_METAL > CN_AGRI > US_EQUITY > US_MACRO > CN_INDEX） | — | US_MACRO > CN_METAL > CN_INDEX > CN_AGRI > US_EQUITY | ❌ 排序变化 |
| OTM 2/3/4 档位扫描 | EV +32.5→+39.9% | 无法重价 | ❓ unreproducible |
| 4-tick vs ATR 跨市场效果 | +30pp 节省 | 无法重价 | ❓ unreproducible |
| 4-tick / ATR 在 POOLED 的差距 | +5.1pp (+32.5−27.4) | +5.2pp (+29.0−23.8) | ✅ |

## 代码

- 脚本：`src/tools/repro_options_crossmarket.py`
- 输入：`src/data/review/rr_b_*.csv`（5 个池）
- 运行：`.venv/bin/python tools/repro_options_crossmarket.py`
- 对照：`--all-levels` 切换是否过滤新增 6 个 sig_level 变体

## 注释

报告所用 Black 期货期权定价脚本未在 2026-06-07 重建时保留。本复现使用 companion `doc/legacy/options-simulation-report-2026-05-31.html` 中已公布的 per-outcome 期权回报常量作为代理。POOLED 4tk EV +29.0% 与 companion report 显示的 +36.9%（n=41，仅 CN_AGRI+CN_METAL）方向一致但稍低，主要因为 US_EQUITY/US_MACRO 的 tp1_tp2 比例较低。
