# Exhaustion / Capitulation Detector — Spec Draft

**Status:** design draft, not yet implemented
**Targets:** ~30-50% of missed swings whose multi-TF state is "all-3-TF same-direction trending" at the head bar
**Motivation:** evidence from `missed_swing_state` v3 runs (with 14y deep qveris CN intraday) shows the largest single blind-spot bucket — capitulation bottoms (CN 49%, US 25-30%) and euphoria tops (US 30%, CN ~30%). MACD divergence by-design cannot fire here because each new extreme creates a new MACD reference, the comparator resets.

---

## 1. What we're trying to catch

A market state characterized by:
- All visible timeframes (D, 1h, W or D, 15m, 1h) trending the **same direction** (= "everyone's leaning the same way")
- Daily segment is **mature** (multiple cycles already played out in the trend direction)
- Then a **K-line reversal signature** prints on the daily — long wick on the trend side, body in the opposite half (Brooks "reversal bar" or 锤子/上吊线)
- Optionally amplified by volume climax (panic dump / FOMO buy)

This is the classic "everyone wrong at the extreme" pattern. Brooks calls it "second-leg failure" / "exhaustion bar". Wyckoff calls it "selling climax" / "buying climax".

The MACD divergence detector misses it because:
- Each new lower-low in the down-trend makes a new MACD low → comparator says "non-divergence, reset reference"
- After enough cycles, the divergence comparison never accumulates a valid (reference, candidate) pair
- The bar IS the turning point, but divergence needs **two** turning points to compare

## 2. Trigger conditions (all required, AND)

| # | Condition | Concrete check |
|---|---|---|
| **T1** | Daily segment is mature | `current_segment.n_completed_cycles ≥ 3` (segment has run for ≥ 3 cycle resets) |
| **T2** | Multi-TF aligned with segment direction | `higher_tf.trend_side == lower_tf.trend_side == daily.segment_direction` |
| **T3** | Candidate bar has K-line reversal signature | for bottom: `lower_wick_ratio ≥ 0.4` AND `close > (high + low) / 2`; symmetric for top |
| **T4** | Candidate bar is at segment extreme | `bar.low == min(segment.lows[-N:])` for bottom (or new segment low), symmetric for top |
| **T5** | (optional, gated by `--volume-confirm`) | `bar.volume ≥ 1.5 × trailing-20-bar mean` |

Notes:
- T1's "mature segment" threshold (3+ cycles) is an initial guess; needs OOS calibration. Range to test: 2 / 3 / 5 cycles.
- T2 is the key differentiator from divergence — divergence wants OPPOSING higher; exhaustion wants ALIGNED higher.
- T3 uses Z1 wick_ratio + Brooks reversal bar criteria. Both required to avoid noise.
- T4 prevents firing on mid-trend pullbacks — must be at a fresh extreme.
- T5 is the Brooks-style "above-average volume signal bar". Optional because not all exchanges report reliable volume on continuous contracts.

## 3. Schema impact

Two options:

**Option A — new signal `level` value** `"exhaustion"` alongside existing `intra_cycle / inter_cycle / inter_segment`:
- ✅ Consumers see it as a peer signal type
- ❌ Requires schema MINOR bump (new Literal value) and DivergenceSignal field rework (no `amplitude_side` makes sense; `reference_bar_idx` ambiguous)

**Option B — new event type, separate from `DivergenceSignal`**, surfaced through a new `ExhaustionEvent` class and a new top-level `exhaustion_events: list[ExhaustionEvent]` on `AnalysisOutput`:
- ✅ Clean separation, no DivergenceSignal contortion
- ✅ Schema MINOR bump on envelope
- ❌ Two consumer code paths

**Recommendation: B.** The "exhaustion" event has very different structure than divergence (no reference, no amplitude decay) — forcing it into DivergenceSignal would create degenerate fields. A dedicated `ExhaustionEvent` is cleaner. Schema bumps to v1.4.

### Proposed `ExhaustionEvent` fields

- `level_id: str` (e.g. `"D"`)
- `timestamp: datetime` (candidate bar close, UTC)
- `candidate_bar_idx: int`
- `direction: "top" | "bottom"`
- `segment_id: int`, `n_completed_cycles: int`, `bars_in_segment: int` (mature-segment evidence)
- `wick_ratio: float`, `body_half: "upper"|"lower"|"middle"`, `volume_ratio: float | None` (K-line evidence)
- `multi_tf_aligned: dict[str, str]` (which TFs were aligned with segment direction)
- `confidence: float ∈ [0, 1]` (combined score)
- `context_features: dict[str, float] | None` (open-ended, same convention as DivergenceSignal)

## 4. Confidence scoring

Initial linear combine (calibrate with OOS):

```
confidence = clip(0.5
                  + 0.10 × min(n_completed_cycles, 5) / 5
                  + 0.20 × (wick_ratio - 0.4) / 0.6
                  + 0.10 × multi_tf_alignment_strength
                  + 0.10 × min(volume_ratio - 1.0, 1.0)
                , 0, 1)
```

Where:
- segment maturity adds up to +0.10
- wick strength (over 0.4 threshold) adds up to +0.20
- multi-TF unanimity adds up to +0.10
- volume climax adds up to +0.10
- baseline 0.5

Total max ≈ 1.0, min ≈ 0.5 (since trigger requires baseline conditions).

**This is in-design only.** Final weights MUST come from OOS calibration (analyze_sweet_spots_pool style on real exhaustion events vs forward returns).

## 5. Validation plan (do this BEFORE wiring into policy)

1. Implement detector with permissive defaults (T1=3, T3=0.4, T5 off)
2. Re-run `missed_swing_state.py` AS-IS — but additionally tag whether the missed swing would have been caught by the new detector. This is a **recall lift** measurement on existing labels.
3. Run `analyze_sweet_spots_pool.py` with exhaustion events instead of divergence signals → get precision/EV per bucket
4. Walk-forward 3-fold on at least US + CN_COMMODITY before any production weight assignment
5. If walk-forward passes both folds at ≥+10pp uplift → graduate to `policy.exhaustion_*` rule in downstream_policies

**Pass criteria** (analogous to existing sweet-spot stability bar):
- Recall lift on missed swings ≥ +15pp across US + CN pools
- Precision ≥ 55% on captured swings
- Walk-forward stable on both fold[1] and fold[2] in at least 2 of 3 pools

## 6. Open questions for user discussion (BEFORE coding)

1. **Mature-segment threshold (T1)**: Try multiple values (2/3/5 cycles) in OOS sweep, or pick one based on Brooks intuition?
2. **Volume confirmation (T5)**: Required, optional, or per-instrument? CN futures volume is reliable; some US ETFs less so.
3. **Schema option A vs B**: Confirm B (new ExhaustionEvent class)?
4. **K-line pattern variety (T3)**: Just wick+body? Add engulfing/inside/outside as separate detectors? Start single-pattern + expand later?
5. **Multi-TF strictness (T2)**: Require ALL aligned, or 2-of-3 / weighted? CN missed-swing data showed 49% had all-3 aligned, so strict ALL captures the biggest single bucket but misses the 51% that have one-TF differ.
6. **First-pullback detector** (other big bucket per missed_swing data — first-pullback IS the inverse of exhaustion: cycle-EARLY reversal not cycle-late). Should we design both together as a "cycle-position aware" family?

---

## Rough cost & effort

- Implementation: ~1 day (new `engine/detectors/exhaustion.py`, schema v1.4 bump, build_analysis_output rewire, tests)
- OOS validation: ~1 day (extend coverage report to tag exhaustion catches, walk-forward sweep)
- Total: 2 days of focused work

Compare to potential upside: ~30-50% blind-spot coverage. If exhaustion detector catches even half of the all-3-aligned bucket cleanly, US recall could go from 7-8% → 15-20%, CN from ~10% → 25-30%. That's a meaningful step-function on the operational pipeline.
