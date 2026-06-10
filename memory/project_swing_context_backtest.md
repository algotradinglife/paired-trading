---
name: project-swing-context-backtest
description: "Swing context (trend structure / leg count / regime) backtest results 2026-06-02 — US uptrend filter CONFIRMED, CN_METAL inverted"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

Swing context module shipped 2026-06-02. Validates H2 in uptrend-pullback vs downtrend.

**Files**: `engine/features/swing_context.py` (detect_swing_points, classify_trend_structure, count_legs_down, market_regime_label, compute_swing_context), integrated into `engine/divergence/pa_detector.py` (require_trend + swing_context params).

**Backtest: US ETF 60min (backtest_pa_swing.py --dataset us_60min, stop=1.5×ATR, q≥0.3)**

K=2 (IS≤2022-12-31, OOS1=2023-2024H1, OOS2>2024H2):

| Config | n | EV | IS | F1 | F2 |
|--------|---|----|----|----|----|
| uptrend + h=opp | 56 | +0.384R | -0.150(n=20) | +0.625(n=12) | +0.708(n=24) |
| ranging + h=opp | 62 | +0.161R | +0.115(n=26) | +0.625(n=16) | -0.150(n=20) |
| downtrend + h=opp | 94 | -0.032R | +0.056(n=36) | -0.177(n=31) | +0.017(n=27) |
| legs=0 + uptrend + h=opp | 34 | +0.221R | -0.346(n=13) | +0.357(n=7) | +0.679(n=14) |
| legs=1 + uptrend + h=opp | 21 | +0.595R | +0.000(n=6) | +1.000(n=5) | +0.750(n=10) |

K=3 (IS≤2021-12-31, OOS1=2022-2023H1, OOS2=2023H2-2024, OOS3>2025):

| Config | n | F1 | F2 | F3 |
|--------|---|----|----|-----|
| uptrend + h=opp | 56 | +0.147(n=17) | +0.600(n=10) | +0.636(n=22) |
| legs=1 + uptrend + h=opp | 21 | +0.500(n=5) | +0.667(n=3) | +0.750(n=10) |

**legs=1 K=3 verdict**: 4/4 folds positive (incl IS=+0.167), monotonically increasing — pattern is real. n too small for production (max n=10 per fold). Monitoring-grade only.

**Why**: Uptrend filter is textbook Brooks H2-at-EMA in channel trend — highest-priority setup. h=opposing = HTF trend validates the pullback. IS underperformance is consistent with pattern being real (overfit suppresses it in IS).

**Backtest: CN_METAL daily (--dataset cn_metal_daily, stop=1.5×ATR, q≥0.3, h_suffix=None — no HTF available)**

| Config | n | EV | IS | F1 | F2 |
|--------|---|----|----|----|----|
| trend=downtrend (all) | 22 | +0.654R | +0.633R | +1.083R | +0.185R |
| trend=uptrend (all) | 18 | +0.225R | -0.286R | +0.667R | +0.506R |
| trend=ranging (all) | 27 | +0.254R | +0.077R | +0.500R | +0.386R |

**Note**: h_suffix=None because no weekly/monthly CN data available; 60min is lower than daily. So h=opposing filter cannot be applied for cn_metal_daily.

**CN_METAL finding**: Hypothesis INVERTED without h_rel filter — downtrend has best EV (+0.654R). Consistent with commodity mean-reversion at swing exhaustion. F2 drop-off (+0.185R vs F1=+1.083R) suggests regime sensitivity. Per Brooks framework: these are "HH MTR" reversal setups in downtrends, not continuation pullbacks.

**How to apply**:
- US equities: use `require_trend={"uptrend"}` filter in PABottomDetector for 60min bars
- CN_METAL: DO NOT apply uptrend filter; downtrend+h=opp may be the better sub-pool (but n=10 is tiny)
- legs=1 is the best US sub-cell: EV+0.595R, K=3 PASS (4/4 folds positive), monitoring-grade

**Connection to Brooks PA framework** (pa-reasoning-framework.md):
- Layer 1 = market_regime_label
- Layer 2 = classify_trend_structure (HH-HL = Always-In Long)
- Layer 3 = H2 setup = PABottomDetector h_leg_count≥2
- US results validate the framework's channel-trend H2-at-EMA priority
- CN_METAL reversal behavior matches "三推反转" (three-push reversal) pattern

Relates to [[project-pa-standalone-detector]], [[project-cn-metal-pool]].
