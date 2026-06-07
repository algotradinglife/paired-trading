# Exhaustion detector — recall-lift measurement (US daily, 2026-05-27)

**Status**: in-sample recall lift; OOS / walk-forward validation pending.

## Setup

- **Pool**: 10 US ETFs (SPY, QQQ, IWM, DIA, GLD, GDX, XLF, XLK, TLT, NVDA), 5y daily
- **Detectors compared**:
  - Baseline: MACD divergence (`detect_all_divergences`)
  - Lift: Divergence + Exhaustion (`detect_exhaustion_events`, strict 3-TF aligned, `min_bars_in_segment=20`, default 0.4 wick)
- **Ground truth**: `label_swings` ZigZag swings at 4 reversal thresholds
- **Recall window**: signal fires within 10 bars BEFORE swing head
- **Multi-TF**: topology A (D + 1h + W) attached to exhaustion candidates

## Event counts

- Divergence signals: 270
- Exhaustion events: 137 (~13.7 / symbol-year)
- Overlap is implicit (combined recall < sum of individuals).

## Recall table

| Threshold | Direction | n swings | Divergence % | Combined % | Lift (pp) | Exhaustion solo % |
|---:|:---:|---:|---:|---:|---:|---:|
| 3.0 | up | 1041 | 11.1 | 12.5 | +1.3 | 1.4 |
| 3.0 | down | 1039 | 7.0 | 16.2 | **+9.1** | 10.3 |
| 5.0 | up | 497 | 8.0 | 10.1 | +2.0 | 2.2 |
| 5.0 | down | 497 | 7.2 | 18.7 | **+11.5** | 12.9 |
| 8.0 | up | 234 | 6.0 | 8.1 | +2.1 | 2.6 |
| 8.0 | down | 234 | 7.3 | 20.9 | **+13.7** | 15.4 |
| 10.0 | up | 144 | 6.2 | 9.7 | +3.5 | 4.2 |
| 10.0 | down | 145 | 4.8 | 18.6 | **+13.8** | 15.2 |

## Read

- **TOPS / DOWN swings**: the detector catches an *additional* 9–14 pp of historical major peaks. Magnitude grows with swing threshold — bigger declines after sustained rallies are exactly the spec's design target (capitulation peaks where MACD divergence cannot fire because each new high re-anchors the comparator).
- **BOTTOMS / UP swings**: lift is modest (+1.3 to +3.5 pp). The 5-y US sample is bull-dominated; sustained down-trending segments long enough to fire T1 are rarer. Expect this gap to compress when re-run on CN futures (bear-leaning sample) or longer histories.
- **Exhaustion solo recall on down swings** ≈ 10–15%; this approaches the magnitude where it competes with divergence on its own.

## What this is NOT

- **Not precision**. Coverage report measures recall (did we see the swing in advance) — not forward returns. The 137 exhaustion events still need a forward-return pool study analogous to `analyze_sweet_spots_pool.py` to know how often they actually lead to profit.
- **Not OOS**. Same 5-y window used for both detection and labeling. A walk-forward K=3 + bootstrap CI validation per the [`r5-review`](codex-r5-verdict-2026-05-26.md) pattern is the next gate.

## Next steps

1. Forward-return pool analysis on the 137 events: hit-rate at h=5/10/20, bootstrap CI, hold-out OOS.
2. CN futures (CN + CN_COMMODITY) re-run — expect bottom lift to overtake top lift in CN's structurally bear-leaning regime.
3. Walk-forward K=3 before any policy graduation.
4. Hourly / 15m TF run with the per-TF recommended thresholds (50 / 200 bars).
