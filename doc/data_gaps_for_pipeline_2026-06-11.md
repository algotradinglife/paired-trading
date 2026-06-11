# 数据缺口清单 — 转 data-pipeline（quant-cli）

记录日期：2026-06-11（WSL 迁移，策略侧 seam 适配完成后盘点）。
paired-trading 是数据消费方；以下缺口由 data-pipeline 决定是否/如何补。
参照：`~/workspace/quant/docs/strategy-data-access-guide.md`（2026-06-11 版）。

## P0 — 阻塞 CN 全部生产 lane

**CN 期货主连（连续）序列完全缺失。** 旧库 CN 数据是 minishare 主连代码
（`cu0` / `IF0` 风格，provider 侧拼好）；新库只有单月合约（`SHFE.cu2509`），
策略引擎和 5.5 年回测都建立在连续序列上。策略侧已按 `EXCH.sym0` 文件名
约定写好读取（如 `daily/SHFE.cu0.parquet`），数据一到即可用。

需要的主连（按生产池，× 周期 d / 1h / 15min / w，2021 → 今）：

| 池 | 主连代码 | 备注 |
|----|----------|------|
| CN_METAL（生产）| SHFE: cu0 au0 ag0 | vflush 另需 INE: sc0（见 P1）|
| CN_BOND（生产，EV +0.958R 默认池）| CFFEX: TF0 T0 TS0 | **单月合约也没有** — 全新品种 |
| CN 大池（监控/回测）| SHFE: rb0 al0 ni0; DCE: i0 m0 j0 jm0 p0 y0; CZCE: CF0 RM0 SR0 TA0 MA0; CFFEX: IF0 IH0 IC0 IM0 | TA/MA/p 连单月合约都缺 |

**进展（2026-06-11）：策略侧已自行实现主连合成**（`src/data/continuous.py`，
OI 优先/volume 兜底 + 滚月规则，从单月合约只读派生），CN_METAL 已恢复运行。
因此 P0 降级为 P1，需求收窄为下面两项：

1. **2021-2022 年到期的合约月份缺失**（如 cu2107-cu2205）—— 合成序列
   起点被压缩：cu0 只能从 2022-07、ag0/au0 从 2023-03 开始（vs baseline
   的 5.5 年窗口）。补这些历史合约月份即可自动延长合成序列。
2. **历史合约 OI 全为 0**（旧 fetcher 未映射 open_interest；新同步的
   26xx/27xx 合约有值）。当前合成走 volume 兜底，重同步历史后自动转纯 OI。

（原备选 minishare `cu0` 直订 / TqSdk KQ.m 不再必需，pipeline 可自行取舍。）

## P1 — 阻塞单个 lane / 功能

| 缺口 | 影响 |
|------|------|
| **SPY 1h 2021-2024 稀疏洞**（每年约 1000 bar vs QQQ/IWM 的 4000；733 天 vs 1530 天，仅 2025 起完整）| SPY 的一切 60min 回测结论不可用（样本偏 2025 后）；QQQ/IWM 完整。疑似某次早期 sync 配置不同，建议按 QQQ 同配置重 sync SPY 1h 2021-2024 |
| INE sc（单月合约 + 主连都缺）| vflush lane 只剩 cu（验证时 cu/sc 双标的）|
| CN 期权数据格式变更：新库为 parquet 按行权价铺开，旧引擎读 `data/options/cn/*` JSON | `test_options_emission_faithfulness` 3 个失败；期权归因 harness 不可运行。**策略侧后续自己写 options 读取 seam**，但需确认新库 CN 期权 ag/au 日线覆盖回溯到 2024（旧验证窗口）|
| US 15min 缺（仅 d/5min/1h）| DIR `minute15_state` 投票在 US 全部降级 neutral；可由 5min 聚合，希望 pipeline 直接提供 15min 避免策略侧重采样语义风险 |
| US weekly 缺 | DIR `weekly_trend` backdrop 在 US 降级；可由 daily 聚合，同上 |

## P2 — 覆盖面收窄（接受或扩充由用户定）

- US 池从约 14-20 标的缩到 SPY/QQQ/IWM。叠加 `_PA_US_60MIN_SUPPRESS`
  （含 SPY/QQQ），**pa_us_60min 生产 lane 当前实际只有 IWM 一个标的**。
  旧池的 DIA/XL* 防御类本来就被结构性 suppress，损失小；但 NVDA/GLD/GDX/
  TLT 等个性化标的没了。
- CN agri（pa_h2_climax，本就 STALE/weight-0）：m/SR 在，p/ta/ma 缺。

## 时间戳语义备忘（pipeline 侧如改 fetcher 请同步告知）

- CN 分钟线：naive 北京时间，period-END（minishare/tushare 约定）；
  夜盘开盘有 volume=0 的集合竞价 bar（21:00 戳）— 策略侧保留。
- US 全部：naive **抓取机系统时区**（即北京时间，`fetchers/polygon.py`
  `datetime.fromtimestamp(ts_ms/1000)` 无 tz 参数），分钟/小时为
  period-START，含盘前盘后。**若抓取机时区改变，存量与增量会错位** —
  建议 pipeline 改为显式时区（这是一个潜在 footgun，非当前阻塞）。
- 策略侧适配逻辑见 `src/data/store.py` 模块 docstring。
- **US 盘前盘后 bar**：新 feed 含 4:00-20:00 ET 全时段；旧 feed（策略校准
  基础）仅常规时段且无每日首根钟点 bar。策略侧已在 seam 过滤（period_end
  ∈ [9:30+interval, 16:00] ET，经 baseline cell 逐位复现验证 —— 见
  `doc/repro/us_backtest_post_migration_2026-06-11.md`）。pipeline 无需
  改动；仅提示如果未来改 sync 时段配置请同步告知。
