# CN 主连合成验证 — vs 2026-06-09 baselines（2026-06-11）

`data/continuous.py`（OI 优先/volume 兜底、N 天确认、forward-only 滚月）
在真实 store 上合成 cu0/ag0/au0，跑 `backtest_full_stack --pool CN_METAL`
与 baseline 对账。

## 先说清楚：为什么不可能逐位复现（与 US 不同）

1. **窗口短 2-3 年**：store 缺 2021 年到期的合约月份（cu 最早 cu2206），
   头部修剪后 cu0 从 2022-07、ag0/au0 从 2023-03 起；baseline 是 5.5y。
2. **sc 整标的缺失**（INE 无数据），baseline 的 4 标的池只剩 3 个。
3. **滚月规则不同源**：旧 feed 是 minishare 的主连；本实现是自研规则。

因此验证标准是：**信号密度（条/标的年）同量级 + EV 符号/胜率特征一致 +
对 confirm_days 不敏感**，而非 cell 逐位。

## 结果（confirm_days=3 运行；默认已定为 1，见下）

| lane | 新 n（3 标的）| 新 EV | 密度 vs baseline | baseline (4 标的 5.5y) |
|------|------|------|------|------|
| bpull | 88 | +0.411R | 8.5 vs 7.8 条/标的年 ✓ | n=172 +0.179R win57.6 |
| pa_h2 | 28 | +0.481R | 2.7 vs 4.6 偏低 | n=102 +0.189R win55.9 |
| vflush (cu) | 15 | +0.779R | 3.75 vs 3.8 ✓ | n=42 +0.404R win54.8 (cu+sc) |
| context_a | 31 | +0.237R | — | baseline 无 n 锚 |

全部 lane 正向、胜率特征一致。EV 普遍高于 baseline —— 新窗口偏向
2023-2025（按年分解 2023+0.28 / 2024+0.53 / 2025+0.81，2026 −0.57），
窗口效应而非规则优势。**不更新任何 baseline verdict / policy weight**；
全量 re-baseline 等数据侧补齐合约月份后做。

## confirm_days 灵敏度（N=1/3/5，n 加权 EV）

```
N=1: bpull 90/+0.306  context_a 37/+0.309  pa_h2 40/+0.254  vflush 15/+0.650
N=3: bpull 88/+0.411  context_a 31/+0.237  pa_h2 28/+0.481  vflush 15/+0.779
N=5: bpull 86/+0.376  context_a 35/+0.235  pa_h2 32/+0.324  vflush 14/+0.549
```

全 N 全 lane 正向 — 结果对滚月参数不敏感（好性质）。**默认取 N=1**：
(a) pa_h2 密度最接近 baseline 期望（40 vs ~48）；(b) 与 provider 主连
惯例一致（单日越过、次日生效）。forward-only 防来回切换。

## live 冒烟

`score_today --pool CN_METAL --window-days 30`：bpull×2 / pa_h2×1 /
context_a×1 正常发信号，结构止损、仓位分层、ag 期权 strike 建议链路全通
（期权 price/IV 为 n/a — CN 期权数据格式缺口，见 data_gaps 文档）。

## 数据现状备注（同步入 data_gaps 文档）

- 合成起点受合约月份覆盖限制：cu0 2022-07 / ag0 2023-03 / au0 2023-03。
- 历史合约 OI 全为 0（旧 fetcher 未映射），选择度量实际走 volume 兜底；
  pipeline 重同步历史后自动转纯 OI。
- 远月文件含 close-only 占位行（OHLV=0）→ 已在合成层丢弃。
