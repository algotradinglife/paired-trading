# Results Review Packet — Round 3 (2026-05-23)

**Purpose**: validate distribution-based options-payoff analysis on B-topology
signals, before landing a topology-specific policy module.

**Why this is different from R1/R2**:
- R1/R2 evaluated **stock direction** and **stock returns**.
- R3 evaluates **option premium return distribution** under dynamic exit
  strategy (TP/SL parameter sweep), because the consumer is an options-bare-K
  trader for whom the **shape** of the payoff distribution drives realized
  EV, not the fixed-hold mean.

## Input data

**Primary**: `src/data/review/option_payoffs_topology_b_no_nvda.csv`
- 79 signals × stock 30-day hold option payoff (h=20)
- B topology context (D + 15m + 1h)
- NVDA excluded (high-vol single-stock outlier)
- Each row: symbol, date, direction, subtype, rule_id, multi_tf_context,
  contract ticker, entry premium, h{5,10,20}_ret on option premium

**Secondary** (for cross-reference):
- `src/data/review/b_topology_signals_all.csv` — full 266 stock signals
- `doc/experiment-b-topology-2026-05-23.md` — methodology background

## Methodology

For each rule_id and the key sub-bucket, we compute:
1. **Hit rate** at fixed 30-day hold (% premium > 0)
2. **Winner distribution**: mean / median / p25 / p75 among premium > 0
3. **Loser distribution**: same for premium ≤ 0
4. **Simulated realized EV** under 6 exit-strategy variants:
   - TP+30 / SL-30 (tight both)
   - TP+50 / SL-30
   - TP+100 / SL-30
   - Let-run / SL-30 (no upside cap, tight stop)
   - Let-run / SL-50 (loose stop)
   - TP+50 / SL-50 (loose both)

**Critical caveat**: the simulation is non-path-dependent — it clips the
fixed-30-day terminal premium return to TP/SL bounds. Real intraday
movement may trigger stops earlier (less favorable) or scaled exits may
capture more upside (more favorable). The simulation is a structural lens,
not a path-accurate backtest.

---

## R3 Candidate Findings

### F8' — F8 in B topology with let-run / SL-30 exit

```
n=38  hit_rate(fixed 30d)=57.9%
Winners (n=22):  mean +129.0%  median +71.2%  p25 +48.7%  p75 +155.1%
Losers  (n=16):  mean  -56.6%  median -59.1%  p25 -92.8%  p75 -27.5%
Simulated EV(let-run/SL-30):  +64.2% per trade
```

Distribution buckets (F8 fixed-hold premium return):
```
<= -50%       9 (23.7%)
-50 to -30%   3 ( 7.9%)
-30 to 0%     4 (10.5%)
0 to +30%     4 (10.5%)
+30 to +60%   6 (15.8%)
+60 to +100%  5 (13.2%)
+100 to +200% 2 ( 5.3%)
> +200%       5 (13.2%)
```

**Hypothesis**: F8 has fat right tail (~32% of trades return > +60%) and
left tail truncatable by SL. Net let-run EV ≈ +64% per trade.

**Verify**:
- Symbol concentration in the > +100% winners (n=7). Single symbol?
- Time concentration: which year contributes most mega-winners?
- Sensitivity to SL parameter: SL-20 vs SL-30 vs SL-40 EV swing
- Out-of-sample stability: split by date (pre-2024 / 2024+), is EV
  similar in both halves?

---

### F2' — F2 in B topology with let-run / SL-30

```
n=5  hit_rate=40%
Winners (n=2):  mean +77.8%  (one is +111.5%)
Losers  (n=3):  mean -60.0%  (clustered -58 to -62%)
Simulated EV(let-run/SL-30):  +13.1% per trade
```

**Hypothesis**: F2's stock_acc 80% (n=5) doesn't translate directly to
option premium because some "right direction" trades have small magnitude
move that theta dominates. With let-run, the +111% winner offsets losers.

**Concerns**:
- n=5 is critically small. EV swings ±X% on individual trades.
- 2 winners are clustered date-wise (need to check). If both same week
  same regime, no independence.

**Verify**:
- Sample size / power: at n=5, what's the 95% CI on hit rate? Mean EV?
- Independence of the 2 winners (different symbols, far apart in time?)
- Don't add F2 to B policy if n < 10 — flag for "needs more data"

---

### F3' — F3 (candidate × counter-trend) in B topology

```
n=2  hit_rate=100%  (both winners +73-81%)
Simulated EV(let-run/SL-30):  +77.4% per trade
```

**Hypothesis**: F3 fires rarely but with extreme reliability. Both winners
in B-topology data are GLD 2024-10-31 and GLD 2024-11-22.

**Concerns**:
- n=2, both same symbol, both within 3 weeks of each other → these are NOT
  independent observations
- Likely captures one specific regime (GLD Q4 2024 rally)
- "100% hit" is meaningless at n=2

**Verify**:
- Recommend NOT adding F3 weight changes; mark as "monitor only" until
  n ≥ 10 across multiple symbols/regimes
- Confirm both GLD signals are part of same continuous rally (no
  independence)

---

### F4' — F4 (options-asymmetric) in B topology

```
n=5  hit_rate=40%
Winners (n=2):  mean +46.5%
Losers  (n=3):  mean -84.5%   ← very deep
Simulated EV(let-run/SL-30):  +0.6% per trade
```

**Hypothesis**: F4 was originally designed as options-asymmetric tag. In
B topology with let-run+SL-30, marginally positive (+0.6%) but losses
extremely deep (-84.5% average) so SL has limited effect.

**Concerns**:
- F4's loser depth means even SL-30 can't truly cap the loss (the actual
  path may hit SL late in the move; only the terminal return is observed)
- Marginal positive EV (+0.6%) is within noise for n=5

**Verify**:
- Recommend F4 weight ≤ 1.0 in B policy (effectively pass-through, no
  boost, with options_asymmetric hint retained)
- Or recommend F4 removed from B policy entirely; revisit if path-dependent
  simulation shows better realized loss caps

---

### Spotlight — `top + higher_relation=opposing` in B topology

```
n=11  hit_rate=54.5%
Winners (n=6):  mean +70.3%  median +83.3%
Losers  (n=5):  mean -80.9%  median -85.5%
Simulated EV(let-run/SL-30):  +24.7% per trade
```

Per-symbol breakdown (option n=11):
```
GLD  n=2  100% +77.4% mean
GDX  n=1  100% +91.6%
XLF  n=1  100% +91.9%
SPY  n=2   50% -5.1%
DIA  n=1    0% -88.1%
IWM  n=4   25% -55.6%   ← drags overall mean
```

**Hypothesis**: This is the unique-to-B top-side bucket. Highest direction
accuracy in top universe (63.6% stock acc on n=11 option subset; 70.6% on
stock-only n=34). Under let-run/SL-30 exit, +24.7% realized EV.

**Concerns**:
- IWM contributes 4/11 signals with only 25% hit. Symbol concentration
  flagged.
- 11 is small. The 6 wins are heavily weighted to GLD/GDX/XLF (precious
  metals + financials Q4 2025 / Q1 2026 reversals). Regime-specific?
- Stock-only B-topology has n=34 for this bucket (no option data filter);
  cross-check that stock_acc still holds without option-data selection bias

**Verify**:
- Reweight by symbol: equal-weighted by symbol vs trade-count-weighted
- Year breakdown: 2024 vs 2025 vs 2026 distribution
- Stock-only stock_acc: 70.6% on n=34 vs 63.6% on n=11 (option-data
  subset). Are the missing 23 signals systematically different?

---

### F1' — F1 (top + lagging) in B topology

```
n=18  hit_rate=5.6%   (only 1 winner!)
Winners (n=1):  +82.1% (SPY 2024-12-09)
Losers  (n=17):  mean -77.9%  p25 -96.7%
Best simulated EV(let-run/SL-30):  -23.8% per trade
```

**Conclusion (proposed)**: F1 in options is unworkable. Direction wrong
17/18 trades. No exit strategy can salvage. **Hard-drop in B policy
(weight=0)** vs current production A weight 0.70.

**Verify**:
- Confirm 1/18 hit rate is not data error
- Check if same SPY 2024-12-09 winner appears in other rule classes
  (would indicate the policy assignment, not the underlying signal, is
  the differentiator)

---

## Questions for Codex

For each finding, please report:

1. **Sample size verdict**: n=2/5/11 are borderline. Which findings should
   be considered "actionable" (≥ Codex threshold) vs "monitor-only"?

2. **Symbol/period concentration**: HHI by symbol per bucket. Any bucket
   dominated by 1-2 symbols or one regime period?

3. **EV stability under parameter perturbation**: vary SL ∈ {-20, -30, -40,
   -50} and TP ∈ {30, 50, 100, ∞}. Report a heatmap-style summary per
   bucket. Are findings sensitive to exact parameter choice?

4. **Out-of-sample / temporal split**: split signals at 2024-06-01 (rough
   mid-point of data). Compare pre / post EVs for F8, spotlight. Does the
   pattern hold in both halves?

5. **Path-dependent caveat**: the EV simulation assumes terminal premium
   only. Estimate how much realized EV would degrade if 30% of "winners"
   triggered SL during the path before reaching terminal value.

6. **Recommended B-policy weights**: based on the verdicts above, provide
   a final weight table for downstream_policies_b.py:
   - F8: weight = ? (current proposal: 1.3)
   - F2: weight = ? (current proposal: 1.2; flag for n<10 if applicable)
   - F3: weight = ? (current proposal: hold off until n≥10)
   - F4: weight = ? (current proposal: 1.0 or drop)
   - F1: weight = ? (current proposal: 0.0 / hard drop)
   - Spotlight (top+higher_opposing): weight = ? (current proposal: 1.3,
     new rule_id e.g. "B1-top-higher-opposing")
   - top + higher_supporting (B-topology red zone): weight = ? (current
     proposal: 0.0 / hard drop)

7. **Precedence — F4 vs B1**: F4 (`top + lower=leading + higher=opposing`)
   is a strict subset of B1 (`top + higher=opposing`). In the current draft
   policy, F4 fires first (more specific) → weight 1.0; B1 catches the
   residual top+higher_opposing (where lower != leading) → weight 1.3.
   The reported B1 stats (n=11, EV +24.7%) INCLUDE the F4 sub-bucket.
   Should we:
     a) Keep current precedence (F4 first, B1 catches residual). Need to
        recompute residual B1 EV after excluding F4 cases.
     b) Merge: drop F4, B1 catches all top+higher_opposing regardless of
        lower_relation.
     c) Reverse: B1 first (broader), F4 doesn't fire.
   Please report the residual B1 EV (after excluding F4 cases) and
   recommend the cleanest precedence.

## Output expected

A markdown like `doc/codex-verdict-round2-for-claude.md`:
- Per-finding ✅ / ⚠️ / ❌ verdict
- Weight recommendations with caveats
- Methodology flags (path-dependency, sample size, etc.)
