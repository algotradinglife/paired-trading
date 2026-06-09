# PA TOP Path B — A_top sell-the-rally put lane — design

**Date:** 2026-06-10
**Status:** Approved (Codex-reviewed) — ready for implementation plan
**Supersedes:** the failed H2-mirror PA TOP approach (two walk-forward framings, 0/62 cells promoted — see `doc/repro/pa_top_wf_2026-06-08.md`, `pa_top_wf_trendfollow_2026-06-08.md`).

## Problem & reframe

The system must be able to recommend **put options** ("puts must be in MVP"), which requires a TOP-side signal. The prior approach mirrored the bottom H2 detector (`PATopDetector`) to *call the top*; it failed two walk-forward framings.

**Root cause (the asymmetry):** bottoms work because **panic is an event** — a climactic, point-in-time signature (selling-climax bars, price extended below EMA, h=opposing HTF confirms). Tops are the opposite: **distribution is a process** — gradual fatigue, the *absence* of new buyers. Mirroring an event-detector onto a process is mismatched, and the h=opposing polarity inverts at tops.

**Reframe (approved):** don't call the top. **Sell rallies inside a confirmed downtrend** — the mirror of the validated `context_A` bull lane (buy pullbacks inside an uptrend). The entry trigger is **`A_top`** (a DIF<0 counter-trend rally in a downtrend), which is already implemented in `classify_context_top` but never used as a signal source.

## Key facts established

- `classify_context_top(bars, i, macd_df, ema20, ema60) -> "A_top" | "B1_top" | None`
  (`src/engine/divergence/pa_context_classifier.py:319`). Wired into DIR voting only; NOT a live signal and NOT in any backtest.
- The existing grid `backtest_pa_top_grid.py` is NOT reusable: its signals come from `PATopDetector` (the failed mechanism, line 262) and its `context` dimension uses the bull-side `classify_context` (line 291), not `classify_context_top`. A new harness is required.
- `context_A` (the bull mirror) is validated and live at weight 0.60 on US equity + CN_METAL.

## Decisions (locked with user)

1. **Signal:** `A_top` only (B1_top deferred to a follow-up cell).
2. **Direction:** short / buy-put — enter into the rally, profit on downtrend resumption.
3. **Stop:** ATR-based **above** entry in the harness; production structural stop sits at **resistance** (rally high / recent lower-high) per the locked "止损架在压力/支撑线附近" methodology (mirror of the long lanes' below-support stop).
4. **Validation method:** stratified K=3 discovery — let the data define the downtrend gate, exactly how `swing_context` found the bottom lane's winning cell. Do NOT pre-pick a gate.
5. **Seed pools:** US equity + CN_METAL (where `context_A` works).
6. **Productionization is conditional** on the K=3 result (promote vs REJECT). Do NOT force a negative-EV put lane live.

## Section 1 — New validation harness `backtest_pa_atop.py`

Mirrors `backtest_pa_swing.py` / `backtest_pa_standalone.py`. For each symbol in each seed pool:
- Load bars; compute `macd` (→ `macd_df`, `hist`), `ema20`, `ema60`, ATR.
- Scan bars `i`; **fire when `classify_context_top(bars, i, macd_df, ema20, ema60) == "A_top"`**.
- Enforce `min_gap` between consecutive fires (mirror existing harnesses).
- **Forward-sim a SHORT** (signs flipped vs the long harnesses):
  - entry = signal bar close (or next-bar open — match the existing harnesses' convention).
  - stop = entry + `stop_mult × ATR` (ABOVE).
  - target/exit: max_hold bars; realized R = (entry − exit_price) / (stop − entry) so a downmove is positive R.
  - reuse the existing forward-sim helper with a `direction="short"` parameter if one exists; else a local mirror.
- Tag each trade with: `period` (IS/OOS1/OOS2/OOS3 from cutoffs), `phase` (BEAR/TR/TR_FORMING/BULL/UNCLEAR via `PAStructureDetector`), `h_rel` (higher-TF relation — HTF DIF sign vs the signal), `pool`, `symbol`, `r`.
- Aggregate a **phase × h_rel** grid per pool with per-fold (IS/F1/F2/F3) n + EV, mirroring `backtest_pa_swing.py`'s report format. Support `--cutoff1/2/3` (default annual: 2022-12-31 / 2023-12-31 / 2024-12-31).

## Section 2 — Decision rule + built-in sanity checks

- **Promote** a cell only if it clears the bottom-lane bar: **3/3 OOS folds positive** with adequate per-fold n (treat n<10 folds as thin, like the pa_us_60min precedent — robustness across an alternate cutoff framing required before calling PASS).
- **Reframe sanity gate:** **BULL-phase A_top must be NEGATIVE** (selling rallies in an uptrend = the death case). If BULL-phase A_top is *not* negative, the reframe premise is suspect — STOP and report rather than promoting.
- **Polarity watch:** for a put, the confirming `h_rel` is expected to be **h=supporting** (HTF bearish, same direction as the short) — the OPPOSITE of the bottom lanes' h=opposing. The grid reveals which wins; document it.

## Section 3 — Productionization (conditional on a promotable cell)

**If a cell promotes:**
1. Write `baselines/pa_atop_<pool>.json` (schema v2): `full_stack_lane`, `symbols_included`, `samples` (is/f1/f2/f3), `samples_aggregate`, `verdict`, `policy_weight_assigned/recommended`, `fold_date_ranges`, `repro_command`, `production_binding`, `valid_until`, `commit_hash`, `last_verified`.
2. Wire into `score_today.py`: emit a **put** signal when `classify_context_top == "A_top"` on the winning phase/h_rel cell, with the bear-side context (`A_top`) and a **structural stop at resistance** populating `invalidation_level` (rejected to None if the computed stop ≤ entry, mirroring the long lanes' ≥-close reject).
3. Add the lane to `backtest_full_stack.py` (a `_lane_atop` emitter) so the lane gets a per-`(lane,symbol)` `full_stack` anchor — this makes the weekly drift gate cover it automatically.
4. Register in `baselines/EXPECTED_LANES.json`.

**If NO cell promotes:**
- Write `baselines/pa_atop_<pool>.json` with `verdict: REJECT` + the evidence (per-fold table), and a `doc/repro/pa_atop_wf_2026-06-10.md` memo.
- Report back: the "puts in MVP" question returns to the user (B1_top next, or accept no put lane) — do NOT wire a negative-EV lane.

## Section 4 — Testing

- Unit tests for the harness (mirror existing harness tests): `period` fold-tagging from cutoffs; the SHORT forward-sim R sign (a downmove → +R, an upmove to stop → −1R); `min_gap` enforcement; an A_top fire produces a trade row.
- The K=3 run itself is the validation (slow; manual, not a unit test).
- If productionized: `validate_baselines.py` (+ `--full`) clean; drift gate quiet; full pytest suite green.

## Out of scope (this pass)

- `B1_top` (first-pullback) — deferred to a follow-up cell after A_top is settled.
- Pools beyond US equity + CN_METAL.
- The options-layer P&L attribution (separate initiative).
- Any change to `PATopDetector` (the failed mechanism is left as-is, unused for this lane).
