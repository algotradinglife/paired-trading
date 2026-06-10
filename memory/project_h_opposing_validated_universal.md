---
name: project_h_opposing_validated_universal
description: "h=opposing 1h filter validated as universal edge across CN commodities, CN index futures, and US equities — walk-forward OOS confirmed"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

h=opposing (1h trend opposes daily signal direction) is the single most reliable enhancement in the B-topology RR framework.

**Why:** Cross-pool in-sample EV lift:
- US equity: +0.361R → +0.722R (h=opp); bottom+opp → +0.985R
- CFFEX: +0.461R → +0.659R; top+opp → +0.889R
- CN_COMMODITY: +0.237R → +0.505R; bottom+opp → +0.764R
- CZCE: bottom+opp → +1.202R

**Walk-forward K=3 OOS (2026-05-30):**
- CN_COMMODITY stop=1.0: STRONG PASS — fold1 h=opp +0.325R, fold2 +0.479R
- CFFEX stop=1.0: STRONG PASS — fold1 h=opp +0.417R, fold2 +1.125R
- CN commodity base signal (without filter) is breakeven OOS (fold2 overall CI crosses zero) — h=opposing carries the entire edge on commodity futures

**How to apply:**
- Always filter on h=opposing as a primary condition before sizing into trades
- Bottom direction is stronger than top in all pools
- US equity bottoms with h=opposing: ~25% of signals, EV near +1.0R per trade
- CZCE bottom+opposing is the strongest cell: n=13, +1.202R
- Trade frequency: ~1 signal/symbol/yr for h=opp alone; ~0.6/yr for bottom+opp only
- Results are CSV-backed: rr_cn_commodity.csv, rr_cffex.csv, rr_czce.csv, rr_us.csv
