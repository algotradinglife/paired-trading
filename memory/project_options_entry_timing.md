---
name: project-options-entry-timing
description: ag 期权入场时机 — PA/BPull 底部信号时 IV 远高于5-6周前；score_today 集成 OTM call 建议
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

**核心发现 (2026-06-03 options data analysis)**:
当 ag PA h=opposing 底部信号触发时，期权 IV 约 16-17%，远高于当前流程"信号日期前5-6周"时的 6-7%。以 2023-08-21 PA opposing 信号为例：买 ag2310c6000，信号当天 IV≈16.5%，T+2 标的涨 +3.9%，call 从 41pts 涨至 87pts（+113%）。而按旧流程在 9/19（77天后）买入，IV 已压缩至 6.4%，只剩 8pts，theta 侵蚀严重。

**期权市场滞后**: 期权成交量在 PA 信号后 2-3 天才明显放量，说明市场跟随而非预判信号。

**OTM chain 结构 (ag SHFE calls)**:
- Strike 间距：100 yuan/gram
- Rank 1（最近 OTM）：平均 +1.71%，Rank 2：+2.93%，Rank 3：+4.14%
- IV 正偏斜：每 +100pt strike 增加 0.3-1.0pp IV（高价位时斜率变平）
- ATM IV 范围：6-12%（低 IV regime：7-8%，高 IV regime：11-12%）
- 推荐持仓窗口：信号后 2-3 天入场，20-60 DTE 合约

**Contract naming**: `ag{YYMM}c{strike}`，SHFE ag 期权到期日约为每月17日（遇周六退至16日，遇周日退至15日）

**集成状态** (2026-06-03):
- `engine/options/cn_ag_selector.py` — `select_otm_calls(underlying_price, signal_date)` + `estimate_iv()` + `lookup_option_price()` + `enrich_with_iv()`
- `scripts/score_today.py` — ag 底部信号 score≥3 时自动输出 3 档 OTM call 建议 + IV（有历史数据时）
- 已修复 bug：Saturday expiry 算错（15→16），重复 strike 未去重

**IV 数据覆盖**: 历史 daily bar 文件位于 `data/options/cn/ag/`，命名 `{contract}_{YYYYMMDD}_daily.json`。2026 年新信号目前无现成 IV（需 TqSdk 实时拉取）。

**Why:** 信号触发时 IV 高是结构性优势——相同标的涨幅下，高 IV 入场的 call 绝对收益大幅优于低 IV 入场。

**How to apply**: 底部信号（BPull/PA H2/VFlush，score≥3）触发时，用 `select_otm_calls()` 输出建议合约清单；信号后 2-3 天确认标的没有继续下破后再实际买入 Rank 1-2 OTM call；对照 `estimate_iv()` 确认 IV 未大幅压缩。

**下一步**: TqSdk 实时期权价格接入（拉当日 bid/ask 计算 live IV）。

[[project_cn_options_intraday_tqsdk]]
[[project_pa_standalone_detector]]
[[project_bpull_detector]]
[[project_vflush_detector]]
