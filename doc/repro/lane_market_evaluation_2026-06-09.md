# Lane × Market 详细评估 — 2026-06-09

基于 `full_stack_backtest.csv`（5.5 年 / 954 trades / 8 lanes / 4 pools）。

## 关键结论（按重要性）

1. **3 个独立池 lane（pa_cn_bond, pa_h2_climax, bpull/vflush/pa_h2 in CN_METAL）正负分明**——没有跨市场可比
2. **`context_a` 是唯一真正跨市场的 lane**：CN_METAL +0.21R vs US +0.07R = **3x 差距**
3. **PA H2 家族（pa_h2 / pa_us_dif_pos / pa_us_60min）方向一致但量级不同**：所有市场都 EV>0，但 CN 优于 US，与 macro 因素强相关
4. **2022 是 US 的灾难年**（-0.28R/n=77/-21.6R drag），CN 同年正常（+0.16R/n=92）——这是 US 落后的最大原因
5. **个股 kill list**：8 个 (lane, symbol) 组合 EV<0 + n≥5，总 drag -32R，全部可剔

---

## Matrix A — Lane × Pool EV/n/win

| Lane | CN_AGRI_POS | CN_BOND | CN_METAL | US |
|------|-------------|---------|----------|-----|
| bpull | — | — | **+0.18R/n172/w58%** | — |
| context_a | — | — | **+0.21R/n78/w60%** | **+0.07R/n211/w54%** |
| pa_cn_bond | — | +0.12R/n73/w66% | — | — |
| pa_h2 | — | — | +0.19R/n102/w56% | — |
| pa_h2_climax | -0.04R/n64/w47% ⚠ | — | — | — |
| pa_us_60min | — | — | — | **+0.09R/n146/w36%** |
| pa_us_dif_pos | — | — | — | +0.12R/n66/w58% |
| vflush | — | — | **+0.40R/n42/w55%** | — |

**只有 context_a 真跨市场**；其他 lanes 是 single-pool by design。

## Matrix B — Pool 总盈亏 × Year

| Pool | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total | Spread |
|------|------|------|------|------|------|------|-------|--------|
| CN_AGRI_POS | -0.10/n9 | +0.01/n17 | +0.32/n12 | -0.01/n11 | **-0.90/n9** ⚠ | +0.42/n6 | -0.04R/n64 | **1.33R** |
| CN_BOND | +0.15/n15 | +0.02/n22 | +0.12/n15 | +0.36/n7 | +0.11/n10 | +0.24/n4 | +0.12R/n73 | **0.35R** ✓ |
| CN_METAL | -0.04/n58 | +0.16/n92 | +0.20/n72 | +0.35/n71 | **+0.47/n74** | -0.13/n27 | +0.21R/n394 | 0.60R |
| US | +0.07/n48 | **-0.28/n77** ⚠ | +0.09/n59 | +0.15/n83 | +0.32/n100 | +0.05/n56 | +0.08R/n423 | 0.60R |

**关键观察**：
- **CN_BOND 最稳**（spread 0.35R，无负年）——这是 yield curve 信号本身平滑
- **US 2022 单年 -0.28R/n=77 = -21.6R drag**；剔除 2022 后 US EV = +0.16R 与 CN 相当
- **CN_AGRI_POS 2025 单年 -0.90R/n=9 = -8.1R drag**——已知 STALE
- 2026 年初普遍走弱（CN_METAL -0.13、CN_AGRI_POS +0.42 但 n=6）——可能是当前 regime

---

## Deep Dive 1 — context_a 跨市场不对称

### CN_METAL per symbol

| Symbol | n | EV | win |
|--------|---|-----|-----|
| kq_m_shfe_au | 23 | **+0.482R** | 87% |
| kq_m_shfe_ag | 22 | **+0.476R** | 64% |
| kq_m_shfe_cu | 23 | +0.162R | 57% |
| **kq_m_ine_sc** | **10** | **-0.886R** | **0%** ⚠ |

**sc 单一 symbol 拖 -8.86R**。剔除 sc 后 context_a CN_METAL = **+0.376R/n=68/win 70%**。

### US per symbol

| Symbol | n | EV | win | 类型 |
|--------|---|-----|-----|------|
| XLE | 14 | +0.293R | 57% | sector (energy) |
| NVDA | 21 | +0.221R | 57% | 单股 (growth) |
| XLB | 7 | +0.215R | 71% | sector (materials) |
| GDX | 21 | +0.154R | 57% | sector (gold) |
| XLK | 21 | +0.123R | 48% | sector (tech) |
| XLRE | 9 | +0.094R | 56% | sector (REIT) |
| QQQ | 17 | +0.076R | 59% | broad (growth) |
| GLD | 19 | +0.053R | 58% | commodity ETF |
| XLF | 18 | +0.023R | 61% | sector (financials) |
| IWM | 31 | +0.006R | 52% | broad (small cap) |
| **DIA** | **13** | **-0.090R** | 46% | **broad (defensive)** |
| **SPY** | **9** | **-0.199R** | 33% | **broad** |
| **XLU** | **11** | **-0.258R** | 36% | **sector (defensive utility)** |

**清晰 pattern**：context_a 在**广义/防御性**标的（DIA、SPY、XLU）上失败，在 **sector / 单股**上工作。

### context_a 改进方案

| Action | Expected impact |
|--------|----------------|
| 排除 `kq_m_ine_sc`（CN_METAL）| +8.86R 累计 → CN_METAL lane 净增 +22% |
| 排除 DIA, SPY, XLU（US）| +5.79R 累计 → US lane 净增 +37% |
| **defensive-suppression rule**：context_a 不接 broad-market ETF（DIA/SPY/QQQ）和 defensive sectors（XLU/XLP）| 系统化保护，covers IWM 边缘正 EV |

**根因假说**（context_a US defensive 失败）：context_a 是"恐慌买入"模式（B-class breakdown 后的 context bar）。defensive ETF（XLU/SPY/DIA）在恐慌后**不容易迅速反弹**——它们是恐慌的标的而非反弹标的。NVDA/XLE/XLK 这类 risk-on 标的在恐慌结束后 reflate 的概率高得多。

**sc 失败假说**：原油的 reversal pattern 不同于贵金属/铜——sc 受 OPEC + geopolitical 影响，技术形态 reliability 低。需要进一步 case-by-case 验证。

---

## Deep Dive 2 — pa_us_60min 36% win 解析

**这是 by design 的非对称信号**：

- Outcomes: 53 tp1_tp2 (+1.5R) / 25 tp1_stop (+0R) / 67 full_stop (-1R) / 1 max_hold
- 53/146 = **36% 触发 TP1+持仓**
- EV 数学：(53 × 1.5 + 25 × 0 + 67 × -1) / 146 = +0.083R ✓

| Year | n | EV | win |
|------|---|-----|-----|
| 2021 | 12 | +0.333R | 50% |
| **2022** | **43** | **-0.221R** | **26%** ⚠ |
| 2023 | 18 | +0.389R | 44% |
| 2024 | 20 | +0.150R | 40% |
| 2025 | 34 | +0.103R | 38% |
| 2026 | 19 | +0.236R | 37% |

**2022 是杀手**（-9.5R drag）。剔除 2022 后 EV = +0.20R/n=103/win 42%——好得多。

### Per symbol

| Symbol | n | EV | sumR | 类型 |
|--------|---|-----|------|------|
| **IWM** | 15 | **+0.633R** | +9.5R | small cap ⭐ |
| XLF | 11 | +0.455R | +5.0R | financials |
| XLE | 4 | +0.500R | +2.0R | energy |
| XLU | 3 | +0.500R | +1.5R | utility (n too small) |
| GDX | 16 | +0.219R | +3.5R | gold |
| GLD | 13 | +0.115R | +1.5R | gold |
| NVDA | 12 | +0.083R | +1.0R | growth 单股 |
| XLB | 8 | -0.002R | 0R | materials |
| SPY | 25 | -0.040R | -1.0R | broad |
| QQQ | 11 | -0.136R | -1.5R | growth 广义 |
| **XLK** | 14 | **-0.143R** | -2.0R | tech ⚠ |
| **DIA** | 10 | **-0.400R** | **-4.0R** | broad ⚠ |
| **XLRE** | 4 | -0.750R | -3.0R | REIT (n=4 outlier) |

### pa_us_60min 改进方案

| Action | Expected impact |
|--------|----------------|
| 排除 DIA | +4.0R |
| 排除 XLK | +2.0R |
| 排除 XLRE (n=4 警惕)、QQQ | +1.5R + +1.5R |
| **正向 promote IWM**（+0.633R/n=15）| weight bump? |

**根因假说**：pa_us_60min 是 60min bar 的 V-shape reversal——抓 2-5 天反转。IWM (small caps) volatility 高、反弹快——天然吃这种信号；DIA (industrial blue chip) 走势厚重慢——60min 反弹不够强。

**2022 失败假说**：2022 是结构性 bear（VIX > 25 持续半年+），所有 60min "反转"信号都是 dead cat bounce。需要 **VIX gating** 或 **regime filter**：只在 SPY 200dma 之上时启用 pa_us_60min。

---

## Deep Dive 3 — PA H2 家族量级差异

| Lane | n | EV | win | TP1+ tp1_tp2 | max_hold |
|------|---|-----|-----|--------------|----------|
| pa_h2 (CN_METAL daily) | 102 | +0.189R | 56% | 34 / 102 | **39 / 102 (38%)** |
| pa_us_dif_pos (US daily) | 66 | +0.123R | 58% | 15 / 66 | **38 / 66 (58%)** ⚠ |
| pa_us_60min (US 60min) | 146 | +0.086R | 36% | 53 / 146 | **1 / 146** ✓ |

**关键发现**：
- **US daily H2 的 max_hold 率是 58%**——58% 的 trade 还没到 TP1 就过 20 个 daily bar timeout，被 clip 到 max_hold_r。R 上限被砍。
- CN_METAL daily 也有 38% max_hold（仍然偏高）
- 60min 几乎没有 max_hold——bar 周期短，timeout 不是问题

### PA H2 家族改进方案

| Action | Expected impact |
|--------|----------------|
| **US daily H2 缩短 TP1**：1R → 0.75R | 减少 max_hold clip，TP1 hit 率提升；预计 EV +0.05 |
| **CN_METAL daily H2 同样测试**：TP1 1R → 0.75R | 同上，预计 EV +0.03 |
| **延长 max_hold**：20 → 30 daily bars | 让 trade 有时间到 TP1；预计 EV +0.03，但占 capital 时间更长 |

---

## Kill List —— 立即可执行的 8 个 symbol × lane 排除

| Lane | Pool | Symbol | n | EV | Sum R | 优先 |
|------|------|--------|---|-----|-------|------|
| context_a | CN_METAL | **kq_m_ine_sc** | 10 | -0.886R | **-8.86R** | P0 |
| pa_us_60min | US | **DIA** | 10 | -0.400R | -4.00R | P0 |
| pa_h2_climax | CN_AGRI_POS | **kq_m_dce_p** | 11 | -0.361R | -3.97R | (lane 已 quarantine) |
| context_a | US | **XLU** | 11 | -0.258R | -2.84R | P1 |
| context_a | US | **SPY** | 9 | -0.199R | -1.79R | P1 |
| pa_us_60min | US | **XLK** | 14 | -0.143R | -2.00R | P1 |
| pa_us_60min | US | **QQQ** | 11 | -0.136R | -1.50R | P2 |
| pa_h2_climax | CN_AGRI_POS | kq_m_czce_ma | 15 | -0.132R | -1.99R | (lane 已 quarantine) |

**P0 + P1 合计 预计 +19.5R**，约总 PnL 的 16%（基于 +124R）。

---

## 跨市场 regime 总结（核心 narrative）

| Pool | 强项 regime | 弱项 regime | 改进方向 |
|------|------------|-------------|----------|
| CN_BOND | 全 regime 稳定 | （无明显） | 维持现状；扩池增加 signal density |
| CN_METAL | trending market（2024-2025）| 2026 H1 略弱 | 排除 sc；评估 ag 边缘正 EV |
| US | bull / sector rotation（2024-2025）| 2022 bear、broad-market reversals | defensive 排除；regime filter; TP 缩短 |
| CN_AGRI_POS | 反弹 regime | 2025 collapse | 已 STALE；待重做 baseline |

### US 的根本问题

US lane 整体 +0.08R 偏低，三个原因：
1. **2022 单年 -21.6R drag**（占总 US PnL 64%）—— 缺乏 regime detection
2. **Broad-market ETF 拖累**：DIA/SPY/XLU 都负 EV，因为它们是被卖压打的、反弹软
3. **PA H2 US daily timeout 频繁**：58% max_hold 表明 TP1 远 / 持仓久 / 错失 winners

**如果能解决这 3 点，US EV 可从 +0.08R 提升到 +0.18-0.25R 附近**——和 CN_METAL 接轨。

---

## 完整改进清单（按优先级 + 工作量）

### P0（立即可做，每个 < 30 分钟）
1. 排除 `context_a` × `kq_m_ine_sc`（CN_METAL）—— 改 context_a_detector.py 增加 `_CONTEXT_A_EXCLUDED_CN_METAL`
2. 排除 `pa_us_60min` × DIA —— 改 score_today.py 60min lane wiring
3. 修复 `backtest_vflush.py` 和 `backtest_bpull.py` 的 JSON 数据加载（改用 `load_bars_quant_or_json`）—— 避免再有"漂移误报"

### P1（系统化改进，需要 1-2 小时）
4. context_a US：加 broad-market / defensive ETF 排除清单（DIA, SPY, XLU, 可能 XLP/XLV）
5. pa_us_60min：加同款 broad-market 排除（DIA, XLK, QQQ 边缘）
6. context_a CN_METAL：考虑 ag 边缘评估（EV +0.48 但 win 64%，可能是 outlier driven）

### P2（架构级，需要数据+实验，1-3 天）
7. **Regime detection layer**：VIX > 25 或 SPY < 200dma 时关闭 pa_us_60min 和 context_a US，等 regime 切换再开
8. **TP1 缩短 + max_hold 延长 实验**：pa_h2 US daily 从 (TP1=1R, max_hold=20) → (0.75R, 30) 跑一遍 backtest 对比
9. **2025 regime 在 CN_AGRI_POS 上的根因**：除了已知的 STALE 之外，看看是不是 dce_p (棕榈油) 单 symbol 主导

### 投入产出预估

| Tier | 投入 | 预期改进 |
|------|------|---------|
| P0 | < 1h | +12-15R 累计 → EV 从 +0.131R 提升到 ~+0.15R |
| P0+P1 | ~3h | +18-22R 累计 → EV ~+0.155R |
| P0+P1+P2 | 1-3 天 | +30R+ 累计 → EV ~+0.17-0.20R |

---

## 数据复现

```bash
cd src
.venv/bin/python <<'PY'
import csv
P="/Volumes/Data Drive/derived/paired-trading/src-data-review/full_stack_backtest.csv"
# All analysis runs on this CSV (954 rows, 5.5y).
PY
```

CSV schema: `pool, instrument_class, symbol, lane, date, year, entry, stop, policy_weight, outcome, realized_r, bars_held, dir_verdict, dir_confidence, is_60min`
