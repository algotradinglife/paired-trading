# Deep-data CN sweet-spot re-run — 2026-05-26

**Author**: agent-A (analysis subagent)
**Trigger**: Today's qveris backfill extended CN 60min/15min intraday from 1-2y to 14y. Hypothesis (per memory `project_recall_first_paradigm` 2026-05-26 update): missed-swing diagnostics flipped on deep intraday data, so sweet-spots may also flip on deep daily data. This re-run tests that hypothesis on the CN pools using `analyze_sweet_spots_pool.py` (with `--oos-split 0.6` and `--walk-forward 3` against the daily snapshots).

> **Methodology constraint** (per global memory): default trust is **`--walk-forward 3`**. Any in-sample-strong cell that fails walk-forward must be tagged `REGIME-CONDITIONAL not stable`. K=3 chunks, `min_cell_n=15`, train-only tercile edges, horizon-overlap purge.

---

## 1 · Data-depth audit — critical caveat upfront

**The daily snapshots used by `analyze_sweet_spots_pool.py` are unchanged from the 2026-05-25 baseline.** The qveris backfill only refreshed `kq_m_*_{15,60}.json` (intraday); the daily `kq_m_*_daily.json` files (which the pool finder hard-codes as input) were last fetched 2026-05-24 via TqSdk and still start at 2016-01-04. CSV byte-hashes confirm identity:

| File | New (`src/data/review/`, this run) | Old (`data/review/`, 2026-05-25) | Identical? |
|---|---|---|---|
| `sweet_spots_cnc_h5_oos_v2.csv` vs `sweet_spots_pool_cn_commodity_h5_oos.csv` | `e62a6b0d…` | `e62a6b0d…` | ✅ identical |
| `sweet_spots_cnc_h10_oos_v2.csv` vs `…_h10_oos.csv` | `dffbf5ee…` | `dffbf5ee…` | ✅ identical |
| `sweet_spots_cnc_h20_oos_v2.csv` vs `…_h20_oos.csv` | `96de3ea6…` | `96de3ea6…` | ✅ identical |
| `sweet_spots_cn_h5_oos_v2.csv` vs `sweet_spots_pool_cn_h5_oos.csv` | `c92de5e7…` | `c92de5e7…` | ✅ identical |

**Implication**: any "new finding" here cannot be due to deeper data. It can only be due to the **previous 2026-05-25 doc selectively reporting** a subset of the `report_specs` cross-tabs, omitting some that contained latent stable cells. The conclusions on `--walk-forward 3` are therefore expected to match 2026-05-25 exactly — and they do.

### Data depth (per-symbol bar count + date range, daily)

| Symbol | bars | start | end |
|---|---|---|---|
| `kq_m_cffex_if/ih/ic` | 2519 | 2016-01-04 | 2026-05-21 |
| `kq_m_cffex_im` | 927 | 2022-07-21 | 2026-05-21 |
| `kq_m_czce_{cf,ma,sr,ta}`, `kq_m_dce_{i,j,jm,m,p,y}`, `kq_m_shfe_{ag,au,cu,rb}` | 2520 | 2016-01-04 | 2026-05-24 |
| `kq_m_ine_sc` | 1978 | 2018-03-26 | 2026-05-24 |

Pool signal counts (post-detector, daily MACD divergence) at h=5:
- **CN** (4 CFFEX): 239 signals across (`if`:72, `ih`:68, `ic`:78, `im`:21)
- **CN_COMMODITY** (15): 991 signals (range 46 `ine_sc` → 84 `czce_sr`)

---

## 2 · Pre-run sanity vs 2026-05-25

Existing `score_today.py` SWEET_SPOTS registry has 3 CN rules:
- `CN-bot-standard-h5` — train 66.7% / test 88.9%
- `CN-COMMODITY-bot-wlow-vmid-h5` — train 73.5% / test 81.8%
- `CN-COMMODITY-bot-wmid-vhigh-h10` — train 78.3% / test 63.0%

All three previously documented as `regime-conditional, not walk-forward stable` per memory `project_initial_sweet_spots_2026_05_25`. Today's re-run is expected to reproduce the same OOS-split numbers (train+test cells unchanged) and the same walk-forward failure mode (fold2-only).

---

## 3 · Per-cell results (12-cell sweep)

### 3.1 CN (4 CFFEX index futures) — OOS-split 0.6

Logs: `/tmp/agent_a_cn_h{5,10,20}_oos.log`. CSV: `src/data/review/sweet_spots_cn_h{5,10,20}_oos_v2.csv`.

#### h=5 (train n=143, test n=96; train baseline 55.2%, test 63.5%)

OOS-stable cells (both train+test uplift ≥ +10pp, both n ≥ 15):

| cell | train n / hit / uplift | test n / hit / uplift | drift | notes |
|---|---|---|---|---|
| **bottom / standard** | 24 / 66.7% / +11.4pp | 18 / 88.9% / +25.3pp | +22.2pp | matches existing `CN-bot-standard-h5` exactly |
| bottom / standard / swing_high | 22 / 63.6% / +8.4pp | 17 / 88.2% / +24.7pp | +24.6pp | train uplift below threshold (+8.4pp) — NOT stable by both-side rule |

#### h=10 (train n=143, test n=96)

OOS-stable cells: **none meet both-side +10pp**. The `bottom / wick_mid` cell shows train +19.2pp / test +9.4pp (just below threshold) — flagged as `XXX COLLAPSED` by the tool.

#### h=20 (train n=140, test n=95)

OOS-stable cells: **none**. The `bottom / wick_low` (train +16.0pp / test -3.8pp) collapses hard.

### 3.2 CN_COMMODITY (15 futures) — OOS-split 0.6

Logs: `/tmp/agent_a_cnc_h{5,10,20}_oos.log`. CSV: `src/data/review/sweet_spots_cnc_h{5,10,20}_oos_v2.csv`.

#### h=5 (train n=594, test n=397; train baseline 57.6%, test 53.1%)

OOS-stable cells:

| cell | train n / hit / uplift | test n / hit / uplift | drift | notes |
|---|---|---|---|---|
| **bottom / wick_low / vol_mid** | 34 / 73.5% / +16.0pp | 22 / 81.8% / +28.7pp | +8.3pp | matches existing `CN-COMMODITY-bot-wlow-vmid-h5` exactly |

Also: `bottom / weakness / wick_low` train +9.6pp / test +14.4pp (just below train threshold). `bottom / standard / vol_low` collapses (train +20.2pp → test +8.8pp).

#### h=10 (train n=593, test n=396)

OOS-stable cells:

| cell | train n / hit / uplift | test n / hit / uplift | drift | notes |
|---|---|---|---|---|
| **bottom / wick_mid / vol_high** | 23 / 78.3% / +20.1pp | 27 / 63.0% / +12.2pp | -15.3pp | matches existing `CN-COMMODITY-bot-wmid-vhigh-h10` exactly |

Collapses: `bottom / vol_low` (train +12.6pp → test -7.9pp, drift -27.9pp), `bottom / standard / wick_mid` (train +20.1pp → test +5.5pp), `bottom / standard / vol_low` (train +36.3pp → test -17.4pp), `bottom / wick_mid / swing_high` (train +19.2pp → test -0.8pp), `bottom / wick_high / vol_low` (train +22.4pp → test -19.5pp).

#### h=20 (train n=587, test n=394; train baseline 55.7%, test 51.0%)

OOS-stable cells:

| cell | train n / hit / uplift | test n / hit / uplift | drift | notes |
|---|---|---|---|---|
| **bottom / standard / wick_mid** | 22 / 81.8% / +26.1pp | 31 / 61.3% / +10.3pp | -20.5pp | new — but high drift, marginal |
| **bottom / weakness / vol_high** | 39 / 69.2% / +13.5pp | 31 / 64.5% / +13.5pp | **-4.7pp** | **new — symmetric uplift, low drift** ★ |
| bottom / standard / wick_mid / swing_high | 22 / 81.8% / +26.1pp | 31 / 61.3% / +10.3pp | -20.5pp | duplicate of `bottom/standard/wick_mid` (4-way redundant w/ 3-way) |

The **`bottom / weakness / vol_high h=20`** cell is the most interesting new surface — train+13.5pp / test+13.5pp / drift only -4.7pp. It was already present in the 2026-05-25 underlying CSV but **was never surfaced** in `doc/sweet-spots-2026-05-25.md` because that doc omitted the `Direction × subtype × volume` cross-tab section.

### 3.3 CN walk-forward K=3

Logs: `/tmp/agent_a_cn_h{5,10,20}_wf.log`. CSV: `src/data/review/sweet_spots_cn_h{5,10,20}_wf_v2.csv`.

Chunks for h=5 (chunk sizes 79/79/81):
- chunk[0]: 2016-02-29 → 2019-08-06
- chunk[1]: 2019-08-06 → 2023-07-26
- chunk[2]: 2023-07-26 → 2026-04-28

| horizon | fold1 stable cells (passes train+test +10pp) | fold2 stable cells | both folds? |
|---|---|---|---|
| h=5 | (none) | `bottom/standard` (24→17, +12.2pp/+21.6pp); `bottom/swing_high` (25→17, +13.5pp/+21.6pp); `bottom/standard/swing_high` (24→17, +12.2pp/+21.6pp) | **0 cells pass both** |
| h=10 | (none) | (none) | **0** |
| h=20 | (none) | (none) | **0** |

**Conclusion (CN walk-forward)**: 0 cells stable across both folds. Identical to 2026-05-25 walk-forward verdict. `CN-bot-standard-h5` remains **regime-conditional**, only working in the post-2023 fold.

### 3.4 CN_COMMODITY walk-forward K=3

Chunks for h=5/10/20 (sizes ~330 each):
- chunk[0]: 2016-01-21 → 2019-09-05/08
- chunk[1]: 2019-09-08 → 2023-03-22
- chunk[2]: 2023-03-22 → 2026-05-{06,13,21}

| horizon | fold1 stable cells | fold2 stable cells | both folds? |
|---|---|---|---|
| h=5 | (none) | `bottom/weakness/wick_low` (76→29, +10.5pp/+11.4pp); `bottom/wick_low/vol_mid` (39→16, +17.7pp/+33.4pp) | **0** |
| h=10 | `bottom/wick_high/vol_low` (20→15, +21.7pp/+17.6pp) | (none) | **0** |
| h=20 | (none) | `bottom/weakness/vol_high` (45→28, +12.8pp/+14.4pp) | **0** |

**Conclusion (CN_COMMODITY walk-forward)**: 0 cells pass both folds. All discovered cells (including the new `bottom/weakness/vol_high h=20` candidate) are **fold2-only or fold1-only**, i.e., **regime-conditional**.

Note: `bottom / wick_high / vol_low h=10` passes fold1 but **collapses on OOS test** (full-test n=16, hit 31.2%, -19.5pp uplift). It is a **REGIME-CONDITIONAL not stable** artifact, not a candidate.

---

## 4 · Comparison to 2026-05-25 baseline

### 4.1 What this run reproduces (no change)

- `CN-bot-standard-h5` — OOS train 66.7% test 88.9% on identical data → reproduces exactly; still walk-forward fold2-only.
- `CN-COMMODITY-bot-wlow-vmid-h5` — OOS train 73.5% test 81.8% → reproduces; walk-forward fold2-only.
- `CN-COMMODITY-bot-wmid-vhigh-h10` — OOS train 78.3% test 63.0% → reproduces; walk-forward 0/2 folds (was already regime-conditional in baseline).
- US pools — not re-run today (out of CN scope); see 2026-05-25 doc.

### 4.2 What this run newly surfaces

| cell | source of "newness" | OOS verdict | Walk-forward verdict |
|---|---|---|---|
| `bottom / weakness / vol_high h=20 (CN_COMMODITY)` | new — 2026-05-25 doc omitted the `direction × subtype × vol_bucket` table | **STABLE** (train +13.5pp, test +13.5pp, drift only -4.7pp) | fold2-only — **REGIME-CONDITIONAL not walk-forward stable** |
| `bottom / standard / wick_mid h=20 (CN_COMMODITY)` | new — same omission reason | STABLE-by-strict-rule (train +26.1pp, test +10.3pp), but drift -20.5pp = fragile | (not surfaced in either WF fold) |

### 4.3 What this run reverses (zero)

**None.** No previously OOS-stable or walk-forward-stable cell was downgraded. No previously-collapsed cell newly survived. **The 2026-05-25 walk-forward verdict — "0 cells in both test folds" — holds.**

### 4.4 Honesty check vs the user's hypothesis

The user hypothesized that deeper data on CN futures might flip the previous "no walk-forward stable" conclusion (mirroring how deep 60min intraday flipped the CN missed-swing diagnostic). **This hypothesis is not validated for the sweet-spot pool finder because** the pool finder operates on **daily** snapshots, whose depth did not change today. Bit-identical CSVs prove this.

The intraday backfill is relevant to other tools (`missed_swing_state.py` uses 60min/15min as TF inputs for multi-TF lookup), not to `analyze_sweet_spots_pool.py`. To revisit the sweet-spot question with truly deeper history, either:
1. Add a `--tf 60min` / `--tf 15min` option to `analyze_sweet_spots_pool.py` so it runs on the new deep intraday data (different signal universe, finer-grained MACD divergences), OR
2. Backfill the daily snapshots from a provider with pre-2016 history (qveris also exposes `01` daily interval — would extend CN futures back to listing date for many products).

---

## 5 · Recommended additions to `score_today.py` SWEET_SPOTS

### 5.1 Strictly walk-forward stable rules to add: **none.**

No new cell passes both walk-forward test folds. Per project methodology constraint (memory `project_initial_sweet_spots_2026_05_25` and global instruction), do not ship walk-forward-failing rules as durable production filters.

### 5.2 Single-OOS-split-stable candidate (regime-conditional, opt-in)

If the user/main session chooses to add **one** OOS-split-stable rule despite walk-forward failure (consistent with the 4 already-shipped regime-conditional rules), the strongest new candidate is:

```python
SweetSpotRule(
    rule_id="CN-COMMODITY-bot-weakness-vhigh-h20",
    description="bottom weakness-subtype divergence with high volume on CN commodity futures (20-day hold)",
    pool_class="cn_futures",
    direction="bottom",
    horizon=20,
    validated_pool="CN_COMMODITY",
    subtype_constraint="weakness",
    # CN_COMMODITY h=20 train tercile edges (computed from
    # src/data/review/sweet_spots_cnc_h20_oos_v2.csv, split=='train'):
    #   volume_ratio: lo=+0.9543  hi=+1.2645
    # vol_high predicate: value >= +1.2645
    vol_constraint=("vol_high", (0.9543, 1.2645)),
    train_hit_pct=69.2,   # n=39, +13.5pp uplift vs train baseline 55.7%
    test_hit_pct=64.5,    # n=31, +13.5pp uplift vs test baseline 51.0%
    validated_date="2026-05-26",
)
```

**Caveats to attach to this rule** (must appear in description or referencing memory):
- WALK-FORWARD VERDICT: passes fold2 only (post-2023). Fails fold1 (2019-2023 test). **Regime-conditional, NOT durable alpha.**
- DRIFT: train→test hit drift -4.7pp (symmetric uplift +13.5pp on both sides) — the cleanest drift profile of any new candidate.
- DURATION: h=20 = 20 trading days = ~4 weeks hold. Options-strategy implication: needs 4-6 week DTE minimum.
- Test set (2022-08-24 → 2026-04-21) covers a post-COVID CN commodity bull/bear mix; fold1 (2019-09-08 → 2023-03-22) covers the same product set in a different macro regime where this cell underperforms.

### 5.3 Rules NOT recommended (flagged regime-conditional or fragile)

| candidate | reason to skip |
|---|---|
| `bottom / standard / wick_mid h=20 (CN_COMMODITY)` | train +26.1pp / test +10.3pp BUT drift -20.5pp; fragile; not on either WF fold |
| `bottom / wick_high / vol_low h=10 (CN_COMMODITY)` | walk-forward fold1 only (n=20→15) but **OOS-test collapses to 31.2% (-19.5pp uplift)**. Pure regime artifact. **REGIME-CONDITIONAL not stable** |
| `bottom / weakness / wick_low h=5 (CN_COMMODITY)` | walk-forward fold2-only; close to baseline +9.6pp on OOS train (below threshold) |
| `bottom / wick_low / vol_mid h=5 walk-forward fold2` | already covered by existing `CN-COMMODITY-bot-wlow-vmid-h5` rule |
| `bottom / swing_high h=5 (CN)` | walk-forward fold2-only; train OOS +10.0pp barely passes; the dominant subtype overlap is already captured by `CN-bot-standard-h5` |

### 5.4 Existing CN rules — verdict refresh

Re-confirmed unchanged vs 2026-05-25 (same data, deterministic):

| rule | OOS train / test | walk-forward | recommendation |
|---|---|---|---|
| `CN-bot-standard-h5` | 66.7% / 88.9% (+25.3pp test) | fold2-only | keep, retain regime-conditional warning |
| `CN-COMMODITY-bot-wlow-vmid-h5` | 73.5% / 81.8% (+28.7pp test) | fold2-only | keep, retain warning |
| `CN-COMMODITY-bot-wmid-vhigh-h10` | 78.3% / 63.0% (+12.2pp test) | neither fold | keep with stronger warning — drift -15.3pp, only marginally above stable threshold |

---

## 6 · Buckets that look strong in-window but fail walk-forward (avoid)

These cells were tagged `STABLE SWEET SPOT` by the single-OOS-split logic but had clear walk-forward failure or regime restriction. **Do not use as production filters.**

| cell | in-window appearance | actual walk-forward |
|---|---|---|
| `bottom / standard / wick_mid h=20 (CN_COMMODITY)` | train +26.1pp / test +10.3pp | drift -20.5pp; absent from both WF folds |
| `bottom / wick_high / vol_low h=10 (CN_COMMODITY)` | WF fold1 train 80% / test 73.3% | OOS-test collapses to 31.2% — single-fold artifact |
| `bottom / wick_mid / vol_high h=10 (CN_COMMODITY)` (existing rule) | train +20.1pp / test +12.2pp | 0/2 walk-forward folds |
| `bottom / vol_low h=20 (CN)` | train +16.5pp / test +1.1pp | drift -15.4pp, collapsed |
| `bottom / standard / vol_low h=10 (CN_COMMODITY)` | train +36.3pp / test -17.4pp | drift -61.1pp — extreme regime collapse |

---

## 7 · Action items for main session

1. **No new walk-forward-stable rules to ship.** Decision: whether to ship `CN-COMMODITY-bot-weakness-vhigh-h20` (Section 5.2) as a fourth regime-conditional CN rule alongside the existing three. The cell has the cleanest drift profile (-4.7pp) but still fails walk-forward — consistent with the existing rule set's caveat profile.
2. **Update or supersede `doc/sweet-spots-2026-05-25.md`**: that doc's CN_COMMODITY h=20 section omitted `direction × subtype × volume`, hiding the `bottom/weakness/vol_high` cell. If the rule is shipped, link this doc as the disclosure.
3. **Consider extending `analyze_sweet_spots_pool.py` to read intraday** (`--tf 60min` / `--tf 15min`) — this is the only way the qveris deep intraday backfill can influence the sweet-spot pipeline. A separate plan-and-implement task. Without it, this "deep data" hypothesis cannot be tested at all on the sweet-spot axis.
4. **`score_today.py` note**: re-confirm the existing 3 CN rules' "regime-conditional" caveat in the printed output. No code change needed today; the data has not changed.

---

## 8 · Reproducibility — re-run commands

All commands assume cwd = `src/` so paths resolve correctly.

```bash
# OOS-split mode
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 5 --oos-split 0.6 -o data/review/sweet_spots_cn_h5_oos_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 10 --oos-split 0.6 -o data/review/sweet_spots_cn_h10_oos_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 20 --oos-split 0.6 -o data/review/sweet_spots_cn_h20_oos_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 5  --oos-split 0.6 -o data/review/sweet_spots_cnc_h5_oos_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 10 --oos-split 0.6 -o data/review/sweet_spots_cnc_h10_oos_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 20 --oos-split 0.6 -o data/review/sweet_spots_cnc_h20_oos_v2.csv

# Walk-forward K=3
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 5  --walk-forward 3 -o data/review/sweet_spots_cn_h5_wf_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 10 --walk-forward 3 -o data/review/sweet_spots_cn_h10_wf_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN --horizon 20 --walk-forward 3 -o data/review/sweet_spots_cn_h20_wf_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 5  --walk-forward 3 -o data/review/sweet_spots_cnc_h5_wf_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 10 --walk-forward 3 -o data/review/sweet_spots_cnc_h10_wf_v2.csv
uv run python scripts/analyze_sweet_spots_pool.py --pool CN_COMMODITY --horizon 20 --walk-forward 3 -o data/review/sweet_spots_cnc_h20_wf_v2.csv
```

Logs preserved at `/tmp/agent_a_*.log`. CSVs at `src/data/review/sweet_spots_{cn,cnc}_h{5,10,20}_{oos,wf}_v2.csv`. CSVs `_oos_v2` for CN_COMMODITY h={5,10,20} and CN h=5 are byte-identical to the 2026-05-25 `data/review/sweet_spots_pool_*_oos.csv`, confirming deterministic re-run on unchanged data.
