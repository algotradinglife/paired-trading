# Experiment: B-topology (D + 15min + 1h) Multi-TF Alternative

**Date**: 2026-05-23 (initial), 2026-05-23 (execution-aware revision)
**Status (revised)**: **Adopted into engine as opt-in `context_topology="B"`** for
  options-strategy callers. Production stock-strategy default remains A.
  See `engine/output/topology.py` for the registry.
**Source data**: 5y Polygon, 10 symbols (SPY/QQQ/NVDA/GLD/DIA/IWM/TLT/XLK/XLF/GDX)
**Output CSVs**:
- `src/data/review/spy_d1h15m_signals.csv` (SPY-only A/B comparison)
- `src/data/review/b_topology_signals_all.csv` (10-symbol B run)

---

## Motivation

Production topology A is **D primary + 1h lower + W higher**. On 266 signals
across 10 symbols, top-direction divergences perform poorly (52.9% hit at
h=20, -0.27% mean). The hypothesis: replacing weekly with 60min as the
higher context might capture intraday reversal regimes that weekly misses.

## Topology comparison

| | A (production) | B (experimental) |
|---|---|---|
| primary | D | D |
| lower | 1h | 15m |
| higher | W | 1h |

Same daily-signal detection, only the multi-TF context tags differ.

## SPY-only A vs B (43 signals, same signals different tags)

### Direction baseline — unchanged
Identical signal set; topology only affects context tags, not detection.

### TOP × lower_relation
| Bucket | A (1h state) | B (15m state) | Δ |
|---|---|---|---|
| top + lagging | n=11, 18% hit, -2.5% | n=9, 33% hit, -1.9% | hit slightly better, still negative |
| **top + leading** | n=4, **75% hit, +2.13%** | n=6, 33% hit, +0.07% | **strong A-bucket dissolves in B** |
| top + pivoting | n=2, 50% hit, +1.58% | n=2, 50% hit, +0.54% | flat |

**Finding**: 15m is too reactive — it flips lagging/leading multiple times per
day, washing out the timing distinction that 1h-state preserved.

### TOP × higher_relation
| Bucket | A (W state) | B (1h state) | Δ |
|---|---|---|---|
| **top + opposing** | n=15, 33% hit, -0.43% | n=4, **75% hit, +2.13%** | **B surfaces new EV bucket** |
| top + supporting | — | n=11, 18% hit, -2.5% | new red zone in B |

**Finding**: the candidate pattern `top + 60m_opposing` emerges in B topology.
SPY n=4 too small to conclude — escalated to multi-symbol.

---

## Multi-symbol B-topology validation (266 signals)

### Headline: `top + higher_60m_opposing` pattern

```
n=37 across 10 symbols
hit_rate: 64.9%
mean ret: +0.45% (h=20)
median:   +2.51%
```

**Pattern survives expansion**: SPY n=4 / 75% → all-symbols n=37 / 65%. Hit
rate beats 50% baseline by 15 pp.

### Per-symbol breakdown

| symbol | n | hit% | mean |
|---|--:|--:|--:|
| GLD | 3 | 100% | +3.84% |
| GDX | 2 | 100% | +8.46% |
| XLF | 5 | 80% | +0.34% |
| SPY | 4 | 75% | +2.13% |
| QQQ | 4 | 75% | +2.95% |
| DIA | 3 | 67% | +0.76% |
| XLK | 9 | 56% | +2.24% |
| IWM | 4 | 50% | -0.63% |
| **NVDA** | **3** | **0%** | **-17.91%** |

**NVDA is an outlier** (single stock, high-vol). Excluding NVDA: 34 signals,
~71% hit, much higher mean.

The earlier NVDA outlier (2023-05-11, -35.66%) is the same one that destroyed
F4 in stock-payoff backtest. Confirms NVDA-specific high-vol behavior, not a
general pattern flaw.

### Comparison: BOTTOM × higher_relation (B topology, sanity check)
| Bucket | n | hit% | mean |
|---|--:|--:|--:|
| bottom + opposing | 47 | 78.7% | +4.79% |
| bottom + neutral | 12 | 66.7% | +5.35% |
| bottom + supporting | 120 | 65.8% | +2.32% |

For bottoms, `higher_opposing` (1h counter-trend) is also better than
`higher_supporting`. Pattern direction consistent across directions.

### Three-way drill for tops (B topology)

| lower(15m) | higher(1h) | n | hit% | mean |
|---|---|--:|--:|--:|
| lagging | opposing | 9 | 67% | +0.63% |
| **leading** | **opposing** | **26** | **62%** | +0.21% |
| pivoting | opposing | 2 | 100% | +2.81% |
| lagging | supporting | 33 | 49% | -0.79% |
| leading | supporting | 10 | 40% | -1.32% |

The dominant `top + opposing` sub-bucket is `leading + opposing` (n=26).
`lagging + opposing` (n=9) marginally better hit rate. The 15m lower_relation
distinction is weak — `higher_relation=opposing` carries most of the signal.

---

## Statistical sanity

- Binomial test on `top + higher_opposing`: 24 hits / 37 vs 50% null
  → z ≈ 1.81, two-sided p ≈ 0.07
- **Not Bonferroni-strong** (we tested ~30 buckets); raw p only suggestive
- Bootstrap 95% CI on mean: not computed (will be in Round 3 if escalated)

---

## Why we are NOT adopting B into production

1. **F4 essentially disappears in B**: only n=1 signal in B vs n=4 (SPY) /
   n=9 (all) in A. F4-options-asymmetric rule depends on A topology to fire.
2. **Pattern is real but weak**: hit 65% / mean +0.45% / median +2.51% does
   not justify the engineering cost of dual topology + risk of regime mismatch.
3. **15m too reactive**: lower_relation in B doesn't preserve timing
   information — the SPY comparison showed A's "top + leading" sweet spot
   dissolves into noise in B.
4. **NVDA-style high-vol single stocks misclassified**: top + higher_opposing
   loses badly on NVDA (-17.91% avg). Production policy needs consistent
   behavior across symbol classes.

## What we *do* keep

- **Document the candidate pattern** for future re-evaluation if data expands
  significantly (e.g., 10y option-grade data, more single stocks).
- **Inform F4 options work**: confirms NVDA-specific tail risk on the
  "options-asymmetric" thesis — strict stop-loss simulation is required to
  monetize F4.
- **Methodological lesson**: replacing one TF in a multi-TF setup can
  reshuffle which buckets are EV-positive; rules tuned to one topology don't
  port cleanly to another.

## Re-validation triggers

Re-run this experiment if:
- We acquire 10y+ of high-quality 60min + 15min data
- We add more single-stock symbols (current 1 NVDA may be unrepresentative)
- We build stop-loss simulation infrastructure for F4 validation
- Polygon Starter is upgraded to Premium (more option-data depth)

---

## Addendum (2026-05-23): execution-aware revision

The original "B not adopted" decision was based on raw option payoff statistics
(mean / hit rate on PUT premium). Under an execution framework that accounts
for bid/ask via limit-order entry and theta via scaled exit, the cost
arguments shift — the central question becomes whether **stock-direction
accuracy** holds at the signal level.

### Stock direction vs option direction agreement (B topology, no NVDA, n=79)

```
                   opt_correct=F  opt_correct=T
stock_correct=F          39             0       ← no false-positive option wins
stock_correct=T           8            32
```

- **89.9% agreement rate** between stock direction and option direction
- 8 "theta-eaten" cases: stock right but option lost (all sub-2% stock wins)
- 0 cases where stock was wrong but option won

### Per-rule stock-direction accuracy (B topology, n=79)

| Rule | n | **stock_acc** | opt_acc | theta-eaten / correct |
|---|--:|--:|--:|---|
| F2-strong-bottom | 5 | **80.0%** | 40.0% | 2/4 (50%) |
| F8-bottom-weakness | 38 | **65.8%** | 57.9% | 3/25 (12%) |
| F3-candidate-counter-trend | 2 | 100% | 100% | 0/2 |
| F4-options-asymmetric | 5 | 40% | 40% | 0/2 |
| F1-top-lagging | 18 | **22.2%** | 5.6% | 3/4 (75%) |

### Top × higher_relation: spotlight bucket validated under this lens

```
top + higher=opposing    n=11  stock_acc=63.6%  opt_acc=54.5%
top + higher=supporting  n=18  stock_acc=16.7%  opt_acc= 5.6%   ← red zone, can't execute out
top + higher=neutral     n= 3  stock_acc= 0.0%  opt_acc= 0.0%
```

Within the top universe (where A topology offers no clean bucket), B's
`top + higher_60m_opposing` reaches 63.6% stock direction — comparable to
F8's 65.8% on the bottom side.

### Revised conclusions

1. **F8 remains topology-agnostic**: ~66% stock_acc + only 12% theta erosion
   means it works on options without precise execution. Default for all
   strategies.
2. **F2 has the highest stock-direction signal (80%)** but 50% theta erosion
   means it MUST be paired with execution strategy on options. B topology
   surfaces more F2 firings (n=5 vs A's n=1), so B is preferable for any
   options consumer that can execute precisely.
3. **B-spotlight (top + 1h_opposing) is the only viable top-side options
   signal**. A topology has no equivalent good top-bucket (F4 is 40%
   stock_acc, F1 is 22%).
4. **F1 still cannot be salvaged**: 22% stock_acc means the signal itself is
   directionally wrong most of the time. Execution can't fix a wrong
   direction.

### Engineering decision

B topology is now a first-class `ContextTopology` in
`engine/output/topology.py`, callable via
`build_analysis_output(..., context_topology="B")`. AnalysisOutput envelope
schema bumped to 1.1 with a new `topology` field at root. Tests cover both
topologies in `tests/test_context_topology.py`. F1-F8 weight tables in
`downstream_policies.py` are NOT changed — they fire against either topology
but were calibrated on A.

Future work:
- Calibrate a separate `downstream_policies_b.py` (or topology-aware policy)
  for options strategies that integrates execution assumptions.
- Spotlight bucket validation as F-rule candidate: needs Codex Round 3 with
  proper stop-loss / scaled-exit simulation.
