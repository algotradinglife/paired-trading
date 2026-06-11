# US 池迁移后回测 — seam 校准与 baseline 对账（2026-06-11）

WSL 迁移后首个正式回测。目的：验证新数据层（quant-cli store）经
`src/data/store.py` seam 读出的数据能否复现 2026-06-09 的 US baseline
cell，并量化不可归因于 seam 的真实漂移。

**结论：seam 校准完成后，`pa_us_60min` 生产相关 cell 与 baseline 逐位
复现（IWM n=15 EV+0.633R win60%）。无真实策略漂移证据。** 数据覆盖缺口
（SPY 4 年洞、池缩水）另见 `doc/data_gaps_for_pipeline_2026-06-11.md`。

## 对账路径

`backtest_full_stack.py --pool US --out-json` per-(lane,symbol) cell vs
`baselines/{pa_us_60min,pa_h2,context_a}_us_equity.json` 锚点 +
`doc/repro/lane_market_evaluation_2026-06-09.md` per-symbol 表。
可用标的：SPY/QQQ/IWM（13 个 baseline 标的中的 3 个）。

## 排查链（4 次受控实验）

| 实验 | pa_us_60min 关键 cell | 判定 |
|------|----------------------|------|
| 0. 原始 seam（无过滤）| IWM n=50 EV+0.077；QQQ n=28 EV+0.196（baseline 符号全翻转，n 超 155%）| 新 feed 含盘前盘后 bar，信号灌水 ~3× |
| 1. 常规时段过滤 (9:30,16:00] | QQQ n=11 EV−0.182（baseline n=11 EV−0.14 ✓）；IWM n=16 EV−0.188（baseline +0.633 ✗）| 盘后污染确认；IWM 仍翻转 |
| 2. 关闭 +1h period-end 平移 | 与实验 1 完全相同 | **+1h 平移对回测零影响**（只修 live as_of guard，安全保留）|
| 3. 剔除每日首根钟点 bar | **IWM n=15 EV+0.633 win60% — baseline 逐位复现**；QQQ n=11 EV−0.136 ≈ −0.14 ✓ | 首根 9:00-10:00 ET bar 的 OHLC 混入 9:00-9:30 盘前成交；旧 feed 无此 bar |

其他排除项：新旧 polygon 路径均 `adjusted=true`（复权一致）。

## 最终 seam 契约（已入 `store.py` + 19 个单元测试）

US 盘内 bar 仅保留**完整窗口落在常规时段内**者：
`period_end ∈ [9:30+interval, 16:00] ET`。对 60min 即 (10:00, 16:00]，
经验上与旧 quant-data feed 的 bar 集合一致。

## 最终 cell（commit 后 `--out-json` 可复跑）

```
lane            sym   n    ev_r     win%    baseline 锚
pa_us_60min     IWM   15   +0.633   60.0    n=15 +0.633R ✓ 逐位
pa_us_60min     QQQ   11   −0.136   27.3    n=11 −0.14R ✓（生产已 suppress）
pa_us_60min     SPY    8   +1.000   75.0    n=25 −0.04R ✗ — SPY 1h 2021-2024 缺 ~75%（数据洞，样本偏 2025 后牛市），不可比
context_a       IWM   29   +0.040   55.2    旧 IWM n=31 +0.006R ≈ ✓
context_a       QQQ   15   +0.164   46.7    （生产 broad-market 排除位）
pa_us_dif_pos   *     n≤7  —        —       样本过小，不判
```

## 决策含义

1. **政策层不需要推翻**：suppress 决策（SPY/QQQ/DIA/XLK/XLRE）在正确过滤
   的数据上依然成立（QQQ 复现负 EV）。
2. **IWM 是 pa_us_60min 在本机的唯一生产标的**，其 cell 健康（+0.633R）。
3. **SPY 任何结论都不可用**直到数据洞回填（pipeline 侧）。
4. baseline 体系（schema v2 per-cell 锚）正是本次能快速定位 feed 契约
   差异的原因 — 对账机制按设计工作。
5. drift-gate cron 维持暂缓，等 CN 回填后全量 re-baseline 再装。

## 局限

- 13 个 baseline 标的只有 3 个在库；池级聚合（n=146 EV+0.086）无法机械
  验证，本次按 per-symbol cell 对账。
- 对账窗口差异：旧评估窗口比新库早开始约 6 个月（2020-12 vs 2021-06）；
  IWM/QQQ n 仍逐位吻合，说明该 6 个月对这两个 cell 无样本贡献。
- `pa_h2`/us_regime_gate 未单独对账（full_stack US 路径未触发 pa_h2 emit；
  regime gate 为 DEPLOYED 无数值锚）。
