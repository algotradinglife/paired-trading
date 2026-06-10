---
name: project_ag_options_swing_findings
description: "ag PA H2 options swing simulation findings — h=supporting beats h=opp, wide stop, take2=3x"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

Black-76 daily simulation of ag PA H2 options swing (analyze_ag_options_swing.py).

**Key findings (2026-06-05):**
- h=supporting (60min DIF bullish at signal) → EV=1.337x (n=6, 67% win rate)
- h=opposing (standard PA filter) → EV=0.666x (n=12, 17% win rate) — WORSE for ag options
- Best config: htf=supporting + stop=0.10 + take2=3.0x → EV=1.685x (n=6, 83% win)

**Why h=supporting beats h=opp for options:**
- Options need 2x premium move to hit take1 → requires sustained directional momentum
- h=supporting = pullback in confirmed trend → higher probability of sustained move
- h=opp = counter-trend play → lower probability of large sustained option gain

**Stop finding:** wider stop (stop_frac=0.10 = cut at 90% loss) beats strict stop (0.30)
- Black-76 value decays slowly; small bounces can rescue the option → don't cut too early
- stop=0.10: 0.775x (all) vs stop=0.30: 0.714x (all)

**Simulation limitation — Xiao's actual strategy is different:**
- My model: entry at daily close, stop = 70% premium loss
- Xiao's 飞天期权: left-side anticipatory limit orders on OPTION K线, stop = few ticks on option
- With few-tick stop, risk per trade is trivial (~5-10% of premium)
- Entry precision via DD线 (trend line through declining option candle lows) or prior lows

**Script params:** analyze_ag_options_swing.py --htf [opposing|supporting|none] --stop 0.10 --take2 3.0

**Why:** To implement the correct model, need option K线 intraday data or underlying structure + delta mapping. Both are pending.
