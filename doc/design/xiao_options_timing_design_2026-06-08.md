# Xiao Options Timing — Signal-Layer Design Memo

**Date**: 2026-06-08 · **Status**: design draft (no code yet)

The third theory pillar — 肖淳心《飞天期权择时》 — is currently the most
data-rich and signal-poor.  We have ~60 k option payoff rows in
`derived/.../option_payoffs_parquet_cn_v2.csv` and live OTM-selector
code, but no **timing signal layer**.  This memo proposes what to build.

## 1. What "Xiao timing" means (working understanding)

Pieced together from `doc/legacy/options-simulation-report-2026-05-31.html`,
the `cn_{ag,au}_selector.py` comments, and `doc/cn-option-payoff-backtest-2026-05-24.md`:

- **Underlying-first**: the option trade exists only if the underlying
  has a validated directional signal (MACD divergence or PA H2).
  Options are not a standalone signal source.
- **OTM ladder**: buy 1st/2nd/3rd OTM call (≈+1.7/+2.9/+4.1 % above
  spot for ag), 20-60 DTE, sized so one rank carries the measured-move
  target `B2 + (H1 − B1)`.
- **4-tick stop on the underlying** — the killer detail.  Exit when
  the underlying moves 4 ticks against entry, not when the premium
  falls X %.  Legacy report: with 4-tick stops, fully-stopped trades
  bled −8.6 % of premium vs −51.9 % under ATR×1.5; theta + delta
  compound fast once the underlying turns.
- **Time scoping**: T = 17 trading days, TP1 = +1R (sell half),
  TP2 = +2R (sell rest), max-hold = T forced exit.
- **HV20 ≈ IV** in backtest; in production we back IV out from the
  option close via the BS solver already in `cn_ag_selector.estimate_iv`.
- No Xiao-specific entry-timing rule is encoded yet.  Bare-minimum
  gate today is `PA bottom + h=opposing + 4-tick stop`; the full
  method likely adds IV-regime gating, intraday confirmation and a
  prescriptive ladder rule — none of these exist in code.

If the user has a more authoritative reading, the "open questions"
section is where corrections should land.

## 2. Current state

### Data we have

| Layer | Coverage | Where |
|-------|----------|-------|
| CN option daily bars | SHFE au/ag/cu/rb (~3 078 contracts), thin DCE/CZCE (44 contracts) | `data/quant/{SHFE,DCE,CZCE}/<contract>/daily.parquet` |
| CN option intraday | au/ag 15min + 60min JSON; uneven date coverage | `src/data/options/cn/{ag,au,...}/*_{15,60}min.json` |
| US option daily | empty (placeholder dirs only) | `src/data/options/{spy,qqq,...}/` |
| Payoff matrix | 3 111 CN signals × OTM ranks × h5/h10/h20 | `DERIVED_ROOT/.../option_payoffs_parquet_cn_v2.csv` |
| Contract metadata | strike / expiry / portfolio per contract | `data/quant/_contracts/{EXCHANGE}.parquet` |

Critical gaps still open per `src/docs/data-fill-request.md`:
**OTM rank** is null for 45 % of rows (P0); **h20** has n=6 for the
headline bucket (P1); CN_AGRI has 44 vs CN_METAL 3 078 contracts (P1).

### Logic we have

- `cn_ag_selector.py` — picks the 20-60 DTE contract month, generates
  3 OTM call dicts at +1.71/+2.93/+4.14 %, snaps strike to the 100-yuan
  grid, optionally tags the rank closest to a MM target.  Includes a
  BS IV solver (`estimate_iv`), JSON price lookup, and a live-fetch
  wrapper (`enrich_with_iv` → `tqsdk_feed`).
- `cn_au_selector.py` — au twin: 8-yuan grid, 25-DTE floor, last-
  trading-day-of-month expiry.  IV solver is copy-pasted.
- `tqsdk_feed.py` — batch live price fetch; all-None when creds absent.

### Integration today

`score_today.py` calls `select_otm_calls{,_au}` + `enrich_with_iv{,_au}`
in four scan loops (lines 533/543, 583/587, 697/701, 844/852).  Each
site duplicates: filter on `cn_metal_futures` + `_ag`/`_au` suffix +
`score ≥ 3` → selector → enrich → store under `rec["options_calls"]`.

**Where this falls short of Xiao timing**:

- No entry-timing **gate** — any score ≥ 3 gets options annotated; we
  never check IV regime, 15min confirmation, or term-structure shape.
- No **stop layer** — selectors emit strikes; nobody computes the
  4-tick underlying-stop level or wires it into `invalidation_level`.
- No **ladder rule** — we always emit all three ranks; the user picks
  at execution time.  Xiao's method is prescriptive (typically a
  1-2 rank split sized to MM).
- No **exit/duration logic** — T=17, TP1=+1R, TP2=+2R lives only in
  the legacy backtest, not in `engine/`.
- **au/ag only** — cu, rb, m, i, sr all have liquid options + PA
  signals and currently get nothing.

## 3. Gap analysis

### Missing data

- **IV history** — option daily closes exist, but no per-contract IV
  time series is stored.  Need `data/derived/options_iv/<contract>.parquet`
  produced by scanning `_contracts` + daily premiums through the BS
  solver (or Black-76; see below).
- **Underlying realised vol / HV20** — trivial to compute from existing
  bars, just not stored.
- **Term structure** — front- vs back-month IV requires loading 2
  contracts per signal day; data is there, no join logic yet.
- **CN_AGRI option coverage** (per `data-fill-request.md` §3) — gates
  the CZCE/DCE arm entirely.

### Missing logic

- **IV regime gate** — IV-rank over 252 trading days; reject when
  rank > ~0.70 (premium too rich).  Xiao buys cheaper time.
- **Prescriptive ladder rule** — e.g. rank 1 (Δ≈0.40) for primary
  swing, rank 2 (Δ≈0.25) as MM stretch, never rank 3+ unless MM ≥
  rank-3 OTM %.  Selectors today are non-prescriptive.
- **4-tick stop layer** wired into `invalidation_level`.  Tick-size
  table already exists in `analyze_options_payoff.TICK_SIZES`; should
  move to `engine/options/tick_sizes.py` for reuse, plus a
  `compute_underlying_stop(entry, ticks=4)` helper.
- **Entry-window logic** — we annotate the signal bar; Xiao supports
  waiting for intraday confirmation (15min h=opposing).  Score_today
  already builds `pa_15m_confirmed` as an info flag — promote to entry
  trigger.
- **Exit/scope module** — T=17 max-hold, TP1=+1R/TP2=+2R is in the
  legacy backtest but not in `engine/`.

### Missing infrastructure

- **Greek surface** (Δ, Γ, Θ, Vega) — one differentiation away from
  the existing BS code; needed for delta-target ladder selection and
  theta-aware exits.
- **Black-76 for futures options** — legacy backtest used Black, not
  BS, because SHFE options are European on the futures.  Current
  `_bs_call_price` treats futures price as spot with zero carry —
  passable short-DTE, inexact at 90+ DTE.  Rebuild and replace both
  copy-pasted `_bs_call_price` definitions.
- **Unified `BaseOTMSelector`** — `cn_ag_selector` and `cn_au_selector`
  are ~80 % duplicated.  Parameterise by `(strike_step, dte_floor,
  expiry_rule)` to unblock cu/rb/m/i in a day instead of per-symbol
  rewrites.

## 4. Minimal viable design

Three modules, each a clean addition to `engine/options/`; the wiring
into `score_today` is small.

### Module 1: `engine/options/iv_regime.py`

```python
def iv_rank(
    contract_sym: str,
    signal_date: date,
    lookback_days: int = 252,
    storage: ParquetStorage,
) -> float | None
def iv_percentile_gate(
    rank: float | None,
    max_rank: float = 0.70,
) -> bool
```

Loads the contract's daily premium history, runs BS back-out per
bar, returns IV percentile rank over the lookback.  Gate returns True
when premium is cheap enough to buy.  Data already in
`data/quant/<exchange>/<contract>/daily.parquet`; no new fetch.

### Module 2: `engine/options/xiao_entry.py`

```python
@dataclass
class XiaoEntrySignal:
    signal_date: date
    underlying: str
    underlying_close: float
    chosen_rank: int           # 1 or 2; never 3 unless mm forces it
    contract_sym: str
    option_price: float | None
    iv: float | None
    iv_rank: float | None
    stop_level: float          # underlying price = entry - 4*tick
    mm_target_pct: float | None
    confirm_source: str        # "daily-only" | "15min" | "60min"
    rejected_reason: str | None  # filled when gate fails

def build_xiao_entry(
    pa_signal: PASignal | DivSignal,
    bars: pd.DataFrame,
    h_bars_60: pd.DataFrame,
    bars_15: pd.DataFrame | None,
    storage: ParquetStorage,
) -> XiaoEntrySignal | None
```

Pipeline:
1.  Underlying signal must be PA H2 bottom + `higher_relation == opposing`
    (already the validated bucket).
2.  IV-regime gate via Module 1 (skip if IV-rank > 0.70).
3.  Pick contract (existing `select_otm_calls` per underlying).
4.  Choose rank: prefer rank 1; if `mm_target_pct` matches rank 2's
    OTM%, use rank 2; never rank 3.
5.  Compute `stop_level = pa_close - 4 * tick_size(underlying)`.
6.  Optional 15min confirmation flag using `pa_15m_confirmed` logic
    already in `score_today.py`.
7.  Return a single decisional record (not a list of 3 candidates).

### Module 3: `engine/options/xiao_exit.py`

```python
@dataclass
class XiaoExitPlan:
    tp1_premium: float       # premium at underlying = entry + 1R
    tp2_premium: float       # premium at underlying = entry + 2R
    max_hold_days: int       # default 17
    stop_underlying: float   # from Module 2

def project_exit_levels(
    entry: XiaoEntrySignal,
    r_unit: float,           # underlying ATR or PA structural-stop distance
) -> XiaoExitPlan
```

Uses Black-76 to forward-project option price at TP1/TP2 underlying
levels assuming flat IV.  Pure analytic; no extra data.

### Integration with PA H2 bottoms

Replace the per-symbol `_AG_SYMBOL_SUFFIX/_AU_SYMBOL_SUFFIX` ladder in
`score_today.py`'s PA H2 loop with a single call:

```python
if instrument_class == "cn_metal_futures" and pa_score >= _OPTIONS_MIN_SCORE:
    xiao = build_xiao_entry(pa_sig, bars, h_bars, _m15_bars, storage)
    if xiao and xiao.rejected_reason is None:
        pa_rec["xiao_entry"] = asdict(xiao)
        pa_rec["xiao_exit"]  = asdict(project_exit_levels(xiao, atr_r))
        pa_rec["invalidation_level"] = xiao.stop_level
```

This collapses ~30 lines of per-symbol special-casing across four
scan loops into one call site.  PA H2 bottoms become the canonical
underlying entry that Xiao sits atop (rather than today's
"everything ≥ score 3 with the right suffix").

### Scope: 1 week vs 1 month

**1-week (recommended)**: Modules 1+2 only, au+ag.  Reuse existing
selectors as the strike-picker.  No Black-76; no Greeks.  Output:
`xiao_entry` field on PA H2 records, IV-gated, with a 4-tick
`stop_level`.  Validation = one notebook re-running
`option_payoffs_parquet_cn_v2.csv` filtered on the new gate.

**1-month**: add Module 3 + Black-76 + Greek surface + cu/rb/m/i
extensions via `BaseOTMSelector`.  Also resolve the P0/P1 data items
in `data-fill-request.md`.  Output: full Xiao loop with TP ladder
projection and live IV-rank for any CN metal/agri PA bottom.

## 5. Open questions for the user

1.  **IV-rank cutoff.**  Is 70 % the right threshold?  Some versions
    of the framework use 50 % or compare front-back IV slope instead
    of absolute rank.  Need a citation or empirical sweep.
2.  **Ladder size and split.**  When Xiao says "买阶梯", is the
    canonical split 1 contract of rank 1 + 1 contract of rank 2, or
    weighted to MM?  Current selectors emit 3 ranks unweighted.
3.  **15min confirmation: required or optional?**  Backtest shows
    confirmed F3 = +0.682 R vs unconfirmed +0.081 R for CN_METAL.
    Should Xiao entry **require** 15min confirm (lose ~60 % of fires
    but lift EV) or just annotate?
4.  **Top signals.**  Legacy report cautions against trading top +
    h=opposing without n≥50 confirmation.  Do we wire Xiao puts into
    PA tops at all, or strictly long calls on PA H2 bottoms?
5.  **Live IV source.**  TqSdk gives premium; we back-out IV via BS.
    Is that good enough, or do we want to integrate exchange IV
    publish (SHFE publishes implied vol for ag/au options) as a
    second source for cross-check?

---

Once items 1-5 are answered, Module 1 + Module 2 + the score_today
patch is a ~1-week build with no new data dependency beyond what's
already in `data/quant/SHFE/`.  Modules 3 + Black-76 + non-ag/au
extensions are the next stretch and pair naturally with the P0/P1
data-fill items in `src/docs/data-fill-request.md`.
