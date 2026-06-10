---
name: broad-market-defensive-h2-suppress
description: "US 广义市场/防御性 ETF（DIA, SPY, XLU 等）在 H2 反转家族 lane 上系统性负 EV，2026-06-09 P0+P1c 已全面排除"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

US 广义市场（DIA, SPY）和防御性 sector（XLU）在所有 3 个 H2 反转家族 lane 上系统性负 EV，已于 2026-06-09 全面排除：

| Lane | 排除标的 | Why |
|------|---------|-----|
| context_a × US | DIA, SPY, XLU | n=33 sum -5.79R |
| pa_us_60min | DIA, XLK, QQQ, XLRE, SPY | n=64 sum -11.5R |
| pa_us_dif_pos | DIA, SPY | n=17 sum -1.00R |
| context_a × CN_METAL | kq_m_ine_sc | n=10 sum -8.86R（不是 broad-market 而是单 symbol 异常）|

**Why（结构性原因）：** H2 是"恐慌后反弹"形态。广义市场（DIA/SPY/QQQ）和防御性 sector（XLU）反弹动能弱：
- DIA 是 Dow 30 industrial blue chip，走势厚重，反弹慢
- SPY 是被卖压打的本身，恐慌结束后不易迅速 +1R
- XLU/XLP 是防御 sector，资金在 risk-off 时进来、risk-on 时出去——H2 反弹不在它们的特征上
- 工作良好的反弹标的是 sector（XLE/XLF/XLB）、growth 单股（NVDA）、small caps（IWM）

Counterfactual on full_stack 5.5y / 954 trades：
- 排除前：EV +0.131R / win 53.2%
- 排除后：EV +0.183R / win 56.5% (+40%)
- US pool 单独：+0.082R → +0.171R (+109%)

**How to apply:**
- 任何新 US lane（特别是 PA H2 / V-reversal 家族）默认应该排除 DIA, SPY；XLU/XLP 视情况
- 不要排除 XLE/XLF/XLB/IWM/NVDA—这些 EV 正向 + win 健康
- 如果未来扩 US 池加入 XLP/XLV，**默认 suppress** 直到有 n≥10 正 EV 证据
- 排除清单在 [[project_baselines_infra]] 跟踪的 baseline JSON 里登记，docstring 用 BASELINE_REF
- 相关：[[baselines-as-auditable-artifacts]]
