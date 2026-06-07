# crosspool-merge 复现 — 2026-06-07

对照 `doc/crosspool-merge-report-2026-05-31.html`。

## 结论

报告所有关键定量主张全部坍塌，只剩最弱的"5 池都有正贡献"成立。**核心叙事失效。**

## §1 池贡献

| Pool | 报告 n / EV | 重跑 n / EV |
|------|-------------|-------------|
| US_EQUITY | 27 / +0.889R | 192 / +0.041R |
| CN_AGRI | 26 / +0.814R | 449 / +0.199R |
| CN_METAL | 22 / +0.836R | 126 / +0.233R |
| US_MACRO | 13 / **+1.124R**（最高） | 121 / +0.104R |
| CN_INDEX | 14 / +0.643R | 20 / +0.332R |

Portfolio Sharpe 0.860 → **0.143**。

## §1.5 年度 EV

| Year | 报告 | 重跑 |
|------|------|------|
| 2021 | +0.736R | +0.288R |
| 2022 | +0.827R | +0.115R |
| 2023 | +1.071R | +0.311R |
| 2024 | +0.598R | +0.057R |
| 2025 | +0.904R | +0.186R |
| 2026 YTD | +0.812R | **−0.101R** |

"every year positive" → 2026 翻转。

## §2 相关性

| Pair | 报告 | 重跑 | 状态 |
|------|------|------|------|
| US_EQUITY × US_MACRO | +0.848 | +0.113 | ❌ |
| CN_AGRI × US_EQUITY | −0.768 hedge | +0.020 | ❌ hedge 消失 |
| CN_INDEX × US_EQUITY | +0.312 | +0.039 | ❌ |
| CN_METAL × CN_AGRI | +0.006 | +0.095 | ✅ 仍接近零 |

样本扩展 8.9x 把月度时序平滑了，原报告的"hedge pair"很可能是小样本噪声放大效应。

## §4 双池 Sharpe

报告 #1 CN_METAL+US_MACRO（1.111）；重跑 #1 CN_INDEX+CN_METAL（0.22 per-signal）。
"US_MACRO 进 Top 4 全位"不再成立，重跑只一席。

## 代码

`tools/repro_crosspool_merge.py`，读 `data/review/rr_b_*.csv`，filter `bottom × opposing`，K=3 chronological chunk。
