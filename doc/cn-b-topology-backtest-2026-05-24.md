# CN Futures B-Topology (D + 15min + 1h) Backtest — 2026-05-24

Backtest of the divergence detection + multi-TF context + downstream policy
stack on **19 Chinese futures 主力连续 contracts** with **B topology**
(primary=D, lower=15m, higher=1h). All three TFs sourced via TqSdk
2026-05-23/24.

- Script: `src/scripts/backtest_cn_b_topology.py`
- Long-format CSV: `src/data/review/cn_b_topology_signals_all.csv`
- Instrument class: `cn_futures` (direction_gate pass-through; CN policy applied)
- Horizons: **5 / 10 / 20** trading days
- Multi-TF coverage window: **2023-11-12 → 2026-04-21** (≈2.4y)
- Total evaluable signals: **233** (130 bottom, 103 top); 100% enriched with multi-TF context

---

## 1. Methodology

Pipeline per symbol:

1. Load daily / 60min / 15min bars from
   `data/raw/kq_m_<exch>_<product>_{daily,60,15}.json`.
2. Compute MACD (12, 26, 9, `hist_scale=1.0`) on daily bars.
3. Compute feature streams → unit metadata.
4. Run `detect_all_divergences(..., instrument_class="cn_futures")` —
   `direction_gate` becomes pass-through (1.0 multiplier on top signals).
5. Restrict signals to the **intersection window** of 60min and 15min coverage
   (the limiting factor; 15min depth is the bottleneck).
6. Enrich with 60min via `enrich_with_higher_tf(..., higher_tf_level_id="1h")`.
7. Enrich with 15min via `enrich_with_lower_tf(..., lower_tf_level_id="15m")`.
8. Apply `apply_policy(sig, "cn_futures")` for per-rule weighting.
9. Forward-return at h ∈ {5, 10, 20}, signed by direction; `hit = signed_return > 0`.

### Caveats / data quality

- **Short common window**: 15min depth restricts pooled sample to ~2.4y. n=233
  vs prior single-TF (no window restriction) n=1,372. Per-bucket samples often
  ≤ 20 — confidence intervals are wide.
- **TqSdk continuous-main splicing** (KQ.m@…): same rollover-gap artefact as
  AKShare data; not materially different from prior baseline.
- **Window covers 2024-2026 only**: this is a regime that includes the 2024
  CN equity rally + 2025 sideways + commodities bear. Direction-asymmetry
  result below is regime-conditional in a way the 21y baseline was not.
- **Multi-TF rules F2/F4/B1 are not part of CN policy** — they only fire
  under `us_equity`. Below we report informational "what-if" buckets using
  the same context tags, but the deployed CN policy keeps top divergences at
  pass-through weight (`CN1-top-passthrough`) and the only fired specific
  rule is `F8-cn-no-boost` for bottom+weakness.

---

## 2. Pooled aggregates

### 2.1 Direction baseline (h=20)

| direction | n   | hit_rate | avg_ret | median  |
|-----------|----:|---------:|--------:|--------:|
| bottom    | 130 | 60.0%    | +2.58%  | +0.99%  |
| top       | 103 | 48.5%    | **-1.06%** | -0.19% |

| direction | h=5 hit | h=5 avg | h=10 hit | h=10 avg |
|-----------|--------:|--------:|---------:|---------:|
| bottom    | 60.8%   | +0.77%  | 54.6%    | +1.72%   |
| top       | 53.4%   | +0.48%  | 55.3%    | -0.45%   |

**Key finding — direction asymmetry is restored vs prior CN single-TF**: CN
tops in this B-topology window are **negative (-1.06% @ h=20)**, opposite to
the prior 21y single-TF result (+0.65%). Bottoms also nearly **double** in EV
(+2.58% vs +1.31%). Whether this is (a) a more honest read once multi-TF
filtering surfaces the right buckets, or (b) the 2024-2026 regime favouring
bottoms in index futures specifically, cannot be disentangled with this
sample. See §6.

### 2.2 Per-rule (cn_futures policy, h=20)

| rule_id                | n   | hit_rate | avg_ret | median  |
|------------------------|----:|---------:|--------:|--------:|
| F8-cn-no-boost         | 56  | 76.8%    | +3.81%  | +1.56%  |
| CN1-top-passthrough    | 103 | 48.5%    | -1.06%  | -0.19%  |
| — (baseline)           | 74  | 47.3%    | +1.64%  | -0.15%  |

The baseline bucket is **non-weakness bottoms** (standard + hidden). F8'
(bottom + weakness) is the clear workhorse — exactly the pattern the
US-equity F8 captures.

### 2.3 Subtype × direction (h=20)

| direction | subtype  | n  | hit_rate | avg_ret | median  |
|-----------|----------|---:|---------:|--------:|--------:|
| bottom    | standard | 66 | 48.5%    | +1.68%  | -0.10%  |
| bottom    | weakness | 56 | **76.8%** | **+3.81%** | +1.56% |
| bottom    | hidden   |  8 | 37.5%    | +1.33%  | -0.84%  |
| top       | standard | 16 | 43.8%    | -2.14%  | -0.91%  |
| top       | weakness | 79 | 51.9%    | -0.58%  | +0.26%  |
| top       | hidden   |  8 | 25.0%    | **-3.64%** | -1.89% |

- The previous CN ordering (standard > weakness > hidden) **inverts on the
  bottom side**: weakness now dominates standard (3.81% vs 1.68%). This is
  the F8 pattern reasserting itself once multi-TF context is available.
- Hidden remains the weakest cell on both sides — too rare and apparently
  trades on noise here.

### 2.4 F8' (bottom + weakness) × confidence band (h=20)

| band      | n  | hit_rate | avg_ret |
|-----------|---:|---------:|--------:|
| watching  |  7 | 85.7%    | +1.65%  |
| forming   |  7 | 85.7%    | **+8.07%** |
| candidate | 13 | 76.9%    | +5.42%  |
| confirmed | 29 | 72.4%    | +2.59%  |

**Confidence band remains anti-monotone in CN** under B topology (forming /
watching beat confirmed). Same finding as the single-TF baseline — the
F8-no-boost CN rule is still justified. Sample size for the lower bands is
small (n=7 each) but the direction of the effect is consistent.

---

## 3. Multi-TF context cuts

### 3.1 Direction × higher_relation (1h, h=20)

| direction | higher_relation | n  | hit_rate | avg_ret |
|-----------|-----------------|---:|---------:|--------:|
| bottom    | neutral         | 10 | **90.0%** | **+8.71%** |
| bottom    | opposing        | 25 | 60.0%    | +4.36%  |
| bottom    | supporting      | 95 | 56.8%    | +1.46%  |
| top       | neutral         |  9 | 22.2%    | -4.65%  |
| top       | opposing        | 20 | **80.0%** | **+2.51%** |
| top       | supporting      | 74 | 43.2%    | -1.59%  |

**Spotlight buckets** (mirror US B-topology findings):

- **`top + higher_opposing`**: n=20, **80.0% hit**, **+2.51%** — direct
  analogue of the US B-topology spotlight (n=11, 65% hit, +0.45%). On CN
  futures the same logical pattern fires harder and more often (largely
  driven by index futures; see §4).
- **`bottom + higher_opposing`**: n=25, 60% hit, +4.36% — strong but
  out-performed by `bottom + higher_neutral` (n=10, 90% / +8.71%), which is
  a tiny sample.

### 3.2 Direction × lower_relation (15m, h=20)

| direction | lower_relation | n  | hit_rate | avg_ret |
|-----------|----------------|---:|---------:|--------:|
| bottom    | lagging        | 84 | 59.5%    | +1.61%  |
| bottom    | leading        | 32 | 62.5%    | +4.32%  |
| bottom    | pivoting       | 14 | 57.1%    | +4.39%  |
| top       | lagging        | 59 | 57.6%    | +0.09%  |
| top       | leading        | 32 | 37.5%    | -3.30%  |
| top       | pivoting       | 12 | 33.3%    | -0.74%  |

Lower-TF distinction is weaker than higher-TF (as in US B-topology, where
15m was found to be too reactive). `bottom + leading` and `bottom + pivoting`
deliver +4.3-4.4% but with marginal hit-rate edges (~60%).

### 3.3 Direction × lower × higher (h=20, n ≥ 6 shown)

| direction | lower    | higher     | n  | hit_rate | avg_ret |
|-----------|----------|------------|---:|---------:|--------:|
| bottom    | lagging  | supporting | 70 | 60.0%    | +1.56%  |
| bottom    | leading  | supporting | 17 | 52.9%    | +0.66%  |
| bottom    | leading  | opposing   | 12 | 66.7%    | **+6.73%** |
| bottom    | lagging  | neutral    |  7 | 85.7%    | +5.84%  |
| bottom    | lagging  | opposing   |  7 | 28.6%    | -2.04%  |
| bottom    | pivoting | opposing   |  6 | 83.3%    | +7.09%  |
| bottom    | pivoting | supporting |  8 | 37.5%    | +2.37%  |
| top       | lagging  | supporting | 48 | 54.2%    | -0.10%  |
| top       | leading  | supporting | 18 | 22.2%    | -5.44%  |
| top       | leading  | opposing   | 10 | **80.0%** | **+3.40%** |
| top       | lagging  | opposing   |  7 | 85.7%    | +1.06%  |
| top       | pivoting | supporting |  8 | 25.0%    | -1.85%  |

### 3.4 Informational "what-if" — US F-rule equivalents applied to CN

What the US F-rules would have selected on this CN sample (the CN policy does
NOT fire any of these — included for calibration insight only):

| US rule | predicate                                    | n  | hit_rate | avg_ret | median |
|---------|----------------------------------------------|---:|---------:|--------:|-------:|
| F2-equiv | bottom + lower=leading + higher=opposing    | 12 | 66.7%   | **+6.73%** | +5.82% |
| F4-equiv | top + lower=leading + higher=opposing       | 10 | 80.0%   | +3.40%  | +3.52% |
| B1-equiv | top + higher=opposing (incl. F4)            | 20 | 80.0%   | +2.51%  | +2.90% |
| B1-resid | top + higher=opposing, lower≠leading        | 10 | 80.0%   | +1.63%  | +2.79% |
| F1-equiv | top + lower=lagging                          | 59 | 57.6%   | +0.09%  | +1.30% |
| F3-equiv | candidate (0.65 ≤ conf < 0.80) + higher=opposing | 11 | 72.7% | +3.35% | +2.71% |

**All five US F-rules would have produced positive EV on CN under
B-topology**. Most-striking: F1 (US "soft de-weight" rule for top+lagging)
is +0.09% on CN, not the strongly negative bucket the US calibration
de-weights. The US calibration is over-penalising this cell on CN.

---

## 4. Per-symbol breakdown (h=20)

| symbol             | bot n | bot hit | bot avg | top n | top hit | top avg |
|--------------------|------:|--------:|--------:|------:|--------:|--------:|
| kq_m_cffex_if      |     9 | 78%     | +2.85%  |     9 | 56%     | -2.33%  |
| kq_m_cffex_ih      |    11 | 82%     | +1.85%  |     9 | 33%     | -1.48%  |
| kq_m_cffex_ic      |     6 | 67%     | +3.39%  |     9 | 67%     | +0.87%  |
| kq_m_cffex_im      |    10 | 80%     | +8.35%  |     7 | 43%     | -4.48%  |
| kq_m_shfe_rb       |    10 | 30%     | -0.36%  |     7 | 43%     | -0.36%  |
| kq_m_shfe_cu       |     3 | 100%    | +1.65%  |     3 | 33%     | -0.99%  |
| kq_m_shfe_au       |     4 | 75%     | +6.70%  |     2 | 50%     | +1.17%  |
| kq_m_shfe_ag       |     3 | 100%    | **+19.76%** | 2 | 0%   | **-15.26%** |
| kq_m_dce_m         |     8 | 50%     | +0.47%  |     6 | 33%     | -2.43%  |
| kq_m_dce_i         |    10 | 70%     | +2.45%  |     9 | 11%     | -3.92%  |
| kq_m_dce_j         |     7 | 29%     | -1.92%  |     6 | 50%     | -1.13%  |
| kq_m_dce_jm        |     9 | 33%     | -0.01%  |     8 | 62%     | +2.24%  |
| kq_m_dce_p         |     4 | 100%    | +3.27%  |     5 | 80%     | +3.72%  |
| kq_m_dce_y         |     7 | 43%     | -1.20%  |     3 | 33%     | +1.01%  |
| kq_m_czce_ta       |     5 | 20%     | -0.55%  |     4 | 75%     | +1.61%  |
| kq_m_czce_ma       |     7 | 57%     | +3.26%  |     3 | 33%     | -0.72%  |
| kq_m_czce_cf       |     5 | 60%     | +1.99%  |     4 | 100%    | +4.54%  |
| kq_m_czce_sr       |     8 | 50%     | +0.01%  |     5 | 80%     | +0.42%  |
| kq_m_ine_sc        |     4 | 75%     | +12.12% |     2 | 0%      | -12.55% |

### Group rollup

| group           | direction | n  | hit_rate | avg_ret |
|-----------------|-----------|---:|---------:|--------:|
| index (IF/IH/IC/IM) | bottom | 36 | **77.8%** | **+4.17%** |
| index           | top       | 34 | 50.0%    | -1.70%  |
| coal (j/jm)     | bottom    | 16 | 31.2%    | -0.85%  |
| coal            | top       | 14 | 57.1%    | +0.80%  |
| other commodity | bottom    | 78 | 57.7%    | +2.55%  |
| other commodity | top       | 55 | 45.5%    | -1.14%  |

- **Index futures dominance confirmed and stronger than baseline**: bottoms
  77.8% / +4.17% (vs prior 63.7% / +1.95%). Index tops have flipped *negative*
  on this window (-1.70%) vs prior +1.36% — consistent with the regime change
  (2024-2026 saw multiple sharp CN equity rallies followed by exhaustion).
- **Coal complex underperforms on bottoms only**: j/jm bottoms 31% hit /
  -0.85% (worst cell). Tops on coal are mildly positive — the persistent
  weakness of CN coal in 2024-2025 has made top divergences less reliable
  as "reversion to mean" signals. The blacklist is still warranted but the
  failure mode has shifted from "tops fade" to "bottoms fail to reverse".
- **Small-sample outliers**: `ag` (n=3 bot / +19.76%, n=2 top / -15.26%) and
  `sc` (n=4 bot / +12.12%, n=2 top / -12.55%) — these are single regime
  moves (silver squeeze, crude shock) and should not influence policy.

---

## 5. Comparison to baselines

### 5.1 vs prior CN single-TF baseline (2026-05-24, n=1,372)

| metric              | CN single-TF (n=1,372) | CN B-topology (n=233) | Δ                          |
|---------------------|------------------------|------------------------|----------------------------|
| bottom hit / avg    | 55.3% / +1.31%         | 60.0% / +2.58%         | +4.7 pp / +1.27%           |
| top hit / avg       | 55.8% / **+0.65%**     | 48.5% / **-1.06%**     | -7.3 pp / **-1.71%** (sign flip) |
| best subtype (bot)  | standard (+2.17%)      | weakness (+3.81%)      | F8 reasserts                |
| F8 conf-band order  | anti-monotone          | anti-monotone          | same — robust              |
| index futures (bot) | 63.7% / +1.95%         | 77.8% / +4.17%         | +14 pp / +2.22%            |
| coal (bot)          | 47% / 0%               | 31% / -0.85%           | worse                       |

**Top sign-flip is the single most important new finding.** Three competing
explanations:

1. **Regime**: 2024-2026 is a window where CN tops *did* fade harder (sharp
   equity rallies followed by exhaustion patterns) — the 21y baseline includes
   long stretches (2007, 2014-15, 2020) where CN tops were powerful trend
   continuations.
2. **Sample composition**: 233 signals concentrated in index futures (44%
   index futures, vs ~11% in the 21y baseline). Index futures show a clear
   top-fade pattern; the 21y mean was pulled positive by commodities.
3. **Window-conditioned higher-TF context**: with 1h context available, top
   signals where 1h still supports the trend (the "supporting" bucket, n=74)
   are reliably negative (-1.59%) — exactly the cell that the 21y single-TF
   could not distinguish.

The right interpretation is probably 60-70% (1)+(2) and 30-40% (3), but with
n=233 over 2.4y we cannot fully separate them. The CN policy's
`CN1-top-passthrough` weight = 1.0 is **already conservative** on either
reading; on this sample, it could justify a mild de-weight (e.g. 0.85-0.90).

### 5.2 vs US B-topology baseline (n=266, 10 symbols, 5y)

| bucket                             | US                  | CN                  |
|------------------------------------|---------------------|---------------------|
| bottom (overall)                   | 69% / +3.17%        | 60% / +2.58%        |
| top (overall)                      | 53% / -0.27%        | 49% / -1.06%        |
| `top + higher_opposing`            | n=11, 65% / +0.45%  | **n=20, 80% / +2.51%** |
| `bottom + higher_opposing`         | n=47, 79% / +4.79%  | n=25, 60% / +4.36%  |
| F8 (bot + weakness, all bands)     | +73% EV (R3, SL-3)  | +3.81% (h=20, no SL) |

- **Bottoms**: CN slightly weaker on hit rate, comparable on EV.
- **Tops**: CN tops more reliably negative than US — and the
  `top + higher_opposing` spotlight bucket fires **harder** on CN
  (n=20 / 80% / +2.51%) than on US (n=11 / 65% / +0.45%).
- **B1 rule is more profitable on CN than US** in this window. CN policy
  does not currently implement B1; if added it would route 20 of 103 CN top
  signals into a clear high-EV bucket.

---

## 6. Key findings

1. **Multi-TF context restores the textbook direction asymmetry on CN.**
   Tops swing from +0.65% (single-TF) to -1.06% (B-topology). The 1h higher
   context is the dominant discriminator; 15m lower context adds little.

2. **F8 pattern reasserts itself.** Bottom + weakness becomes the workhorse
   (n=56, 77% hit, +3.81%) and out-performs bottom + standard (which had
   dominated the single-TF view). Confidence band is still anti-monotone, so
   `F8-cn-no-boost` (weight 1.0, no confidence-bump) remains the right call.

3. **`top + higher_opposing` spotlight bucket is exceptionally strong on CN.**
   n=20 / 80% hit / +2.51% — the closest analogue to the US B1 rule.
   Currently routed to `CN1-top-passthrough` (weight 1.0). A CN B1 rule with
   weight 1.20-1.30 would be the highest-impact policy addition, though n=20
   over 2.4y is below the bar for production-ready calibration.

4. **`top + higher_supporting` is reliably bad on CN** (n=74 / 43% / -1.59%).
   This is the natural counterpart to B1: when 1h still supports the trend,
   top divergences are continuation-into-strength. A CN top de-weight rule
   on this bucket (weight ~0.7-0.8) would also be EV-positive but the sample
   is dominated by index futures and lower-than-expected hit (43%) suggests
   the cell isn't catastrophic — just mildly negative.

5. **Index futures dominance is amplified, not diluted.** With multi-TF
   filtering, index-future bottoms improve from 63.7% / +1.95% to
   77.8% / +4.17%. The `preferred_universe` hint in the CN policy is
   strongly validated.

6. **Coal bottom failure mode has shifted.** In the single-TF baseline coal
   was the worst overall EV cell (jm0 -0.67%). In this window, coal tops
   are mildly positive (+0.80%) but coal bottoms collapse to 31% hit /
   -0.85%. The instrument-class blacklist remains correct; the failure
   mechanism is now "bottoms fail to reverse" rather than "tops fade".

7. **US F-rules would have produced positive EV across the board on CN
   under B-topology.** F1 (top+lagging) — the US "soft de-weight" target —
   is actually +0.09% / 58% hit on CN. The US calibration is **over-
   penalising** this cell on CN; current `CN1-top-passthrough` (no
   de-weight) is defensible.

---

## 7. Recommended CN policy adjustments

**All recommendations are gated on `n ≥ 50` per cell to be production-ready.
Current sample (~2.4y, n=233) is too thin for some; flagged as MONITOR.**

| Proposal | Bucket | Current | Proposed | n | Status |
|----------|--------|---------|----------|---|--------|
| Add CN-B1 | top + higher=opposing | 1.00 (CN1) | **1.20** | 20 | monitor (n<50; refit at n≥50) |
| Add CN-F8-monotonic-fix | bottom + weakness + conf ≥ 0.80 | 1.00 (F8') | 0.85 | 29 | monitor — anti-monotone confirmed |
| Add CN-F8-bump-low-band | bottom + weakness + conf < 0.65 | 1.00 (F8') | 1.15 | 14 | monitor (n<50) |
| Add CN top-supporting fade | top + higher=supporting | 1.00 (CN1) | 0.80 | 74 | **eligible** for production rule |
| Reaffirm CN1-passthrough | top (no other rule) | 1.00 | 1.00 | — | keep (avoids US-over-penalty) |
| Reaffirm symbol blacklist | j0 / jm0 | hint | hint | — | keep (failure mode shifted but still negative-EV) |

**Single change that would have the largest measurable impact under
re-validation**: the `top + higher=supporting` fade rule (n=74, weight 0.80).
Sample is adequate, effect is consistent with US findings, and it's the
natural complement to the B1 rule the US policy uses.

The candidate **CN-B1** rule (top + higher_opposing) is the most exciting
new finding but the sample (n=20 over 2.4y) is below the bar for adoption.
Recommend: re-run this backtest when an additional 12 months of 15min data
is available, and adopt with weight ~1.20 if n≥50 confirms +2.0%+ EV.

---

## 8. Reproducibility

```bash
cd src
uv run python scripts/backtest_cn_b_topology.py
# Writes data/review/cn_b_topology_signals_all.csv (699 rows = 233 × 3 horizons)
```

Inputs (all generated by `scripts/fetch_tqsdk.py`):

- `data/raw/kq_m_<exch>_<product>_daily.json` × 19
- `data/raw/kq_m_<exch>_<product>_60.json` × 19
- `data/raw/kq_m_<exch>_<product>_15.json` × 19

Engine version: 2026-05-24 (`engine/divergence/downstream_policies.py` with
`cn_futures` instrument class). No engine code modified for this run.

### Re-fit triggers

This analysis MUST be re-run if any of:

- Multi-TF coverage window extended ≥ 12 months (lifts sample past n=50
  thresholds on the candidate CN-B1 / CN-F8 monotone-fix rules)
- `direction_gate` multipliers change
- CN policy thresholds in `downstream_policies.py` change
- New CN symbols added to the universe
- Confidence band thresholds change (currently
  `LABEL_CANDIDATE_THRESHOLD=0.65`, `LABEL_CONFIRMED_THRESHOLD=0.80`)
