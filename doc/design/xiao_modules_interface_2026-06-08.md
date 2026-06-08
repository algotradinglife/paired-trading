# Xiao Modules — Interface Specification

**Date**: 2026-06-08 · **Status**: design draft (no code yet) · **Companion to**:
`xiao_options_timing_design_2026-06-08.md`

The companion memo assumed single-architecture α (underlying-only) and
single-direction (calls on bottoms).  The user's 2026-06-08 strategic
decisions shift the design:

1. IV gate raised 0.70 → **0.90**; mid-IV is the sweet spot, no gate
   between 0.30–0.70.
2. Ladder defaults to rank **2**, liquidity-driven step-out to rank
   3 or 4 if `vol < 100 OR oi < 500`.
3. 15min confirmation **required** for CN_METAL only; annotation
   elsewhere.
4. **Puts are MVP**, not v2.  Calls on bottoms and puts on tops are
   symmetric; CN market is "more long short than long".
5. Architecture is **hybrid α / β**:
     - α (underlying ambush): PA H2 + divergence on underlying →
       ambush record.
     - β (option-K-line entry): watch chosen contract's own K-line
       for an H2 entry pattern within N days.
   Direction synthesises four sources — PA phase, multi-TF DIF,
   Context A/B1, divergence — into `long_call` / `long_put` / `skip`.

This memo specifies four modules — DIR, IV, ENT, EXIT — at the level
of dataclasses, signatures, pseudocode, open questions, and slot-in
locations in `score_today.py`.

---

## Module DIR — `engine/divergence/pa_direction_assessment.py` (NEW)

### Purpose

Replace "is `h_rel == opposing`?" with a multi-source synthesiser
that emits `long_call`, `long_put`, or `skip` plus a per-source
rationale.

### Dataclasses

```python
from dataclasses import dataclass
from typing import Literal

Direction = Literal["long_call", "long_put", "skip"]
SourceKey = Literal["structure", "multi_tf", "context", "divergence"]
SourceVote = Literal["long_call", "long_put", "neutral", "block"]

@dataclass
class DirectionSource:
    key:     SourceKey
    vote:    SourceVote
    weight:  float          # default 0.25 each; see open Q-1
    detail:  dict           # raw values (phase=BEAR, dif=-0.012, ...)

@dataclass
class DirectionVerdict:
    direction:   Direction
    confidence:  float            # [0, 1], sum of supporting weights
    sources:     list[DirectionSource]   # always four entries
    rationale:   str              # one-line summary
    bar_idx:     int
    timestamp:   "pd.Timestamp"
```

### Signature

```python
def assess_direction(
    bars:            pd.DataFrame,            # daily OHLCV underlying
    htf_bars:        pd.DataFrame | None,     # 60min (US) / 4h (CN)
    context_bars:    pd.DataFrame,            # alias for bars
    bar_idx:         int,
    *,
    ambush_pattern:  Literal["h2_bottom", "h2_top"],
    divergence_flag: bool = False,
    swing_context:   pd.DataFrame | None = None,
) -> DirectionVerdict
```

### Algorithm (pseudocode)

```
1. STRUCTURE  via PAStructureDetector().detect(bars, up_to_idx=bar_idx).phase
   h2_bottom: BULL→long_call, TR/TR_FORMING→long_call, BEAR→block, else→neutral
   h2_top   : BEAR→long_put , TR/TR_FORMING→long_put , BULL→block, else→neutral

2. MULTI_TF  via _compute_htf_dif(htf_bars) at bar_idx
   h2_bottom: dif>0→long_call, dif<0 AND struct=BEAR→long_put, else→neutral
   h2_top   : dif<0→long_put , dif>0 AND struct=BULL→long_call, else→neutral

3. CONTEXT  via classify_context(bars, bar_idx, macd_df, ema20, ema60)
   h2_bottom: A or B1 → long_call, else → neutral
   h2_top   : (top-side context not defined — see open Q-2)

4. DIVERGENCE  caller-supplied flag from PA-native divergence on underlying
   h2_bottom + flag → long_call; h2_top + flag → long_put; else → neutral

5. SYNTHESIS
   if any source votes "block":  direction="skip", confidence=0
   call_score = sum(weights where vote=="long_call")
   put_score  = sum(weights where vote=="long_put")
   if max(call_score, put_score) < 0.40 → direction="skip"
   else                                  → direction=argmax, confidence=max
```

### Consumes / doesn't have

Uses: bars, htf_bars, swing_context, PAStructureDetector, MACD `dif`,
classify_context, external `divergence_flag`.

Missing today: top-side context classifier
(`pa_context_classifier.py` is bottom-only) — open Q-2.

### Slot in score_today

Replace the `pa_weight + h_rel == opposing` gate at
`scripts/score_today.py:783-801` with a single `assess_direction(...)`
call.  `verdict.direction` becomes a new record field; `score` is
derived from `verdict.confidence` bucketed to 2/3/4.

---

## Module IV — `engine/options/iv_regime.py` (NEW)

### Purpose

IV-rank per contract over 252-day lookback; gate at 0.90.

### Signatures

```python
def iv_rank(
    contract_sym:  str,
    signal_date:   date,
    lookback_days: int = 252,
    storage:       "ParquetStorage",
) -> float | None
    """IV percentile rank in [0, 1].

    Loads daily premiums from data/quant/<exchange>/<contract>/daily.parquet,
    BS-back-outs IV per bar (Newton-Raphson, 50 iters), ranks signal_date
    IV against the lookback distribution.

    Returns None if < 60 valid IV samples in the window.  Caller should
    treat None as 'no gate', not 'blocked'.
    """

def iv_regime_gate(
    rank:     float | None,
    max_rank: float = 0.90,
) -> bool
    """True passes / False blocked.

    rank is None      → True   (insufficient history, don't block)
    rank > max_rank   → False
    otherwise         → True
    """
```

### Consumes / doesn't have

Uses: per-contract daily parquet (already on disk).  BS solver lives
in `engine/options/cn_ag_selector.py::estimate_iv` — extract to
`engine/options/bs.py` so selectors and `iv_regime` share one impl.

Missing today: SHFE-published implied vol time-series (future
cross-check, not MVP).  Black-76 deferred — BS approximation good
enough at 20–60 DTE per companion memo.

### Slot in score_today

Called once per ambush after Module DIR returns non-skip.  Blocks
emission on `gate == False`; otherwise records `iv_rank` field.

---

## Module ENT — `engine/options/xiao_entry.py` (NEW, rewrite of memo §4.2)

### Purpose

Two-phase entry with α / β split and 2 → 3 → 4 liquidity ladder.

### Dataclasses

```python
@dataclass
class OptionCandidate:
    rank:           int           # 1..4 (rank=2 is default home)
    strike:         float
    otm_pct:        float
    contract_sym:   str
    expiry_date:    date
    days_to_expiry: int
    vol:            int | None
    oi:             int | None
    is_liquid:      bool          # vol >= 100 AND oi >= 500
    is_mm_strike:   bool

@dataclass
class XiaoAmbushRecord:
    """α-layer output."""
    ambush_date:        date
    direction:          Direction       # long_call | long_put
    underlying_sym:     str
    underlying_close:   float
    iv_rank:            float | None
    direction_verdict:  DirectionVerdict
    candidates:         list[OptionCandidate]   # ranks 2,3,4 (rank 1 flagged 'aggressive')
    chosen_rank:        int             # 2 default; step-out to 3/4
    rejected_reason:    str | None      # "all_thin" | "iv_extreme" | None
    expires_at:         date            # ambush_date + N (open Q-3)

@dataclass
class XiaoEntrySignal:
    """β-layer output."""
    ambush_date:           date
    entry_date:            date
    direction:             Direction
    underlying_sym:        str
    underlying_close:      float        # at entry_date
    option_contract:       str
    option_close_at_entry: float
    iv_rank:               float | None
    mm_target_pct:         float | None
    stop_underlying:       float        # entry ± 4*tick (sign by direction)
    confirm_source:        str          # "option_h2_bottom" | "option_h2_top" | "daily_only"
    sources:               dict         # serialised DirectionVerdict.sources
    rationale:             str
```

### Signatures

```python
def build_xiao_ambush(
    direction_verdict: DirectionVerdict,
    bars:              pd.DataFrame,
    storage:           "ParquetStorage",
    underlying_sym:    str,
    *,
    iv_rank_value:     float | None,
    liquidity_min_vol: int = 100,
    liquidity_min_oi:  int = 500,
    watch_window_days: int = 5,         # open Q-3
) -> XiaoAmbushRecord | None
    """Phase α — emit ambush record or None if iv_gate / liquidity reject."""

def watch_option_for_entry(
    ambush:      XiaoAmbushRecord,
    option_bars: pd.DataFrame,           # chosen contract's daily K-line
    as_of:       date,
) -> XiaoEntrySignal | None
    """Phase β — scan option bars from ambush_date+1 to as_of for an H2
    pattern (PABottomDetector for long_call, PATopDetector for long_put)
    using relaxed parameters (open Q-4)."""
```

### Algorithm (pseudocode)

```
Phase α — build_xiao_ambush:
  if verdict.direction == "skip":            return None
  if not iv_regime_gate(iv_rank_value):
      return XiaoAmbushRecord(rejected_reason="iv_extreme", ...)

  if verdict.direction == "long_call":
      raw = select_otm_calls(underlying_close, ambush_date,
                             n_strikes=4, mm_target_pct=mm_pct)
  else:
      raw = select_otm_puts(underlying_close, ambush_date,
                            n_strikes=4, mm_target_pct=mm_pct)
                            # select_otm_puts does NOT exist yet — open Q-5

  candidates = [enrich_with_liquidity(c, storage) for c in raw]
  # load contract daily, take vol/OI on ambush_date

  chosen = pick_rank_2_or_step_out(candidates, min_vol=100, min_oi=500)
  # rank 2 if liquid, else rank 3 if liquid, else rank 4 if liquid,
  # else None → "all_thin"

  return XiaoAmbushRecord(
      chosen_rank=chosen.rank if chosen else None,
      rejected_reason="all_thin" if not chosen else None,
      expires_at=ambush_date + watch_window_days,
      ...)

Phase β — watch_option_for_entry:
  if direction == "long_call":
      det = PABottomDetector(min_h_legs=1, min_quality=0.2,
                             ema_threshold=0.0, min_gap=1)
  else:
      det = PATopDetector(min_l_legs=1, min_quality=0.2,
                          ema_threshold=0.0, min_gap=1)
  for s in det.scan(option_bars):
      if ambush.ambush_date < s.timestamp.date() <= as_of:
          return XiaoEntrySignal(
              entry_date=s.timestamp.date(),
              option_close_at_entry=option_bars.loc[s.bar_idx, "close"],
              stop_underlying=compute_4tick_stop(...),
              confirm_source=f"option_{s.pattern}",
              ...)
  return None
```

### Consumes / doesn't have

Uses: DirectionVerdict, OptionCandidate from selectors, contract
daily parquet vol/OI, tick-size table, MM target.

Missing today:
- `select_otm_puts(...)` — symmetric mirror of `select_otm_calls`,
  no code yet (open Q-5).
- Tested PA detector parameter set for option-contract K-lines —
  underlying tuning (0.3 quality) likely too strict (open Q-4).
- vol / OI fields on `OptionCandidate` — `select_otm_calls` returns
  strike+expiry+contract_sym only.  Needs an `enrich_with_liquidity()`
  step that loads each contract's `daily.parquet` vol + open_interest.

### Slot in score_today

The four scan loops (`scripts/score_today.py:671, 690, 729, 844`)
each carry their own `select_otm_calls + enrich_with_iv` pattern.
Replace with one block per loop:

```
verdict = assess_direction(bars, h_bars, bars, sig.bar_idx,
                           ambush_pattern=sig.pattern,
                           divergence_flag=has_divergence)
if verdict.direction == "skip":  continue
ambush = build_xiao_ambush(verdict, bars, storage, sym,
                           iv_rank_value=iv_rank(...))
if ambush is None or ambush.rejected_reason:  continue
rec["xiao_ambush"] = asdict(ambush)
# β-phase runs in a separate daily job over open ambushes — open Q-6
```

New record fields: `direction`, `direction_verdict`, `iv_rank`,
`xiao_ambush`, `xiao_ambush.chosen_rank`, `xiao_ambush.candidates`,
`xiao_ambush.rejected_reason`.  `options_calls` kept for one release
for diff-ability.

**New emission for tops**: mirror the PA H2 bottom block with
`PATopDetector` + `assess_direction(..., ambush_pattern="h2_top")`.
`PATopDetector.policy_weight()` currently returns 0.0 — DIR overrides
this (see What This Design Doesn't Cover §4).

---

## Module EXIT — `engine/options/xiao_exit.py` (NEW, sketch only)

### Purpose

Forward-project option premium at underlying TP1 (+1R) / TP2 (+2R)
via Black-76.  **Informational for v1.**  Actual exit decisions
remain with the existing underlying TP1/TP2 framework.

### Dataclass & signature

```python
@dataclass
class XiaoExitPlan:
    tp1_underlying:    float
    tp1_premium_proj:  float
    tp2_underlying:    float
    tp2_premium_proj:  float
    stop_underlying:   float
    max_hold_days:     int = 17

def project_exit_levels(
    entry:  XiaoEntrySignal,
    r_unit: float,            # underlying ATR or PA structural-stop dist
) -> XiaoExitPlan
```

Lowest priority in MVP — can `raise NotImplementedError` for first
release.

---

## Integration with `score_today.py`

| Loop block                       | Change                                                                                                                                                             |
|----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| PA H2 emit (≈ lines 780–854)     | Replace `pa_weight = PABottomDetector.policy_weight(...)` early-out with `verdict = assess_direction(...)`.  Derive `pa_score` from `verdict.confidence` (2/3/4). |
| Per-loop ladder (671/690/729/844) | Delete four duplicated `select_otm_calls/_au + enrich_with_iv` blocks.  Replace with one `build_xiao_ambush(...)` call handling both directions.                  |
| New record fields                 | `direction`, `direction_verdict`, `iv_rank`, `xiao_ambush.{chosen_rank, candidates, rejected_reason}`.                                                              |
| Deprecation                       | `options_calls` kept for one release, then removed.                                                                                                                 |
| New: tops emission                | Add a PA H2 top scan block mirroring the bottom block; both feed `assess_direction`.                                                                                |

The β-layer (option-K-line entry) does **not** run inside
`score_today.py`'s signal-day loop.  See open Q-6.

---

## Open implementation questions

1. **Equal weights across four direction sources?**  Pseudocode uses
   0.25 each.  Alternative: structure 0.35 / multi_tf 0.25 / divergence
   0.25 / context 0.15 (structure dominates per legacy CN_METAL
   backtest).  Settle by sweep over historical PA records: which
   weighting cleanest-splits subsequent 20-day return into
   long_call vs long_put buckets.

2. **Top-side context classifier.**  `pa_context_classifier.py` is
   bottom-only.  Options: (a) add A_top / B1_top mirrors, (b) drop
   the context source for tops and renormalise weights, (c) reuse
   bottom classifier and negate.  (a) cleanest but scope; (b)
   fastest for MVP.

3. **N for the phase-β watch window.**  Companion memo uses
   T_max_hold = 17 trading days for the *trade*; the *ambush* watch
   window is separate.  Proposal: 5 trading days; if no entry
   pattern, underlying has likely already moved.  Needs a backtest
   on PA records: at what lag does the post-ambush option H2
   typically land?

4. **Relaxed PA detector parameters on option K-lines?**  Option
   contracts have lower liquidity, gappier opens, delta-decay bias.
   Pseudocode uses `min_h_legs=1, min_quality=0.2` vs underlying
   `2, 0.3`.  Minimal experiment before implementation:
     - Take 50 historical CN_METAL PA H2 ambushes
     - Load rank-2 contract's daily K-line over 5-day post-ambush window
     - Run PABottomDetector at (2, 0.3), (1, 0.2), (1, 0.1)
     - Tally confirm rate, lag, post-confirm 5-day return distribution
   Decide between (1, 0.2) and (2, 0.3) by post-confirm return.

5. **`select_otm_puts` does not exist.**  Both selectors emit calls
   only.  Need symmetric puts selector — preferred: `BaseOTMSelector`
   parameterised by `option_type ∈ {C, P}`.  Strike grid, expiry,
   IV solver identical; only OTM direction (strike < underlying)
   differs.

6. **Where does Phase β run?**  (a) Inside `score_today.py` loop,
   scanning forward over N days using a windowed detector — but
   `score_today` is supposed to be a `today` snapshot, not a
   forward simulator.  (b) New daily job `scan_open_ambushes.py`
   that loads ambushes from the last N days and runs β on each.
   Recommend (b); needs a small JSONL state store
   (`data/derived/xiao_ambushes/<date>.jsonl`).

7. **Option K-line bar source: daily or intraday?**  Daily exists
   in `data/quant/<exchange>/<contract>/daily.parquet`.  Intraday
   (15min/60min) only for ag/au under `src/data/options/cn/{ag,au}/`.
   MVP: daily on chosen contract.  Stretch: intraday for tighter
   entry on CN_METAL.

---

## What this design DOESN'T cover

- **Backtest harness for the β-layer.**  No script samples ambushes
  from PA history and replays option-contract bars through β.  Both
  `backtest_pa_swing.py` and `backtest_pa_us_k3.py` stop at the
  underlying signal.  A new `backtest_xiao_ambush.py` is required
  before β can be promoted from "annotation" to "decisional".

- **Live execution wiring.**  Where does ambush state live between
  Phase α and Phase β?  How does the trade desk see an open ambush?
  No persistence layer designed here — suggested but not specified:
  `data/derived/xiao_ambushes/<date>.jsonl` append-only log read by
  `scan_open_ambushes.py`.

- **Position sizing under the rank-2 vs rank-3/4 step-out.**  The
  candidate ladder may carry a different MM target than rank 2;
  sizing rules need to follow.  Today's `_position_size()` helper
  in `score_today.py` does not know about the ladder.

- **Top-side validation.**  `PATopDetector.policy_weight()` returns
  0.0 for every routing path; DIR overrides this, but a formal
  walk-forward validation pass on top-side PA emits has not been
  run.  This memo assumes parity with bottom-side — needs empirical
  check before puts go live.

- **Black-76 vs BS for IV back-out and exit projection.**  IV module
  uses BS as stand-in.  Black-76 (futures-option-native) deferred;
  expected error small at 20–60 DTE, unbounded > 90 DTE.

- **CN_AGRI coverage.**  44 contracts vs CN_METAL 3 078 per
  `data-fill-request.md`.  Modules are agnostic but liquidity
  rejection will dominate AGRI ambushes until data is filled.

---

*Once Q-1 through Q-7 have answers, DIR + IV + ENT are a one-sitting
build.  EXIT comes after.  Backtest harness and live state persistence
are separate work items.*
