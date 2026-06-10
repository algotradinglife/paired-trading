---
name: retired-and-historical
description: "Condensed record of superseded / DIF-retired findings — what's dead and why, so future sessions don't re-explore disproven directions"
metadata: 
  node_type: memory
  type: project
  originSessionId: e09f4ba0-d8ac-433f-a1b3-f1620d4b21f1
---

Condensed during the 2026-06-09 memory migration (project rename
macd-momentum → paired-trading).  These memories were NOT carried
forward verbatim because their findings are superseded or about
retired code — but the *lessons* are kept here so future sessions
don't re-explore disproven directions.  Full originals (if ever
needed) live at the pre-move path
`~/.claude/projects/-Volumes-Data-Drive-workspace-trading-macd-momentum/memory/`.

## PA TOP / put lane — disproven 3 mechanisms deep (do NOT re-attempt)

**DECIDED 2026-06-10: no PA-based put lane.** Three distinct mechanisms all
failed K=3 walk-forward with ZERO promotable cells:
1. **H2-mirror counter-trend** (C4, 1.5×ATR/40-bar) — 0/62 cells.
2. **H2-mirror trend-follow** (2.5×ATR/80-bar, BEAR phase) — 0/62 cells.
3. **A_top sell-the-rally** (`classify_context_top=="A_top"`, the context_A
   mirror; `backtest_pa_atop.py`, 2026-06-10) — REJECT. See
   `doc/repro/pa_atop_wf_2026-06-10.md`.

**Why (structural, consistent across all three):** bottoms work because **panic
is an event** (climactic, measurable: selling-climax bars, extended below EMA,
h=opposing confirms). Tops are **diffuse fatigue / distribution — a process, not
an event**, so event-detectors mismatch. The A_top reframe's *logic* was sound
(BULL-phase sanity gate held: selling rallies in an uptrend is correctly the
death case, −0.185R), but A_top fires almost entirely in choppy **TR_FORMING**
(edgeless), almost never in a PAStructure-confirmed **BEAR** phase (too thin,
n≈15 US / n≈2 CN) — the confirmed-downtrend regime that puts need is sparse in
this data.

**How to apply:**
- Do NOT build/tune another PA top/put detector without a genuinely NEW mechanism
  class AND fresh evidence. The "puts must be in MVP" premise is now satisfied by
  expressing downside via the **options layer / portfolio hedge**, not a PA top
  signal. B1_top was considered and NOT pursued (shares A_top's core problem).
- The bear-side context classifier (`classify_context_top`, A_top/B1_top in
  `pa_context_classifier.py`) stays available for DIR voting only.
- Related: [[baselines-as-auditable-artifacts]] (the K=3 REJECT methodology).

## Retired DIF detector lane (do NOT re-tune these)

The whole DIF-based MACD-divergence detector family was retired in
production 2026-06-08 ("DIF 全退役").  See [[project-signal-source]]
for the live rule.  These shipped-then-retired findings are now dead:

- **HICD detector** — boosted recall +28pp US / +31pp CN, precision
  63%/55%.  Retired.
- **DIFSR + DEAD + bull variants** — DIFSR +0.319R was the star;
  6 `intra_cycle_*` variants shipped, then all retired.  Their sample
  explosion (2.4–10×) is the *root cause* of the 2026-05-31 baseline
  reports collapsing (see STATUS.md repro matrix).
- **CN_INDEX gate (CNI1)** / **CN2 gate** / **CNM1 top gate** — per-pool
  gates that disabled negative DIF sublevels.  Moot now that the whole
  lane is gated off by score_today.
- **DIF-crossing capitulation study** — already concluded *not viable*
  (EV +0.036R; fast MACD(6,13,5) −0.384R).  Do not revisit.
- **DIF>0 missed-swing analysis** / **top_signal_analysis** /
  **top_lagging_red_zone** — DIF-era diagnostics, superseded.

## Superseded policy / data / scope (historical context only)

- **CN policy R4 → R5**: R4's 4 cn_futures rules were validated OOS,
  then R5 (2026-05-26, 14y qveris data) collapsed most magnitudes and
  *deleted* the CN-top-supp-fade rule.  This is *why* `cn_futures` is
  monitoring-only (EV ≈ 0) today.  Filter-tuning hit a wall — don't
  retry magnitude-based cn_futures rules.
- **US policy fragile rules**: B1(1.30)/F3(1.15) couldn't validate OOS
  (n=9).  F2/F1/F8 were the stable ones.  Historical — current US lanes
  are PA-based, not policy-table-based.
- **Exhaustion detector (standalone)**: WF K=3 failed on all 5 cells —
  each feature axis (conf/wick/volume) is a regime *predictor*, not a
  filter.  It survived only as one of the 8 DIR synthesiser sources
  (STATUS.md DIR section), never as a standalone gate.
- **Data source**: early work used a Polygon proxy (daily+60min 5y,
  split-adjusted) and later an AlphaVantage US baseline (10 ETF, 190
  events).  Both superseded — production now reads **Parquet** via
  `data.bar_loader.DEFAULT_QUANT_ROOT` (STATUS.md "Data layout").
- **B-topology experiment** (D+15m+1h execution-aware lens, stock-dir
  64-80%) and **crosspool 6-pool portfolio OOS** (Sharpe 9.43 IS) —
  early-validation artifacts now superseded by the [[baselines-as-auditable-artifacts]]
  registry as the single source of truth.
- **Initial sweet-spots (2026-05-25)** and the **PA integration plan** /
  **post-Layer-9 deliverable spec** — historical milestones.  PA is now
  the shipped system, not a plan; the recall-first paradigm
  ([[project-recall-first-paradigm]]) is the surviving methodology.

## How to apply

- If a request implies re-tuning, re-validating, or "recovering" any
  DIF detector or the dead policy rules above, surface this memory and
  the cost (sample inflation, OOS failure) before spending effort.
- The surviving, still-live findings from this era kept their own
  verbatim memories: [[project-h-opposing-validated-universal]],
  [[project-cn-bond-pool]], [[project-bpull-detector]],
  [[project-vflush-detector]], [[project-pa-standalone-detector]],
  [[project-swing-context-backtest]].
