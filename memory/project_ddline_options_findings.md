---
name: ddline-options-findings
description: "DD-line W-bottom options strategy (Xiao 飞天期权) param sweep results + IS/OOS + Strategy A (Black-76) — precious metals work, industrial metals don't"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

# DD-Line Options Strategy — Cross-Commodity Findings (Updated 2026-06-05)

## Framework naming (corrected)
- **Strategy A (期货传导法)**: Futures PA H2 signal → Black-76 pricing → buy OTM call
- **Strategy B1 (一滴不剩)**: W-bottom retest on option K-line; entry at DD-line level; stop = entry − stop_ticks × tick
- **Strategy B2 (五滴不剩)**: Declining-highs trend line breakout on option K-line; stop = entry − stop_ticks × tick

## Best parameters (validated on ag + au)
- stop_ticks = 5 (TICK_SIZE: ag=1.0, au=2.0, cu=10.0)
- retest_tol = 10 ticks (B1 only)
- decline_min = 20% (initial option decline from recent high)
- bounce_min = 8% (bounce before watching for retest)
- peak_window = 5–7 bars
- take1_mult = 2.0x entry
- take2_mult = 4.0x entry
- max_hold = 30 days
- Results insensitive to stop_ticks(4/5/6) within ~0.04x EV

## Strategy A for au (Black-76 theoretical pricing)

| Stop method | n | EV_mult | IS | OOS |
|---|---|---|---|---|
| stop_ticks (5×2=10元/克) | 114 | **1.80x** | 1.74x | **2.45x** |
| delta_stop (delta<0.10) | 114 | 1.45x | 1.39x | 1.87x |
| stop_frac (30%) | 114 | 1.25x | 1.21x | 1.44x |

- stop_ticks strongly outperforms (5 stops vs 85 with stop_frac)
- h-filter can't be tested: 60min au data only covers 2026
- Script: `backtest_strategy_a_au.py`

## Strategy B IS/OOS results

| Commodity | Strategy | All EV | IS (pre-2024) | OOS (2025+) |
|---|---|---|---|---|
| ag (silver) | B1 | ~1.29x | ~1.2x | ~1.3x | (robust, consistent)
| ag (silver) | B2 | ~1.19x | ~1.2x | ~1.2x | (robust, consistent)
| au (gold) | B1 | 1.10x | **0.18x ❌** | 1.14x |
| au (gold) | B2 | 1.06x | **0.22x ❌** | 1.08x |
| cu (copper) | B1 | 0.75-0.78x | — | — | (all params negative)
| cu (copper) | B2 | 0.85-0.87x | — | — | (all params negative)
| rb (rebar) | B1/B2 | 0.82-0.87x | — | — | (all params negative)

**Critical: au B1/B2 IS validation fails completely** — strategy is 2025 gold bull market regime play, not robust edge.

## au best sub-segments (OOS)
- DTE: mid-DTE (91-180d) EV=1.61x (B1), 1.43x (B2)
- OTM%: 5-15% OTM EV=1.41x (B1), 1.31x (B2)
- Avoid: far OTM (>30%), near-expiry (≤90d) both sub-optimal

## Industrial metals (cu, rb): CLOSED LOOP REJECTION
- Best cu EV: 0.87x (B2) — all 6 param combos negative
- cu futures PA signals: only 1 in entire dataset (structural incompatibility)
- Root cause: industrial metals lack upside volatility skew + safe-haven demand

## ag specific home runs (B1/B2)
- AG2309C5600 2023-08-21: 3.5x (July 2023 rally)
- AG2409C7200 2024-07-30: 1.49x
- ag2507c8100 2025-05-27: 3.5x (May 2025 rally — biggest winner)

## Recommended application
| Commodity | Strategy | Recommended | Reason |
|---|---|---|---|
| ag | B1+B2 | Yes, robust | IS+OOS consistent |
| au | A | Yes (stop_ticks) | IS+OOS positive |
| au | B1/B2 | Regime-only | Only in bull regime |
| cu/rb | Any | No | Universally negative |

Scripts: `sweep_ddline_options.py`, `analyze_au_ddline_deep.py`, `backtest_strategy_a_au.py`

**Why:** Precious metals respond to macro fear spikes (safe-haven demand) creating sustained trend + retest patterns needed for DD-line. Industrial metals lack this.
