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

**未验证疑点：minishare 端 `cu0` 类主连代码是否可订阅未实测**（旧库可以，
API 同源，预期可行但需 pipeline 确认）。若不可行，备选是 TqSdk
`KQ.m@SHFE.cu`（quant-cli 已有 tqsdk fetcher）或 pipeline 侧做持仓量拼接。

## P1 — 阻塞单个 lane / 功能

| 缺口 | 影响 |
|------|------|
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
