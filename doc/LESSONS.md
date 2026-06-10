# Lessons learned — `paired-trading`

A version-controlled digest of the durable lessons, so they survive a machine
migration even if the out-of-repo auto-memory store isn't copied. The **live,
authoritative store** is the Claude auto-memory at
`~/.claude/projects/<path-slug>/memory/` (MEMORY.md index + ~37 entries); this
file is a snapshot of its load-bearing content as of 2026-06-10. When they
disagree, trust the current code + the memory store.

---

## 1. Methodology & philosophy

- **Signals are posterior inference.** Zero-axis returns, divergences, and
  trend-change ("变盘") are not knowable ex-ante. Algorithms emit a *continuous
  confidence*, not a discrete boolean event.
- **Multi-timeframe is fusion, not a layer.** Single-timeframe pattern confidence
  is unreliable; confidence must be fused across timeframes (aligns with the DIR
  module).
- **Recall-first.** MACD divergence only captures ~5–11% of tradeable swings. The
  bulk of the opportunity is in *new detector types*, not in refining a narrow
  subset.
- **Scope = analysis & probability only.** This project does NOT implement
  concrete trade actions (stops, sizing, contract selection) — those belong to a
  downstream execution system. It outputs confidence/probability for that system.
- **instrument_class-aware.** us_equity vs cn_futures get separate calibrations
  across detector + policy + envelope; don't assume a signal ports across classes.

## 2. Validated findings (live lanes)

- **`h=opposing` is the universal strong signal.** Bottom × h=opposing passes K=3
  strictly (over Bonferroni) across CN + US cross-pool. It is the backbone filter.
- **CN_BOND is the default pool** (CFFEX TF/T/TS): bottom×h=opp EV +0.958R.
- **Detectors that passed:** BPull (CN_METAL DIF>0 EMA20 pullback; `rb` excluded;
  CN_BOND rejected), VFlush (V-shaped flush bottom; `cu`/`sc` only), PA H2
  standalone (CN_METAL h2|h=opp PASS; CN_AGRI rejected), context_A (buy pullbacks
  in uptrend; US + CN_METAL at weight 0.60).
- **Swing quality:** `tight` and `wick` are two *independent* signals; bottom ×
  EMA↓ × opposing × (tight|wick) hit ~91.7%.
- **pa_us_dif_pos daily TR/TR_FORMING weight = 0.30, KEEP** (validated-marginal):
  the subset is entirely TR_FORMING, ~86% of the gated daily lane post gate-drop,
  +0.069R at the production 1.5×ATR stop — fails the 3/3-OOS bar (no raise) but
  positive across variants (no suppress). See `doc/repro/pa_us_dif_pos_tr_k3_2026-06-10.md`.

## 3. Decisions that are CLOSED — do not re-explore

- **DIF detector family is OFF; signal source is PA** (`engine/divergence/pa_*`).
  `include_dif_detectors` defaults False.
- **No PA put / TOP lane.** Three mechanisms all REJECTED. Structural reason: tops
  are *diffuse fatigue* (a process), not a *panic event* — mirroring an
  event-detector onto a process fails, and h=opposing polarity inverts at tops.
  Downside is expressed via the options/hedge layer, not a top detector. Don't
  build another PA-top detector without a genuinely new mechanism class + new
  evidence. (`doc/repro/pa_atop_wf_2026-06-10.md`)
- **Broad-market / defensive names** (DIA/SPY/XLU…) are systematically negative-EV
  in H2 reversals → suppressed. Apply the same suppression to any new US lane.
- **The SPY/SMA200 regime gate is NOT portable** to bottom-reversal lanes —
  bottom-reversal and a trend filter are mutually exclusive. Cross-market portable
  signals are rare.
- **Options layer (slice 1) is MODEL_DOMINATED, not market-validated.** The exact
  emitted ag/au OTM strikes have ~5–21% daily market coverage; the Black-76
  fallback dominates and the verdict is IV-sensitive (au flips REGIME_ONLY↔PROMOTE
  with the IV assumption). Treat as monitoring-grade. Next step: real strike data
  (TqSdk) or an ATM-proxy. (`doc/repro/options_attribution_2026-06-10.md`)

## 4. Engineering & process

- **`baselines/` is the single auditable source of truth.** It is committed.
  `validate_baselines.py --full` does *real* per-(lane,symbol) drift detection
  against the full_stack primary anchor. The rejected "folds-secondary" comparison
  is not reliable (baseline folds are config/symbol-filtered subsets).
- **When reusing validated code, never change its logic to satisfy a plan/test —
  the test may be wrong.** Two instances this project: (1) the validated option
  exit `simulate_entry` uses a half-at-take1 / half-at-take2 *blended* model
  (single-bar t1→t2 span = 3.0×, not 4.0×) — a plan test asserting 4.0× was wrong;
  (2) a faithful emission replay must reproduce production's gates *line-by-line*
  (e.g. pa_h2 skips `phase == "BULL"`; pass `symbol=sym` to `policy_weight`).
  Verify gates against the production source, not against intuition.
- **A shared trade-sim boundary bug** (TP1 banked then the trade runs to the hold
  boundary) was latent across 12 simulators — the post-loop fall-through scored
  raw mark-to-market and dropped the +0.5R partial-exit credit. When writing or
  reusing a forward simulator, check the boundary partial-exit path.
- **Model-priced backtests must disclose `modeled_fraction`** and flag
  model-dominance; a verdict driven by a model + an assumption (IV) is
  monitoring-grade, not validated edge. Truncate modeled option paths at expiry
  (don't price past expiry).
- **Wire `compute_data_hash`**: `backtest_full_stack` emits a deterministic
  `data_hash` over loaded bars so drift attribution can tell a data refresh from a
  code change (enabled once a baseline records the emitted hash in
  `data_snapshot_hash` on a deliberate re-baseline).
- **VCS is `jj` (colocated), not `git`** for writes: `jj describe -m ... && jj new`.
- **Codex review by default** after generating scripts/analysis/reports and after
  each fix; fix P1/P2 before reporting. `codex review --uncommitted` is the
  pre-commit pre-flight; `codex review --base <last-reviewed-commit>` after commit.
- **TDD; commit per logical unit autonomously** (conventional-commit format).

## 5. Collaboration preferences

- **Give a recommendation with reasoning and wait for go-ahead** on judgment calls
  — don't dump an `AskUserQuestion` menu. When you do list options, always mark a
  recommendation. Explain in plain language with concrete examples first.
- **Signal reports lead with macro** (multi-timeframe + trend structure + bull/bear
  context) before the signal itself.
- During concept walkthroughs, clarify thinking — **no pseudocode/code**. Let Song
  Jianyi's framework stand on its own (multi-TF + divergence) before fusing it with
  Xiao Chunxin's options timing.
