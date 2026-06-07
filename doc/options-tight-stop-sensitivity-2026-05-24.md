# Options Tight-Stop EV Sensitivity (2026-05-24)

Source data: `src/data/review/option_payoffs_topology_b_no_nvda.csv` (79 signals, NVDA excluded).
Long-format output: `src/data/review/tight_stop_ev_sensitivity.csv`.

## Methodology

For each (rule_id, horizon h, stop-loss level SL):

- Take the option-premium return at horizon h: `h{h}_ret`.
- Apply tight stop: realized return = max(h{h}_ret, SL).
  - If h{h}_ret < SL → realized = SL  (stop triggered)
  - Else            → realized = h{h}_ret
- Realized EV per trade = mean of realized returns across trades in the bucket.

SL levels tested: -3%, -5%, -10%, -20%, -30%.
Horizons: h = 5 / 10 / 20 trading days.
"Fixed hold" column = mean of raw `h{N}_ret` (no stop, terminal value only).

### Caveat (must read)

This is an **upper bound** on realized losses. The terminal value at day h is
the only information we have — we cannot tell whether intraday path hit the
stop *before* an eventual recovery. Real path-dependent stop fills would:

1. **Increase** the realized stop-out rate (some trades that recovered to a
   small final loss may have touched the stop intra-window).
2. Therefore **lower** the realized EV vs. what this report shows.

In particular, the "SL -3%" column is essentially "if we stop out the moment
premium drops 3%, what's the realized average?" — but with daily-close-only
data we only stop trades whose *day-h close* is worse than -3%. A trade
ending at +50% that touched -8% mid-path is counted as +50% here. So treat
this as a **best-case** for tight stops.

### Buckets

- Per rule_id: F1, F2, F3, F4, F8, baseline (`—`).
- Spotlight: all signals where `direction == top` AND `higher_relation == opposing`
  (regardless of rule_id) — the dual-confirmation top-reversal context.


## Realized EV per Trade — Matrix

### h = 5 trading days

| rule_id | n | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% | fixed hold |
|---|---|---|---|---|---|---|---|
| F1-top-lagging-soft | 18 | +9.3% | +8.1% | +5.2% | +0.0% | -4.1% | -13.6% |
| F2-strong-bottom | 5 | +5.2% | +4.0% | +1.0% | -3.5% | -7.5% | -12.6% |
| F3-candidate-counter-trend | 2 | +35.6% | +35.6% | +35.6% | +35.6% | +35.6% | +35.6% |
| F4-options-asymmetric | 5 | +8.3% | +7.5% | +5.5% | +2.3% | +0.3% | -5.9% |
| F8-bottom-weakness-baseline | 38 | +27.0% | +26.1% | +24.0% | +20.0% | +16.8% | +11.2% |
| — | 11 | +12.7% | +11.3% | +8.3% | +3.4% | +1.5% | +1.1% |
| SPOTLIGHT: top + higher=opposing | 11 | +10.1% | +9.2% | +7.2% | +4.5% | +3.6% | +0.8% |

### h = 10 trading days

| rule_id | n | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% | fixed hold |
|---|---|---|---|---|---|---|---|
| F1-top-lagging-soft | 18 | +8.6% | +7.1% | +3.5% | -3.6% | -9.9% | -29.7% |
| F2-strong-bottom | 5 | +38.4% | +37.2% | +34.2% | +28.2% | +22.2% | +11.4% |
| F3-candidate-counter-trend | 2 | +97.5% | +97.5% | +97.5% | +97.5% | +97.5% | +97.5% |
| F4-options-asymmetric | 5 | +27.4% | +26.6% | +25.4% | +23.4% | +21.4% | +13.0% |
| F8-bottom-weakness-baseline | 38 | +34.4% | +33.4% | +30.9% | +26.5% | +22.7% | +13.5% |
| — | 11 | +9.4% | +8.3% | +5.6% | +0.1% | -5.3% | -16.8% |
| SPOTLIGHT: top + higher=opposing | 11 | +43.1% | +42.6% | +41.6% | +39.7% | +37.9% | +33.3% |

### h = 20 trading days

| rule_id | n | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% | fixed hold |
|---|---|---|---|---|---|---|---|
| F1-top-lagging-soft | 18 | +1.7% | -0.2% | -4.9% | -14.3% | -23.8% | -69.1% |
| F2-strong-bottom | 5 | +29.3% | +28.1% | +25.1% | +19.1% | +13.1% | -4.9% |
| F3-candidate-counter-trend | 2 | +77.4% | +77.4% | +77.4% | +77.4% | +77.4% | +77.4% |
| F4-options-asymmetric | 5 | +16.8% | +15.6% | +12.6% | +6.6% | +0.6% | -32.1% |
| F8-bottom-weakness-baseline | 38 | +73.5% | +72.7% | +70.8% | +67.4% | +64.2% | +50.9% |
| — | 11 | +20.1% | +18.6% | +15.0% | +7.7% | +0.4% | -25.6% |
| SPOTLIGHT: top + higher=opposing | 11 | +37.0% | +36.1% | +33.8% | +29.3% | +24.7% | +1.6% |

## Stop-hit rate (share of trades whose terminal value < SL)

Recall: actual path-dependent stop-hit rate would be >= these numbers.

### h = 5

| rule_id | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% |
|---|---|---|---|---|---|
| F1-top-lagging-soft | 61% | 61% | 56% | 44% | 39% |
| F2-strong-bottom | 60% | 60% | 60% | 40% | 40% |
| F3-candidate-counter-trend | 0% | 0% | 0% | 0% | 0% |
| F4-options-asymmetric | 40% | 40% | 40% | 20% | 20% |
| F8-bottom-weakness-baseline | 45% | 45% | 42% | 37% | 29% |
| — | 73% | 73% | 55% | 27% | 18% |
| SPOTLIGHT: top + higher=opposing | 45% | 45% | 36% | 9% | 9% |

### h = 10

| rule_id | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% |
|---|---|---|---|---|---|
| F1-top-lagging-soft | 72% | 72% | 72% | 67% | 61% |
| F2-strong-bottom | 60% | 60% | 60% | 60% | 60% |
| F3-candidate-counter-trend | 0% | 0% | 0% | 0% | 0% |
| F4-options-asymmetric | 40% | 40% | 20% | 20% | 20% |
| F8-bottom-weakness-baseline | 50% | 50% | 50% | 39% | 34% |
| — | 55% | 55% | 55% | 55% | 55% |
| SPOTLIGHT: top + higher=opposing | 27% | 27% | 18% | 18% | 18% |

### h = 20

| rule_id | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% |
|---|---|---|---|---|---|
| F1-top-lagging-soft | 94% | 94% | 94% | 94% | 94% |
| F2-strong-bottom | 60% | 60% | 60% | 60% | 60% |
| F3-candidate-counter-trend | 0% | 0% | 0% | 0% | 0% |
| F4-options-asymmetric | 60% | 60% | 60% | 60% | 60% |
| F8-bottom-weakness-baseline | 39% | 39% | 37% | 32% | 32% |
| — | 73% | 73% | 73% | 73% | 73% |
| SPOTLIGHT: top + higher=opposing | 45% | 45% | 45% | 45% | 45% |

## Spotlight bucket — top + higher=opposing

Sample size: **n = 11** trades (rule composition: F4-options-asymmetric×5, F1-top-lagging-soft×3, F3-candidate-counter-trend×2, —×1).

Per-horizon realized EV under each stop:

| horizon | n | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% | fixed hold |
|---|---|---|---|---|---|---|---|
| h=5 | 11 | +10.1% | +9.2% | +7.2% | +4.5% | +3.6% | +0.8% |
| h=10 | 11 | +43.1% | +42.6% | +41.6% | +39.7% | +37.9% | +33.3% |
| h=20 | 11 | +37.0% | +36.1% | +33.8% | +29.3% | +24.7% | +1.6% |

Raw return distribution within spotlight:

| horizon | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| h=5 | -60.9% | -15.7% | -2.6% | +13.9% | +54.0% | +0.8% |
| h=10 | -71.7% | -2.2% | +20.5% | +70.7% | +174.5% | +33.3% |
| h=20 | -92.3% | -80.6% | +1.5% | +83.3% | +91.9% | +1.6% |

## Key Findings

### Tight stops that flip a losing rule positive

(fixed-hold EV < 0, but realized EV > 0 after applying SL)

- **F1-top-lagging-soft** @ h=5, SL=-3%: fixed -13.6% → realized +9.3% (n=18, stop hit 61%)
- **F1-top-lagging-soft** @ h=5, SL=-5%: fixed -13.6% → realized +8.1% (n=18, stop hit 61%)
- **F1-top-lagging-soft** @ h=5, SL=-10%: fixed -13.6% → realized +5.2% (n=18, stop hit 56%)
- **F1-top-lagging-soft** @ h=5, SL=-20%: fixed -13.6% → realized +0.0% (n=18, stop hit 44%)
- **F1-top-lagging-soft** @ h=10, SL=-3%: fixed -29.7% → realized +8.6% (n=18, stop hit 72%)
- **F1-top-lagging-soft** @ h=10, SL=-5%: fixed -29.7% → realized +7.1% (n=18, stop hit 72%)
- **F1-top-lagging-soft** @ h=10, SL=-10%: fixed -29.7% → realized +3.5% (n=18, stop hit 72%)
- **F1-top-lagging-soft** @ h=20, SL=-3%: fixed -69.1% → realized +1.7% (n=18, stop hit 94%)
- **F2-strong-bottom** @ h=5, SL=-3%: fixed -12.6% → realized +5.2% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=5, SL=-5%: fixed -12.6% → realized +4.0% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=5, SL=-10%: fixed -12.6% → realized +1.0% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=20, SL=-3%: fixed -4.9% → realized +29.3% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=20, SL=-5%: fixed -4.9% → realized +28.1% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=20, SL=-10%: fixed -4.9% → realized +25.1% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=20, SL=-20%: fixed -4.9% → realized +19.1% (n=5, stop hit 60%)
- **F2-strong-bottom** @ h=20, SL=-30%: fixed -4.9% → realized +13.1% (n=5, stop hit 60%)
- **F4-options-asymmetric** @ h=5, SL=-3%: fixed -5.9% → realized +8.3% (n=5, stop hit 40%)
- **F4-options-asymmetric** @ h=5, SL=-5%: fixed -5.9% → realized +7.5% (n=5, stop hit 40%)
- **F4-options-asymmetric** @ h=5, SL=-10%: fixed -5.9% → realized +5.5% (n=5, stop hit 40%)
- **F4-options-asymmetric** @ h=5, SL=-20%: fixed -5.9% → realized +2.3% (n=5, stop hit 20%)
- **F4-options-asymmetric** @ h=5, SL=-30%: fixed -5.9% → realized +0.3% (n=5, stop hit 20%)
- **F4-options-asymmetric** @ h=20, SL=-3%: fixed -32.1% → realized +16.8% (n=5, stop hit 60%)
- **F4-options-asymmetric** @ h=20, SL=-5%: fixed -32.1% → realized +15.6% (n=5, stop hit 60%)
- **F4-options-asymmetric** @ h=20, SL=-10%: fixed -32.1% → realized +12.6% (n=5, stop hit 60%)
- **F4-options-asymmetric** @ h=20, SL=-20%: fixed -32.1% → realized +6.6% (n=5, stop hit 60%)
- **F4-options-asymmetric** @ h=20, SL=-30%: fixed -32.1% → realized +0.6% (n=5, stop hit 60%)
- **—** @ h=10, SL=-3%: fixed -16.8% → realized +9.4% (n=11, stop hit 55%)
- **—** @ h=10, SL=-5%: fixed -16.8% → realized +8.3% (n=11, stop hit 55%)
- **—** @ h=10, SL=-10%: fixed -16.8% → realized +5.6% (n=11, stop hit 55%)
- **—** @ h=10, SL=-20%: fixed -16.8% → realized +0.1% (n=11, stop hit 55%)
- **—** @ h=20, SL=-3%: fixed -25.6% → realized +20.1% (n=11, stop hit 73%)
- **—** @ h=20, SL=-5%: fixed -25.6% → realized +18.6% (n=11, stop hit 73%)
- **—** @ h=20, SL=-10%: fixed -25.6% → realized +15.0% (n=11, stop hit 73%)
- **—** @ h=20, SL=-20%: fixed -25.6% → realized +7.7% (n=11, stop hit 73%)
- **—** @ h=20, SL=-30%: fixed -25.6% → realized +0.4% (n=11, stop hit 73%)

### Rules that stay negative at every SL level tested

(truly directionless under this stop model — adding a tighter stop does not rescue them)

- *None — every rule reaches positive EV at some SL level.*

### Best realized EV per rule (across all SL × h combos)

| rule_id | best EV | at horizon | at SL | n | fixed hold @ same h |
|---|---|---|---|---|---|
| F1-top-lagging-soft | +9.3% | h=5 | SL -3% | 18 | -13.6% |
| F2-strong-bottom | +38.4% | h=10 | SL -3% | 5 | +11.4% |
| F3-candidate-counter-trend | +97.5% | h=10 | SL -3% | 2 | +97.5% |
| F4-options-asymmetric | +27.4% | h=10 | SL -3% | 5 | +13.0% |
| F8-bottom-weakness-baseline | +73.5% | h=20 | SL -3% | 38 | +50.9% |
| — | +20.1% | h=20 | SL -3% | 11 | -25.6% |
| SPOTLIGHT: top + higher=opposing | +43.1% | h=10 | SL -3% | 11 | +33.3% |

### Interpretation

1. **Tight stops mechanically improve every rule's EV** in this end-of-day model, because they truncate the left tail without touching the right tail. The interesting question is *how much* improvement, and whether it crosses zero.

2. **Path-dependence warning bites hardest at SL -3% and -5%**. A 30-DTE ATM option routinely swings 5-10% intraday on noise. Real-world tightness of -3% to -5% will stop out many trades that this analysis credits with positive terminal value. Treat -10% as the most operationally honest column.

3. **The spotlight bucket (top + higher=opposing)** is where the multi-TF confirmation thesis should pay off. Compare its realized EV to F1 alone and to the `—` baseline at the same horizon to see whether the higher-TF filter adds edge net of the smaller sample.

4. **Use the CSV** (`tight_stop_ev_sensitivity.csv`) for further slicing — it's long-format and joins cleanly to other rule/topology metadata.
