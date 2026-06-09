# pa_us_dif_pos daily TR/TR_FORMING 0.30 sub-cell — K=3 — KEEP 0.30 (2026-06-10)

**Verdict: KEEP 0.30 (validated-marginal / monitoring-grade).** The un-gated
TR/TR_FORMING phase subset of the `pa_us_dif_pos` daily lane is walk-forward
tested for the first time. It is **consistently positive-EV but marginal** at
the production stop framework, and **fails the 3/3-OOS promotion bar** (F1
negative). So: do **not** raise the weight, do **not** suppress to 0 — the
deliberately-low 0.30 placeholder (set in B1-1 when the `at_tr_bottom` gate was
dropped) is the right number, now backed by evidence rather than a guess.

This closes pa_us_60min baseline open-item context for the **daily** lane only.
The 60min lane's own TR/TR_FORMING 0.30 cell (`baselines/pa_us_60min_us_equity.json`
notes #1) is a separate validation, not done here.

## What the 0.30 weights

`score_today.py:1349-1362` (lane `pa_us_dif_pos`): after the production gate
(`DIF>0 & h=opposing & phase∉{BEAR,UNCLEAR} & structural_stop<close`), the
signal is weighted by **PAStructure phase** — `BULL=0.65`, `TR/TR_FORMING=0.30`.
The 0.30 was set deliberately low because the un-gated TR subset had never been
independently walk-forward validated (B1-1, 2026-06-08; `score_audit_2026-06-08.md`
§S2 lowered it 0.40→0.30 after dropping the dead `at_tr_bottom` gate).

## Method

Harness: `src/scripts/backtest_pa_us_k3.py` (commit 52db5c6d at run time).
Scans daily bars via `PABottomDetector` (production path), simulates forward
(ATR×1.5 stop — the pa_h2_us_equity WF framework — `max_hold=40`, `min_gap=10`,
TP1-boundary partial-exit credit included). Each signal is tagged with
`PAStructureDetector.detect(bars, up_to_idx).phase` — the exact call production
uses — and `structural_stop < close`. The phase cell applies the **production
gate** and drops production-suppressed symbols (`tlt/dia/spy`). K=3 folds:
IS≤2022 / F1=2023 / F2=2024 / F3=2025+ (IS absorbs the long pre-2023 history).

Repro:
```
cd src && .venv/bin/python scripts/backtest_pa_us_k3.py            # production config
cd src && .venv/bin/python scripts/backtest_pa_us_k3.py --stop-mult 2.0
cd src && .venv/bin/python scripts/backtest_pa_us_k3.py --min-quality 0.1
```
Read the `── PA structural phase × production pa_us_dif_pos gate ──` block,
`[production(excl tlt/dia/spy)]`.

## Results — production view (excl tlt/dia/spy)

Production config (1.5×ATR, min_quality 0.3):
```
BULL (w=0.65)            n=  6  EV=+1.083R  hit=83%   IS=—  F1=+1.500(1) F2=—  F3=+1.000(5)
TR+TR_FORMING (w=0.30)   n= 36  EV=+0.069R  hit=36%   IS=-0.222(9) F1=-0.125(4) F2=+0.562(8) F3=+0.033(15)
  TR                     n=  0
  TR_FORMING             n= 36  (identical — the whole subset is TR_FORMING)
```

Robustness (TR+TR_FORMING cell across stop width / min_quality):
```
1.5×ATR  mq0.3  n= 36  EV=+0.069R   IS=-0.222 F1=-0.125 F2=+0.562 F3=+0.033   (2/3 OOS+, F1<0)
1.5×ATR  mq0.1  n=138  EV=+0.049R   IS=-0.398 F1=+0.088 F2=+0.394 F3=+0.268   (3/3 OOS+, IS<0)
2.0×ATR  mq0.3  n= 36  EV=+0.410R   IS=+0.018 F1=+0.250 F2=+0.562 F3=+0.606   (4/4 folds+)
2.0×ATR  mq0.1  n=138  EV=+0.199R   IS=-0.351 F1=+0.382 F2=+0.454 F3=+0.548   (3/3 OOS+, IS<0)
```

## Findings

1. **TR is empty; the subset is entirely TR_FORMING.** `PAStructureDetector`
   rarely emits a confirmed `TR`; H2 bottoms land in `TR_FORMING`. (Same shape
   the PA-TOP A_top run saw — `pa_atop_wf_2026-06-10.md`.)
2. **TR_FORMING now dominates the daily lane.** Production-gated: 36 TR_FORMING
   vs 6 BULL (86%). After B1-1 dropped `at_tr_bottom`, the lane's quality
   effectively *is* this cell — so weighting it correctly matters.
   (Contrast `score_audit_2026-06-08.md` §S2's "5 records, all BULL" — that 365d
   window still had the `at_tr_bottom` gate killing TR signals.)
3. **Marginal at the production stop, fragile to stop width.** At 1.5×ATR
   (production WF framework) TR_FORMING is +0.069R with F1 negative — below the
   3/3-OOS bar that promoted pa_us_60min. It never goes negative across the four
   variants, but only turns *clearly* positive with a wider 2.0×ATR stop
   (+0.410R, 4/4 folds). That stop-width sensitivity is the structural fingerprint
   of a forming-range regime: tight stops get whipsawed in the chop.
4. **BULL stays at 0.65.** n=6 is too thin to raise; +1.083R only confirms
   direction.

## Decision

- **`TR/TR_FORMING` weight: KEEP 0.30.** Positive-EV but marginal and fails the
  walk-forward promotion bar → no raise; never negative → no suppress. Status
  flips from "un-validated placeholder" to "validated-marginal, monitoring-grade."
- **No production behavior change** (`score_today.py` weight unchanged; comment
  updated to cite this memo instead of "not validated").
- **`BULL` weight: KEEP 0.65.**

## Backlog (not done here)

- **Stop-width-by-phase lead**: TR_FORMING jumps to +0.410R / 4-of-4 folds at
  2.0×ATR. A phase-conditional stop (wider for TR_FORMING) is a real optimization
  lead, but it changes the production stop model (currently structural stop) and
  is out of scope for "define the weight." Revisit if the daily lane is promoted
  from monitoring.
- **60min lane TR/TR_FORMING 0.30** (`pa_us_60min_us_equity.json` notes #1) — its
  own validation, separate harness (`backtest_pa_swing.py --dataset us_60min`).
