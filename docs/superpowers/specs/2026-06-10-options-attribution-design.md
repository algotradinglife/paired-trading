# Options-layer P&L attribution — ag/au — design

**Date:** 2026-06-10
**Status:** Codex-reviewed (2 P2 emission-faithfulness fixes applied) — pending user spec-review, then implementation plan
**Scope:** First slice of the options-layer initiative = "validate & make auditable" (not extend, not infra-rebuild).

## Problem & framing

The futures lanes just gained rigorous `baselines/` + `validate_baselines.py --full` + weekly drift-gate discipline. The **options layer** — the承重墙 that expresses both up- and down-side via `score_today`'s emitted `options_calls` — has **none** of it. It emits ag/au OTM-call suggestions with no systematic, reproducible P&L attribution binding them to measured edge. Findings exist but are scattered across ad-hoc scripts + memory, never frozen into an auditable single source of truth.

**The pricer is not dead.** The handoff's "Black-model pricer didn't survive migration" caveat is narrow: only one *bespoke 2026-05-31 CN_AGRI+CN_METAL RR simulation harness* is gone (`src/tools/repro_options_simulation.py` documents this, and runs fine today). Working Black machinery + real-data lookups already live in the selectors. So this slice does **not** rebuild a pricer.

## Key facts established (grounded interfaces)

- **Live emission gate**: `instrument_class == "cn_metal_futures"` AND `sym.endswith("_ag"|"_au")` AND `sig.direction == "bottom"` AND `score >= 3` (`_OPTIONS_MIN_SCORE`). There are exactly **4 ag/au emitters**, each in its own detector loop (verified by reading `score_today`, corrected per Codex review):
  | emitter | emit site | `mm_target_pct`? |
  |---|---|---|
  | divergence main scan | `913/923` | **yes** — `_compute_mm_pct(sig, bars, entry_close)` (`score_today.py:68`); the signal carries `reference_bar_idx`/`candidate_bar_idx`/`price_side` |
  | BPull | `977/981` | no — `select_otm_calls(bentry_close, bsig_date)` |
  | PA H2 | `1092/1096` | no — `select_otm_calls(pa_close, pa_date)` |
  | Context A | `1293/1301` | no — `select_otm_calls(aclose, asig_date)` |
  **VFlush does NOT emit options** (the `options_calls: None` at `1230` is never populated for ag/au) and the cn_bond PA H2 loop (`1168`) excludes ag/au. Both are outside the attribution universe.
- **`select_otm_calls(underlying_price, signal_date, n_strikes=3, mm_target_pct=None)`** (`src/engine/options/cn_ag_selector.py:78`; `_au` twin in `cn_au_selector.py`) returns dicts: `{strike, otm_pct, expiry_month, contract_sym (e.g. "ag2507c8300"), days_to_expiry, mm_target_pct, is_mm_strike}`. Expiry = first 20-60 DTE contract.
- **Pricers already present** in each selector: `_bs_call_price(...)` (Black model, line 192), `estimate_iv(...)` (229), `lookup_option_price(...)` (290, real-data), `enrich_with_iv(...)` (376).
- **Real option data**: `data/options/cn/{ag,au}/{contract}_*.json` (daily; TqSdk intraday also available per `project_cn_options_intraday_tqsdk`). Coverage is partial; 2026 signals may lack ready IV.
- **Underlying futures bars**: `data/raw/kq_m_shfe_{ag,au}` (daily).
- **Validated exit precedent** (`project_ddline_options_findings`): ag B1/B2 robust (~1.29x, IS+OOS consistent); au Strategy A robust (1.80x); au B1/B2 **regime-only** (IS fails → only 2025 gold bull); cu/rb universally negative. DD-line params: `take1=2.0x`, `take2=4.0x`, `stop=5 ticks` (tick ag=1.0, au=2.0), `max_hold=30d`.

## Decisions (locked with user)

1. **Goal:** validate & make auditable (mirror futures baseline discipline).
2. **Scope:** ag + au only (= what `score_today` actually emits).
3. **Entry/exit:** signal-day close on the emitted OTM call (Strategy-A style = live emission), validated **DD-line take/stop** exit.
4. **Pricing:** real option data primary, **Black-76 fallback only when a contract has no data**, modeled fraction reported.
5. **Auditable depth:** baseline JSON + repro harness + repro doc. Drift-gate / `--full` integration is an explicit follow-on, **not** in this slice.
6. **Primary cell = Rank 1** (nearest OTM); Rank 2/3 and `is_mm_strike` reported as secondary cells.
7. **Exit params = the DD-line validated set** (take1=2x / take2=4x / stop=5 ticks / max_hold=30d) — the more thoroughly IS/OOS-validated set; standardize over the ag-swing take2=3x variant.

## Section 1 — Pipeline & module layout

New orchestrator `src/scripts/backtest_options_attribution.py`, run per underlying:
```
backtest_options_attribution.py --underlying ag|au [--out-json PATH]
```
Five stages, each a small testable unit:
```
replay → emission → price-loader → exit-sim → aggregate
```
Reuses (does not duplicate): the detector path from `score_today`, `select_otm_calls`/`_au` + `_compute_mm_pct`, the selector pricers, and the validated exit-sim (extracted from `sweep_ddline_options.py` into a shared helper so both call it).

## Section 2 — Stage 1: replay signals

Walk ag/au daily futures bars. Regenerate **bottom** signals through the **4 emitting detector loops only** — divergence main scan, BPull, PA H2, Context A (NOT VFlush, NOT cn_bond; see Key facts table) — and apply the live gate where each attaches `options_calls`: `direction == "bottom"` AND `score >= 3`. Each loop runs its own detector with the same params `score_today` uses and enforces the same `min_gap`. Output: one record per gated signal tagged with its **emitter** (so Stage 2 replays the correct call signature), plus `sig_date`, `entry_close`, the `sig` object, and the year (for folds).

**Faithfulness requirement:** the score and signal set per emitter must match `score_today` (same detector params, same scoring). The plan confirms whether each emitter's scan + scoring is importable in isolation or needs a small shared refactor rather than re-deriving it.

## Section 3 — Stage 2: emission

Replay **each emitter's exact live call signature** (per the Key facts table) — this is a per-emitter detail, not a uniform call:
- **divergence main scan only**: `mm_pct = _compute_mm_pct(sig, bars, entry_close)` then `select_otm_calls(entry_close, sig_date, mm_target_pct=mm_pct)`. Only this signal type carries the `reference_bar_idx`/`candidate_bar_idx`/`price_side` fields `_compute_mm_pct` needs.
- **BPull / PA H2 / Context A**: `select_otm_calls(entry_close, sig_date)` with **no** `mm_target_pct` (mirrors live; calling `_compute_mm_pct` on these would crash and would diverge from production).
- ag → `select_otm_calls`, au → `select_otm_calls_au`.

The emitted list is the attribution universe. **Primary = `calls` sorted by `otm_pct` ascending → index 0 (Rank 1).** The `is_mm_strike` tag (only ever set on divergence-emitter calls) drives the secondary mm-cell.

## Section 4 — Stage 3: price-loader (the one real abstraction)

Single interface making "market vs model" explicit:
```python
def premium_path(contract_sym: str, entry_date: date, horizon_days: int,
                 underlying_path, *, tick: float) -> PremiumPath
# PremiumPath = {prices: list[float], source: "market" | "model", first_price: float}
```
- **market**: real premium series for the exact `contract_sym` via `lookup_option_price` over `data/options/cn/{ag,au}/`. Used when the contract has ≥ a minimum number of bars covering the hold window.
- **model**: Black-76 (`_bs_call_price` over the underlying futures path + `estimate_iv`) when market data is absent/insufficient.
- Every trade carries its `source`; aggregate reports **`modeled_fraction`**. This is the auditability guarantee — disclose how much P&L is modeled vs measured.

## Section 5 — Stage 4: exit-sim

Shared helper (extracted from `sweep_ddline_options.py`), DD-line params:
- entry premium = `first_price` at signal-day close.
- `take1 = 2.0×` entry → bank partial; runner to `take2 = 4.0×` (full) or stop/max_hold.
- `stop = entry − 5 × tick`.
- `max_hold = 30` days.
- **TP1-at-boundary partial-exit credit** applied (same boundary-bug lesson fixed on the futures simulators — credit the partial when take1 banks then runs to the hold boundary).
- Returns `EV_mult` (premium multiple; 1.0 = breakeven), plus the exit reason.

## Section 6 — Stage 5: aggregate (folds + verdict)

- **Folds:** IS ≤ 2023-12-31 / OOS ≥ 2024-01-01 (ag/au samples are thin — K=3 annual would be too sparse). Per-year sub-rows reported when n permits.
- **Verdict criteria:**
  - **PROMOTE** = `EV_mult > 1.0` in **both** IS and OOS (robust, not single-regime).
  - **REGIME-ONLY / MONITORING** = OOS-only positive (the au B1/B2 failure mode).
  - **REJECT** = IS and OOS both ≤ 1.0.
- Reported per primary (Rank 1), plus Rank 2/3 and mm-strike secondary cells, plus `modeled_fraction`.

## Section 7 — Auditable artifact: baseline schema

`baselines/options_ag.json` + `baselines/options_au.json` — options-native (NOT forced into R-multiple schema v2):
```jsonc
{
  "lane": "options_ag",
  "underlying": "kq_m_shfe_ag",
  "emission_binding": "score_today.py:906-925; cn_ag_selector.select_otm_calls",
  "entry": "signal-day close, Rank-1 OTM call (score>=3 bottom)",
  "exit": {"take1": 2.0, "take2": 4.0, "stop_ticks": 5, "tick": 1.0, "max_hold_days": 30},
  "pricing": {"market_n": 0, "model_n": 0, "modeled_fraction": 0.0},
  "samples": {"is": {"n": 0, "ev_mult": 0.0, "win_pct": 0.0},
              "oos": {"n": 0, "ev_mult": 0.0, "win_pct": 0.0},
              "by_year": {}},
  "cells": {"rank1": {}, "rank2": {}, "rank3": {}, "mm_strike": {}},
  "verdict": "PROMOTE | REGIME_ONLY | REJECT",
  "verdict_reason": "...",
  "repro_command": "cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying ag",
  "data_snapshot": "2026-06-10",
  "valid_until": "2026-..."
}
```

## Section 8 — Repro doc

`doc/repro/options_attribution_2026-06-10.md`: method, results table (IS/OOS per rank), modeled-fraction disclosure, verdict per underlying, caveats (coverage gaps, illiquid-strike model reliance, thin n).

## Section 9 — Testing

- **price-loader**: market-lookup hit; Black-76 fallback selection on missing contract; modeled-fraction accounting; insufficient-coverage → model.
- **exit-sim**: take1/take2/stop/max_hold + TP1-at-boundary partial-exit credit (one regression, mirroring `tests/test_simulate_trade_boundary.py`).
- **harness determinism**: same inputs → identical baseline output, incl. a `data_hash`-style stamp over the option-price inputs.

## Section 10 — Out of scope (explicit follow-ons)

- Drift-gate / `validate_baselines --full` integration for options baselines.
- DD-line option-K-line entry (B1/B2) — separate, does not bind to live emission.
- US ETF options edge (`option_payoff_backtest.py`, Polygon).
- cu/rb negative-control baselines.

## Risks / caveats

- **Coverage gaps**: `select_otm_calls` picks specific strikes that may never have traded / lack data → high modeled fraction. Mitigation: report it per underlying; if `modeled_fraction` is high, the verdict is model-dominated and must say so.
- **Illiquid-strike market data** can be staler/noisier than the Black model → "market primary" is not unconditionally more honest. Mitigation: minimum-coverage threshold before trusting market over model; documented in the repro doc.
- **Thin n** (ag ~12-114, au ~114 over the full history; the score≥3 bottom subset is smaller) → folds may be monitoring-grade, not a clean PROMOTE. That is an acceptable, honest outcome (mirrors the futures marginal cells).
