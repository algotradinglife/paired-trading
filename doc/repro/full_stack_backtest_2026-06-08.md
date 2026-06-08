# 全栈历史回测 — 2026-06-08

第一份 paired-trading 当前架构的端到端历史 PnL：8 个 emit lane × 4
个 pool × 5.5 年。脚本 `scripts/backtest_full_stack.py`，CSV 输出
`data/review/full_stack_backtest.csv`。

## 核心发现（按重要性降序）

### 1. DIR gating 现在会摧毁 PnL

| Verdict | n | EV/trade | 累计 R |
|---------|---|----------|--------|
| `long_call` | 27 | +0.152R | +4.1R |
| `skip` | **927** | +0.130R | +120.5R |
| **总计** | **954** | **+0.131R** | **+124.5R** |

DIR 现行 8-source 阈值（0.50 × total_weight）下，**只有 2.8% 的交易能拿到 long_call**。其余 97% 的 trades 累计贡献 +120R——如果今天 gating 切上，几乎全部 PnL 消失。
这与 `dir_verdict_alignment_2026-06-08.md` 的"100% skip" 结论一致，但**这次有 PnL 数字佐证**：DIR 不只是评判保守，它否决了产线绝大部分**实际盈利的**信号。

**结论**：DIR 上 gating 之前必须做的两件事——
- 数据驱动重校 threshold（绝对 0.50 而非比例 0.50 × total_weight？bear-only veto？）
- 否则把 DIR 永久定位为 annotation，仅用于事后复盘

### 2. CN_METAL 是 PnL 主引擎

| Pool | n | EV | win% | 累计 R | 占总 R |
|------|---|----|------|--------|--------|
| CN_METAL | 394 | **+0.212R** | 57.4% | +83.5R | 67% |
| CN_BOND | 73 | +0.123R | 65.8% | +9.0R | 7% |
| US | 423 | +0.082R | 48.2% | +34.7R | 28% |
| CN_AGRI_POS | 64 | **-0.040R** | 46.9% | -2.6R | -2% |

CN_METAL 占 41% 的 trade 数，贡献 67% 的总 PnL。
CN_BOND 信号稀少但胜率最高（65.8%）——稳如老狗。
US 大量交易、EV 微正、胜率低于 50%——靠少数大 winner 拉平。
CN_AGRI_POS 实证负 EV——见 §3。

### 3. ⚠️ pa_h2_climax 与 baseline 严重不符

`pa_baseline_2026-06-08.md` 与 `pa_detector.py::policy_weight` docstring 声明 `cn_agri_pos` (m/p/ta/ma/sr + require_climax + h=opp) **K=3 STRONG PASS**：
- F1=+0.640R (n=8)
- F2=+0.516R (n=7)
- F3=+0.571R (n=7)
- Policy weight: 0.65

本次回测实测：
- n=64, EV=-0.040R, win 46.9%
- 5 个 symbol 全部低于 baseline

**严重不符**。可能原因：
1. **stop/TP 框架差异** —— baseline 用 pa_swing 的固定 ATR×1.5；本回测用 PA structural_stop（信号 bar 附近的最近 pivot low - 1%）。结构止损在 CN agri 上可能太宽
2. **sample 期差异** —— baseline K=3 验证在某个 cutoff 之前，本回测 2021-2026 全程
3. **样本量差异** —— baseline n=22 (8+7+7) vs 本回测 n=64

最快确认方式：把 stop 换成 ATR×1.5 重跑一次 CN_AGRI_POS。

### 4. Per-lane 排名

| Rank | Lane | n | EV/trade | win% | 备注 |
|------|------|---|----------|------|------|
| 1 | **vflush** | 42 | **+0.404R** | 54.8% | median +1.500R —— 极度非对称 R/R |
| 2 | pa_h2 | 102 | +0.189R | 55.9% | CN_METAL 主力 |
| 3 | bpull | 172 | +0.179R | 57.6% | CN_METAL ex-rb K=3 STRONG PASS 验证 |
| 4 | pa_cn_bond | 73 | +0.123R | 65.8% | 高胜率，稳 |
| 5 | pa_us_dif_pos | 66 | +0.123R | 57.6% | US daily PA H2 |
| 6 | context_a | 289 | +0.105R | 55.4% | 最大量 lane，稳定 |
| 7 | pa_us_60min | 146 | +0.086R | **36.3%** | 极低胜率，靠 R 倍数补 |
| 8 | **pa_h2_climax** | 64 | **-0.040R** | 46.9% | ⚠️ 见 §3 |

`vflush` median +1.500R 异常高——这条 lane 一旦 TP2 触发就吃满，但样本 42 太小，需要更长期数据。

`pa_us_60min` 胜率 36.3% 是个真信号：60min H2 设计就是抓 3-5 天的反转，但 TP1 触发率低（一半下面会被 stop）；大赢家 +1.5R 拉平了一堆 -1R。

### 5. 年度 PnL：逐年改善

| Year | n | EV | 累计 R |
|------|---|-----|---------|
| 2021 | 130 | +0.019R | +2.5R |
| 2022 | 208 | -0.030R | -6.2R ⚠ |
| 2023 | 158 | +0.162R | +25.6R |
| 2024 | 172 | +0.234R | +40.2R |
| 2025 | 193 | **+0.309R** | +59.6R |
| 2026 YTD | 93 | +0.030R | +2.8R |

2022 是唯一负年（与 hopp_stability "2024 CN commodity stress" 叙事**不同**——本回测的 2024 反而是最强年之一）。
2025 最强，2026 半年只 +2.8R——年初承压。

---

## 方法学

### 模拟框架
| 维度 | 设置 |
|------|------|
| Entry | 信号 bar close |
| Stop | 各 lane 自带 invalidation_level（结构止损、swing_low、信号 bar low）|
| TP1 | entry + 1R (50% exit) |
| TP2 | entry + 2R (剩余 50%) |
| Max hold | 20 daily bars (daily lane) / 140 60min bars (pa_us_60min) |
| 检查顺序 | 每根 bar 先检查 stop direction，再检查 TP direction |
| Slippage / commission | **未计入** |
| Position sizing | **每单 1R**（无 Kelly、无连损降仓）|

### 信号生成
- 每个 detector 一次性 `scan()` 全历史，依次模拟
- 8 个 lane 各自的 emission gates 严格复制 `score_today.py`
- DIR 调用 `assess_direction()`，pa_us_60min 走 10-source POC 路径，其他 lane 走 8-source

### 覆盖范围
| Pool | Symbols | 用例 |
|------|---------|------|
| US | 14 ETFs (SPY/QQQ/IWM/DIA/GLD/GDX/XLF/XLK/TLT/NVDA/XLB/XLE/XLRE/XLU) | tlt 在 US_LONG_BOND_SUPPRESS 中，pa_us_60min/dif_pos/context_a 不接 |
| CN_METAL | 4 (cu/au/ag/sc) | pa_h2 / bpull / vflush / context_a 全 active |
| CN_BOND | 3 (cffex_tf/t/ts) | pa_cn_bond only |
| CN_AGRI_POS | 5 (m/p/ta/ma/sr) | pa_h2_climax only |

---

## 限制与后续

1. **未计 slippage / commission** —— 真实交易 PnL 会更低，估计 1-3% per trade 折损
2. **position sizing = 1R 等权** —— 没用 `_position_size()` 的 half/light/watch 档位
3. **同一 symbol 同一天多 lane 触发** —— 算 2 笔独立 trade（实战会有 overlap）
4. **pa_h2_climax 异常** —— 下次回测优先重 stop framework，确认 baseline 是否仍 hold
5. **2022 负年 + 2025 强年** —— regime sensitivity 真实，没有数据基础认为 2026 会维持
6. **DIR threshold 校准** —— 现状是 annotation only，PnL 数据上看也应该保持，gating 切上立刻死 90%+

## 复现

```bash
cd src
DERIVED_ROOT="/Volumes/Data Drive/derived" \
  .venv/bin/python scripts/backtest_full_stack.py
# Single pool
.venv/bin/python scripts/backtest_full_stack.py --pool CN_METAL
# Custom start
.venv/bin/python scripts/backtest_full_stack.py --since 2023-01-01
```

CSV 输出在 `$DERIVED_ROOT/paired-trading/src-data-review/full_stack_backtest.csv`，954 行 × 15 列。
