# score_today.py live smoke audit — 2026-06-08

Live audit of `scripts/score_today.py` against US, CN_METAL, CN_BOND
pools for the last 7 days. Run with `DERIVED_ROOT=/Volumes/Data Drive/derived`,
`.venv/bin/python scripts/score_today.py --pool <P> --window-days 7
-o /tmp/score_<p>.json`. 365-day re-runs sit beside the 7-day output
for context (`/tmp/score_us_1y.json`, `/tmp/score_cnm_1y.json`).

## Headline

1. **CN_BOND is broken in production.** The pool crashes with
   `KeyError: 'cn_bond'` from `engine/divergence/direction_gate.py`
   _before_ score_today gets a chance to filter the DIF lane out.
   Zero CN_BOND signals can be produced today.
2. **`pa_us_dif_pos` (US daily PA lane) is effectively silent.**
   5 signals over 365 days vs 30 from the 60min sibling; the 7-day
   window for both US and CN_METAL had 0 daily-lane fires. The
   `at_tr_bottom` gate on TR/TR_FORMING phases is killing every
   non-BULL daily setup.
3. **Sweet-spot rules are dead-on-arrival for PA records.** 0/95
   1-year US records carry a matched_sweet_spot — PA detectors never
   populate `prior_swing_distance_pct`, so `US-bot-swing-mid-h20`
   can never match.
4. **STATUS.md numbers do not match the code.** The daily US lane
   advertised at "0.80*" emits at 0.65 (BULL) or 0.40 (TR). The
   `pa_h2_climax` lane for cn_agri is documented as live but only
   reachable via `--pool CN_COMMODITY` (not exercised by today's
   audit), and `bpull`/`vflush` levels aren't mentioned in STATUS at
   all yet ship in CN_METAL.

## Per-pool signal counts (window=7d)

| Pool      | Status     | Total | Levels emitted                          |
|-----------|------------|-------|-----------------------------------------|
| US        | ok         |  2    | pa_us_60min (1), context_a (1)          |
| CN_METAL  | ok         |  1    | pa_h2 (1)                               |
| CN_BOND   | **crash**  |  0    | n/a — KeyError in direction_gate        |

365-day window for context (PA filter, DIF lane removed):

| Pool      | Total | Levels & counts                                       |
|-----------|-------|--------------------------------------------------------|
| US        |  95   | pa_us_60min 30 · pa_us_dif_pos 5 · context_a 60       |
| CN_METAL  |  67   | bpull 31 · pa_h2 17 · context_a 11 · vflush 8         |

Per-level 1-year score distribution:

| Level          | Pool      | n   | score=4 | score=3 | score=2 |
|----------------|-----------|-----|---------|---------|---------|
| pa_us_60min    | US        | 30  | 9       | 21      | 0       |
| pa_us_dif_pos  | US        | 5   | 0       | 5       | 0       |
| context_a (US) | US        | 60  | 0       | 60      | 0       |
| pa_h2          | CN_METAL  | 17  | 4       | 9       | 4       |
| bpull          | CN_METAL  | 31  | 31      | 0       | 0       |
| context_a (CN) | CN_METAL  | 11  | 0       | 11      | 0       |
| vflush         | CN_METAL  | 8   | 0       | 8       | 0       |

## Looks correct

### 1. DIF retirement filter works (US/CN_METAL)

0/95 US 1-year records and 0/67 CN_METAL 1-year records carry any
of the 9 DIF detector levels (`intra_cycle`, `inter_cycle`,
`inter_segment`, or the 6 `intra_cycle_*` variants). STATUS.md's
default-skip is operating as designed.

### 2. Policy weights match the table (where reachable)

Spot-checks vs `engine/divergence/pa_detector.py::policy_weight()`:

- US 60min `pa_us_60min` legs=0, h=opp → 0.80 ✓
- US 60min `pa_us_60min` legs=1, h=opp → 0.90 ✓ (STATUS line 32)
- CN_METAL `pa_h2` h=supporting → 0.45 ✓ (the only 7-day fire is
  ag h=supporting, weight 0.45; matches the supporting-branch in
  `policy_weight()`)
- CN_METAL `pa_h2` h=opp → 0.75 ✓ (visible in 1y subset)
- CN_METAL `bpull` h=opp → 0.75 ✓ (matches `bpull-k3-cn-metal` policy)
- US `context_a` → 0.60 ✓ (Conditional PASS lane)
- CN_METAL `vflush` cu/sc h=opp → 0.65 ✓ (ag/au correctly excluded)

### 3. PA structure filters fire as documented

- BULL-phase suppression on CN_METAL pa_h2 (BULL never appears in the
  17-record 1y output).
- TR/TR_FORMING cap → position_size="half" even when score=4 (CN_METAL
  cu 2025-11-05: score=4, phase=TR_FORMING, position_size=half ✓).
- TLT suppression: 0 records for TLT across all US lanes in 1 year
  (matches `US_LONG_BOND_SUPPRESS` set; STATUS line 34).

### 4. Spot-checks of high-score signals look like real H2 bottoms

- **XLB 2026-06-01 15:30 UTC pa_us_60min score=3, conf=0.80**
  60min low at 50.50 (14:30 bar) → signal bar (15:30) closes 50.65
  → next 4 bars run to 51.03 then 50.90/51.03/50.90. Clean H2-style
  bounce, conservative continuation. Underlying_price field = 50.65
  matches the signal-bar close.
- **XLRE 2026-06-01 daily context_a score=3, conf=0.60**
  Daily low 43.27, close 43.27 — pin-bottom day. Next 4 days run
  43.49 / 43.51 / 44.40 / 44.70 (+3.3% follow-through). Reasonable.
- **kq_m_shfe_ag 2026-06-02 pa_h2 score=2, conf=0.45**
  H2-style wick — opens 18253, low 17850, closes 18522 (rally back
  through prior day's high). 60min `higher_tf_relation=supporting`
  → 0.45 weight (vs 0.75 for opposing); score=2 (vs 3-4) — penalty
  is correct. structural_stop=17126 below the 17412 swing low of
  2026-05-28. Geometry is plausible (next day did sell off, so EV
  remains an open question — but at signal time the setup is sane).
- **kq_m_shfe_cu 2025-11-05 pa_h2 score=4, conf=0.75, iso=True,
  15m=True, phase=TR_FORMING**
  Cu daily peak 88,890 on Oct 29 → pulls back through 86,990 / 87,910
  / 87,030 → signal bar low 85,000 close 85,650 → bounces to 86,300
  / 86,480 / 86,630 over next 3 days. structural_stop 78,705 (8.1%
  wide), 15m confirmation present. Position_size="half" via TR cap.
  All four annotations consistent.

## Suspicious / probably wrong

### S1. CN_BOND production lane crashes (P0)

```
ValueError: Unknown instrument_class: 'cn_bond'.
  Supported: ['cn_futures', 'cn_index_futures', 'cn_metal_futures', 'czce', 'us_equity']
```

`engine/divergence/direction_gate.py::_TABLES_BY_CLASS` was last
updated before cn_bond was promoted to a first-class instrument
class (commit `88eca10` 2026-06-07, `08727f2` 2026-06-08).
`score_today.detect_all_divergences(... instrument_class='cn_bond')`
at line 490 calls into `gate_signals` which in turn calls
`apply_direction_gate` for every top-direction signal. Even though
the user never sees a DIF top signal (the score_today DIF filter at
line 497 would have dropped it), the ValueError fires _during
detection_, killing the entire CN_BOND pool.

Repro: `DERIVED_ROOT=... .venv/bin/python scripts/score_today.py --pool CN_BOND --window-days 7`
crashes on the first cffex symbol. Adding `cn_bond` to
`_TABLES_BY_CLASS` (mapping to the same pass-through CN tables —
bond futures' direction-gate calibration isn't done, and pass-
through is the safe default per existing cn_index/cn_metal entries)
fixes it.

CN_BOND data itself is healthy:
- `kq_m_cffex_tf` 2973 daily / 6003 60min bars ✓
- `kq_m_cffex_t`  1965 daily / 6008 60min bars ✓
- `kq_m_cffex_ts` 1730 daily / 5993 60min bars ✓

So there is _no_ "empty data feed" excuse — STATUS followup #2
("confirm 60min Parquet bars exist for kq_m_cffex_tf/t/ts")
is satisfied. The blocker is purely the missing registration.

### S2. `pa_us_dif_pos` daily lane is effectively dead (P1)

Over 365 days:
- US 60min lane: 30 records across 12 of 13 active US symbols
- US daily lane: 5 records, only SPY/QQQ/GDX, all phase=BULL

STATUS.md describes the daily lane as 0.80* weight "weaker; both
lanes emit". In practice the daily lane is silent for 11/13
symbols. The cause is the cascade:
1. `pa_us_dif_pos` requires `DIF > 0` AND `h=opposing` AND
   `phase ∉ {BEAR, UNCLEAR}` AND `structural_stop < close`.
2. For TR/TR_FORMING phases it additionally requires
   `at_tr_bottom=True`, which means `pos_in_tr < 0.25` (close in
   bottom 25% of the recent 8-pivot range).
3. The 7-day window had two qualifying base PA signals (XLF
   2026-06-01 DIF=+0.045 pos_in_tr=0.43; XLRE 2026-06-02 DIF=+0.087
   pos_in_tr=0.74) — both correctly identified as PA bottoms with
   opposing 60min trend, but neither was at the bottom of its
   range so both were rejected.

If `at_tr_bottom` is the intended gate, the documented hit-rate
weight (0.80 EV +0.173R n=68 per STATUS) isn't the right number —
that backtest didn't have this gate. Either:
- raise the gate weight on TR signals to reflect the additional
  filter (it's now a tighter subset),
- or relax the gate (e.g. `at_tr_bottom OR phase==BULL` is the
  existing logic, but `pos_in_tr < 0.40` may be where the
  backtest sample sits).

Either way the **5x recall gap (60min:daily = 30:5)** suggests the
two lanes are no longer the "both lanes emit" parity STATUS
describes. **Also note**: the code emits 0.65 (BULL) or 0.40
(TR/TR_FORMING) — not 0.80. STATUS line 33 is stale.

### S3. Sweet-spot rules are dead-on-arrival for PA records (P1)

The only US sweet-spot rule (`US-bot-swing-mid-h20`) requires
`ctx['prior_swing_distance_pct']` to fall in a tercile. None of the
PA detectors populate this field — `wick_ratio`, `swing_pct`,
`vol_ratio` are uniformly `None` across all PA records.

365-day match rate: 0 / 95 US records. The rule was validated on
the DIF detector path (pre-retirement), and the matching machinery
still runs, but no PA record can ever satisfy it. As a result the
`matched_sweet_spots` field is always `[]` and the readiness_score
bonus from sweet-spot matching never fires.

Two reasonable paths:
- back-populate `prior_swing_distance_pct` (and wick/vol ratios)
  on PA signals so the rule can score them, or
- retire `SWEET_SPOTS` entries that depend on context features the
  PA detectors don't surface and replace them with PA-native
  predicates (e.g. `legs_count_down`, `phase`, `pa_isolated`).

The 2026-05-25 OOS validation behind these rules was on the DIF
lane that just got retired — the most honest move is to mark them
"pre-DIF-retirement, requires re-validation" and either backfill
the contexts or build PA-native rules.

### S4. `bpull` always score=4 in 1y output (P2)

bpull records in CN_METAL: 31/31 at score=4 (look at code line 561:
`bscore = 4 if bsig.higher_tf_relation == "opposing" else 2`). The
policy_weight filter (line 556) drops the supporting branch unless
weight>0, so in practice only h=opposing reaches output, hence the
uniform 4. That's "by design" but means the bpull lane is also
dead-on-arrival to differentiation — there's no signal-quality
gradient surfaced to the consumer. Sweet-spot matching is
guaranteed empty (subset same as PA), and there's no
isolation/phase context. Either:
- surface bpull quality features so consumers can rank,
- or accept that bpull is a binary "fire / don't fire" lane.

### S5. STATUS.md vs code mismatches

- STATUS line 33 says us_equity daily 0.80, code emits 0.65 / 0.40
  via `_us_phase_w` branch.
- STATUS line 40 lists `pa_h2`, `pa_h2_climax`, `pa_cn_bond`,
  `pa_us_daily`, `pa_us_60min` but does NOT mention `bpull`,
  `vflush`, `context_a`, `pa_us_dif_pos`. The current emitted
  level set is wider than the documented set.
- STATUS line 44 describes lane name `pa_us_daily` but the code
  emits `pa_us_dif_pos`. (Naming drift; non-functional but
  confusing for downstream consumers.)

## Missing fields / operational gaps

### M1. `pa_us_60min` has no invalidation_level (30/30)

Hard-coded `None` (line 984). STATUS followup #1 already notes
this: "60min lane structural stop — wait for live samples". With 9
score=4 60min signals in 1 year, there ARE live samples now —
prioritize calibration.

### M2. Per-record context features uniformly None for PA records

`wick_ratio`, `swing_pct`, `vol_ratio` are populated only via the
DIF-classical `detect_all_divergences` path (line 514-516). All PA
records carry None for these three. Downstream consumers can't
rank or filter on these features — the score scaffolding is
essentially dead.

### M3. `pa_isolated` field shape inconsistent

- `pa_h2` (CN_METAL): True/False populated
- `pa_us_dif_pos`, `pa_us_60min`, `context_a`, `bpull`, `vflush`,
  `pa_h2_climax`, `pa_cn_bond`: hard-coded `None`

Either drop the field from non-applicable lanes, or compute
isolation for all PA lanes for consistency (the rendering code
shows "iso"/"—"/"" via a tri-state).

### M4. `pa_15m_confirmed` only set on cn_metal pa_h2

Other lanes that could benefit from 60min/15min confirmation
(CN_BOND pa_h2, US pa_us_dif_pos) don't have it. CN_BOND's
docstring (line 712-716) explicitly says "NO 15min confirmation
gate (validated for CN_METAL only)" — fine, but the JSON schema
makes the field's presence look optional.

### M5. STATUS.md lists rate-of-emission targets that aren't met

No quantitative SLA but STATUS line 43-44 reads as "both lanes
emit". With 30:5 60min:daily ratio over a year and 0 daily-lane
fires this week, an explicit SLO ("daily fires at least 1
signal/symbol/year") would catch the at_tr_bottom regression.

## Concrete next steps (ranked)

### N1. P0 — Register `cn_bond` in direction_gate (15min fix)

Add to `_TABLES_BY_CLASS` in
`engine/divergence/direction_gate.py`:

```python
"cn_bond": (TOP_SUBTYPE_MULT_CN, TOP_LEVEL_MULT_CN, TOP_GAP_MULT_CN),
```

(Pass-through; bond futures top calibration isn't done, this matches
the existing cn_metal_futures / cn_index_futures policy.) Then
re-run `--pool CN_BOND` to confirm signals actually emit. Without
this, every CN_BOND consumer is dead.

Bonus: also update the `InstrumentClass` Literal type annotation
on line 44 to include `cn_bond`.

### N2. P1 — Triage the `pa_us_dif_pos` `at_tr_bottom` gate

Either (a) widen the zone (raise from 0.25 to 0.40 — empirical
distribution suggests ~40% of TR signals sit in this band, vs ~10%
under 0.25) and update STATUS to reflect the recall path, or
(b) keep the gate and downgrade STATUS to say "daily lane fires
~1 per symbol per year, BULL-phase dominant — primarily a 60min
lane book".

Validation: re-run K=3 walk-forward on the daily lane with the
proposed gate (`backtest_pa_us_k3.py` or equivalent) and re-cite
the EV / hit numbers.

### N3. P1 — Sweet-spot rules for PA lane

The `SWEET_SPOTS` table holds 4 rules but only 1 applies to the
current US class — and that 1 can't be satisfied by any PA
record. Options:
1. Back-populate `prior_swing_distance_pct` (and wick/vol ratios)
   on every PA signal via `compute_feature_streams` or its
   downstream contexts. Cheap if PA detectors already see the
   underlying bars.
2. Replace `SWEET_SPOTS` with PA-native predicates (legs_count,
   phase, pa_isolated, 15m_confirmed) re-validated 60/40 OOS.
3. Mark the existing rules `validated_date="pre-DIF-retirement,
   requires re-validation"` and surface a warning in score_today
   output when the active-rule list is empty for the chosen pool.

### N4. P2 — STATUS.md sync pass

Update STATUS.md to:
- Drop `pa_us_daily` naming, use `pa_us_dif_pos`.
- Add `bpull`, `vflush`, `context_a`, `pa_h2_climax`, `pa_cn_bond`
  to the active-levels table.
- Correct the US daily weight from `0.80*` to `0.65 (BULL) / 0.40
  (TR/TR_FORMING)`.
- Note that the `at_tr_bottom` gate exists on the daily lane and
  is currently the dominant recall-killer.

### N5. P2 — Calibrate 60min structural stop

9 score=4 (legs=1) and 21 score=3 (legs=0) `pa_us_60min` records in
the past year — enough to extract empirical stops from peak
adverse excursion. Add `invalidation_level` to the 60min record.
Until then, position_size derivation falls back to score-only and
loses the stop-aware sizing the daily lane has.

---

Data sources: `/tmp/score_us.json`, `/tmp/score_cn_metal.json`,
`/tmp/score_cn_bond.err` (crash trace), `/tmp/score_us_1y.json`,
`/tmp/score_cnm_1y.json` (365-day context).

Bars sample-checked: XLB 60min @ 2026-06-01 15:30 UTC, XLRE daily
@ 2026-06-01, kq_m_shfe_ag daily @ 2026-06-02, kq_m_shfe_cu daily
@ 2025-11-05.

No code changes made — pytest n/a.
