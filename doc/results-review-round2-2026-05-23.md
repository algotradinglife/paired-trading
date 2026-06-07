# Results Review Packet — Round 2 (2026-05-23)

**Purpose**: validate 5 NEW candidate patterns surfaced by systematic mining,
using the same methodology as Round 1 (F1-F4 verdicts).

**Input data** (unchanged from Round 1):
  `src/data/review/signals_2026-05-23.csv` — 266 signals × 3 horizons.

**Mining output (new)**:
  `src/data/review/mined_patterns_h20.csv` — 237 buckets at h=20, with FDR-
  corrected p-values, bootstrap CI, drop-top-2 mean, winsorized mean, HHI.
  `src/data/review/mined_patterns_h20_top.md` — top-25 by composite score.

---

## What Round 1 already validated (do NOT re-verify)

| ID  | Rule | Status |
|-----|------|--------|
| F2  | bottom + lower_relation=leading + higher_relation=opposing | ✅ strong, n=15, in policy |
| F3  | candidate band × higher_relation=opposing                  | ✅ strong + monitor, n=14, in policy |
| F1  | top + lower_relation=lagging                               | ⚠ edge, soft de-weight, in policy |
| F4  | top + lower_relation=leading + higher_relation=opposing    | ❌ collapses for stocks; in policy as options-asymmetric tag |

The new candidates below either **generalize** these (broader/larger sample
versions) or **add a new dimension** (subtype).

---

## Round 2 Candidates

### F5 candidate — `subtype=standard + lower_relation=leading + lower_cycle=in_cycle`

Mined rank #10. Adds the SUBTYPE dimension to F2-like pattern.

```
n          = 31
hit @ h=20 = 83.9%
mean ret   = +3.55%
median ret = +2.89%
CI95       = [+2.12%, +4.98%]
drop_top2  = +2.80%
winsor5%   = +3.42%
HHI        = 0.13
FDR p_hit  = 0.0038
FDR p_mean = 0.0012
```

**Hypothesis**: among "leading + in_cycle" signals, the `standard` subtype
(price broke prior extreme + amplitude decayed) outperforms `weakness` and
`hidden`. Adds discriminating power beyond multi-TF context.

**Verify**:
- Direction split: how many are bottom vs top in n=31? `df[df['direction']=='top']`
  may contribute disproportionately — F4 collapses for stocks so any top in here
  is suspect for stock-equivalent strategies.
- Symbol distribution: HHI 0.13 looks healthy; confirm no single symbol
  drives > 20%.
- Cycle test against direction-only: is the 83.9% hit substantially better
  than `direction=X + subtype=standard` baseline?

---

### F6 candidate — `lower_relation=leading + lower_cycle=in_cycle + higher_relation=opposing`

Mined rank #11. The **direction-agnostic** version of F2, with stronger statistics.

```
n          = 27
hit @ h=20 = 88.9%
mean ret   = +4.43%
median ret = +3.12%
CI95       = [+2.85%, +6.12%]
drop_top2  = +3.62%
winsor5%   = +4.31%
HHI        = 0.13
FDR p_hit  = 0.0019
FDR p_mean = 0.0005
```

**Hypothesis**: when both 60min and weekly are in counter-trend and 60min
is in_cycle, a daily divergence (either direction) is a high-quality reversal
signal.

**Verify**:
- Direction split: F2 was bottom-only. If this n=27 is mostly bottoms, F6 ≈
  F2 with relaxed lower_cycle. If it includes meaningful number of tops at
  similar hit-rate, F6 supersedes F2 as a more general rule.
- Outlier robustness: drop_top2 dropped from +4.43% → +3.62% (modest); confirm
  no single trade > 25% return.

---

### F7 candidate — `direction=bottom + higher_relation=opposing + higher_cycle=in_cycle`

Mined rank #9. **Highest mean return** of all strong-candidate buckets.

```
n          = 36
hit @ h=20 = 80.6%
mean ret   = +6.72%
median ret = +6.47%
CI95       = [+4.34%, +9.21%]
drop_top2  = +5.41%
winsor5%   = +6.24%
HHI        = 0.12
FDR p_hit  = 0.0051
FDR p_mean = 0.0002
```

**Hypothesis**: bottom divergences when weekly is in a sustained
counter-trend (weekly bearish + in_cycle, not at_zero) have strongest
returns — the "deep oversold within a weekly downtrend" setup.

**Verify**:
- Period concentration: how many of these 36 are in 2022 bear market? If
  > 60%, the rule is regime-dependent.
- Compare to F2 overlap: how many of F2's 15 signals also satisfy F7?
  (F2 requires lower_relation=leading which F7 does not.)

---

### F8 candidate — `direction=bottom + subtype=weakness` (workhorse baseline)

Mined rank #23. **Largest sample**, validates that the weakness-subtype
bottom is consistently positive even without multi-TF context.

```
n          = 123
hit @ h=20 = 68.3%
mean ret   = +2.63%
median ret = +1.97%
CI95       = [+1.47%, +3.92%]
drop_top2  = +2.09%
winsor5%   = +2.29%
HHI        = 0.12
FDR p_hit  = 0.0021
FDR p_mean = 0.0012
```

**Hypothesis**: weakness subtype bottoms (price did NOT make new low + MACD
amplitude decayed) are the largest-sample workhorse signal. A "default"
positive expectation without any multi-TF filter.

**Verify**:
- This bucket has the largest n. If it holds up, it's the natural baseline
  rule the engine should always emit (weight ≈ 1.10) when no stronger F2/F3
  triggers fire.
- Variance: is the hit-rate stable across symbols, or driven by a few that
  are particularly mean-reverting?

---

### F9 candidate — `lower_relation=leading` (single-feature)

Mined rank #8. The strongest **single-feature** predictor across all 1-dim
buckets.

```
n          = 84
hit @ h=20 = 72.6%
mean ret   = +2.88%
median ret = +2.79%
CI95       = [+1.10%, +4.67%]
drop_top2  = +2.19%
winsor5%   = +2.94%
HHI        = 0.11
FDR p_hit  = 0.0019
FDR p_mean = 0.0133
```

**Critical concern**: this bucket MIXES bottom and top signals which have
opposite directional bias under F4 / F2 splits. The aggregate +2.88% may
mask very different sub-patterns.

**Verify**:
- Split by direction. Compute (hit_rate, mean) separately for
  bottom+leading (n≈47) and top+leading (n≈37).
- Compare against direction-only baselines: bottom n=179 / 69.3% / +3.17%
  vs top n=87 / 52.9% / -0.27%. Does `leading` actually add value on each
  side, or is it just re-discovering the bottom asymmetry?

---

## Methodology — same as Round 1

For each candidate, please report:
1. **HHI on symbols** (target < 0.30 for "diversified")
2. **Drop top-2 winners mean** (outlier robustness)
3. **Bootstrap 95% CI on mean return** — does it cross zero?
4. **Bonferroni-corrected p-values** — k = 237 buckets tested
5. **Year/regime breakdown** — 2022 bear market vs other periods
6. **For mixed-direction candidates (F9)**: per-direction split
7. **For sample-heavy candidates (F8, F9)**: Newey-West HAC standard errors
   if serial correlation suspected

**Verdict categories** (same as Round 1):
- ✅ **Survives** (high confidence): all checks pass, ready for policy
- ⚠️ **Survives** (edge / monitor): passes core stats but caveat needed
- ❌ **Collapses**: fails one or more critical checks

For each F5-F9 candidate, output a final recommendation:
- Add to `downstream_policies.py` with specified weight + caveats?
- Or mark as research observation only?

---

## What this packet does NOT include

- Re-verification of F1-F4 (Round 1 already done, in production policy)
- Buckets with n < 15 (under-powered)
- Buckets that are strict subsets of F2 (e.g. `bottom + leading`, n=47, 78.7%
  — strictly dominated by F2 + variations; mining captured but no new
  information)
- Top-only buckets that aren't options-eligible (F1/F4 already cover the
  top-signal landscape adequately for current data)

---

## How to Use

1. Read F5-F9 candidate descriptions above.
2. Use `src/data/review/signals_2026-05-23.csv` for slicing each candidate.
3. Cross-reference `src/data/review/mined_patterns_h20.csv` for full
   bucket-level stats already computed by `scripts/mine_patterns.py`.
4. For each F5-F9, produce a one-paragraph verdict with the verification
   results.
5. Output: a markdown like the `doc/codex-verdict-for-claude.md` from Round 1.
