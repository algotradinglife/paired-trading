# Output API Contract — v1.4

**Status**: stable
**Schema**: [`doc/schemas/analysis-output-1.4.schema.json`](schemas/analysis-output-1.4.schema.json) (auto-generated; run `uv run python scripts/dump_schema.py` to refresh)
**Reference implementation**: `src/engine/output/build.py::build_analysis_output`

**Changelog**:
- v1.4 (2026-05-26): added top-level `exhaustion_events: list[ExhaustionEvent]`
  field. Independent stream of trend-exhaustion reversal candidates emitted
  by `engine.divergence.exhaustion.detect_exhaustion_events`; targets the
  30–35% blind-spot bucket where all 3 TFs trend same-direction so MACD
  divergence cannot fire (see [`doc/exhaustion-detector-spec-2026-05-26.md`](exhaustion-detector-spec-2026-05-26.md)
  for the trigger spec; diagnostic source is `src/scripts/missed_swing_state.py`
  with CSV outputs in `data/review/missed_swing_state_*.csv`).
  Each event carries `confidence ∈ [0, 1]` computed in-detector; no
  PolicyDecision wrapper at v1.4 — instrument-class-specific weights will
  be added in a later minor version once OOS validation is complete.
  Default value is `[]`, so v1.0–v1.3 consumers see no behavior change.
- v1.3 (2026-05-25): added optional `context_features` dict on
  `DivergenceSignal` (nested under each `signals[*].signal`). Initial
  keys shipped (Z1+Z2 round):
    - `candidate_rejection_wick_ratio` ∈ [0, 1] — proportion of the
      price-extreme bar's range occupied by the signal-direction-side
      wick (upper for tops, lower for bottoms).
    - `invalidation_level` — raw price; setup fails if broken in
      signal direction (extreme bar's high for tops, low for bottoms).
      Direct input to tip-stop placement.
    - `prior_swing_distance_pct` — signed percent distance from
      reference extreme to candidate extreme; direct input to
      measured-move target projection. Key absent when reference is
      unavailable.
    - `candidate_volume_ratio` — extreme bar's volume / trailing-20-bar
      mean. Above 1.0 = above-average volume. Brooks-style "signal bar
      with above-average volume" filter (highest-quality reversals).
      Key absent when volume column missing or lookback underflow.
  Open-ended numeric dict; future keys may extend without further
  version bump as long as they remain numeric and additive. **Scope
  note**: this is the first field family that steps outside pure Song
  MACD theory into candle geometry / price-action; consumers who want
  to stay Song-pure can ignore the dict.
- v1.2 (2026-05-24): added `instrument_class` field at envelope root.
  Producer defaults to `"us_equity"`; `"cn_futures"` available. Affects
  BOTH direction_gate calibration (detection) and policy weights.
- v1.1 (2026-05-23): added `topology` field at envelope root. Producer
  defaults to `"A"` for backward compatibility with v1.0 consumers; `"B"`
  available for options-strategy callers.
- v1.0: initial release.

**Doc revisions (no schema change)**:
- 2026-05-24 (later): `cn_futures` rules table refreshed to include
  `CN-top-supp-fade` (R4 review landed); CN description updated to
  reflect that B-topology multi-TF context is now wired up for CN
  signals via TqSdk 60min/15min data.

This document is the contract between the **paired-trading analysis engine** and any downstream consumer (trading systems, dashboards, alerts, backtests). It tells you exactly what fields to depend on, what may change, and how versioning works.

---

## 1. What you call

```python
from engine.output.build import build_analysis_output

bars = {
    "D":   pd.DataFrame(...),   # required — primary level
    "1h":  pd.DataFrame(...),   # used by topology A as lower / topology B as higher
    "W":   pd.DataFrame(...),   # used by topology A as higher
    "15m": pd.DataFrame(...),   # used by topology B as lower
}
# Each DataFrame must have columns: time, open, high, low, close, volume, timestamp (pd.Timestamp UTC)

# US stock strategy (default — topology A + us_equity)
out_stock = build_analysis_output("SPY", bars)

# US options strategy (topology B + us_equity)
out_options = build_analysis_output("SPY", bars, context_topology="B")

# CN futures strategy (CN-calibrated direction_gate + policy)
out_cn = build_analysis_output("IF0", {"D": cn_daily_bars},
                              instrument_class="cn_futures")

json_str = out_stock.model_dump_json(indent=2)
```

The function returns an `AnalysisOutput` pydantic model. Dump with `.model_dump_json()` for downstream transport.

### Choosing a topology

| Topology | Levels | Default for | Calibrated by |
|---|---|---|---|
| **A** (default) | D primary + 1h lower + W higher | Stock / ETF linear strategies | Codex Rounds 1 + 2 (F1-F8 weight tuning) |
| **B** | D primary + 15m lower + 1h higher | Defined-risk options strategies with limit-order entry + scaled exit | `doc/experiment-b-topology-2026-05-23.md` |

The choice only affects the `multi_tf_context` tags attached to signals; the
**same daily signals are detected** by both topologies. Direction prediction
accuracy is what differs by sub-bucket:

- A topology surfaces `bottom + leading + opposing` (F2) and
  `top + leading + opposing` (F4) as actionable buckets.
- B topology surfaces `top + higher_opposing` (60min counter-trend) as a
  high-direction-accuracy top bucket (63.6% stock-direction accuracy on
  validation, vs A's 31.2% baseline for tops).

If unsure, use A. B requires the consumer to handle theta + bid/ask via
execution strategy.

---

## 2. Top-level envelope

```jsonc
{
  "schema_version": "1.4",
  "symbol": "SPY",
  "system_ts": "2026-05-22T23:25:41.716892Z",  // UTC, when analysis ran
  "topology": "A",                              // "A" (stock) | "B" (options) — added in v1.1
  "instrument_class": "us_equity",              // "us_equity" | "cn_futures" — added in v1.2

  "window": {
    "window_start": "2021-05-24T20:00:00Z",  // earliest input bar across all levels
    "window_end":   "2026-05-22T20:00:00Z",
    "bars_per_level": { "D": 1256, "1h": 20064, "W": 261 }
  },

  "cross_level":         { /* CrossLevelSummaryDTO — see §4 */ },
  "levels":              [ /* LevelFusionSummary per TF — see §5 */ ],
  "signals":             [ /* SignalOutput list — see §6 */ ],
  "exhaustion_events":   [ /* ExhaustionEvent list — see §6.3, added in v1.4 */ ]
}
```

---

## 3. Versioning

`schema_version` follows SemVer:

| Bump | Meaning | Consumer impact |
|---|---|---|
| MAJOR (1.x → 2.x) | Field renamed / removed / re-typed | Must update consumer code; do not auto-accept |
| MINOR (1.0 → 1.1) | New optional fields added | Existing code keeps working; new fields silently ignored if unknown |
| PATCH | Doc fixes, no schema change | Transparent |

**What this engine promises** for a v1.x output:
- All v1.0 fields will continue to exist at the same path.
- Field types do not change (e.g. `signals[].signal.confidence` stays `float`).
- New optional fields may appear (e.g. `multi_tf_context` may gain new sub-keys).

**What downstream should do** for forward compatibility:
- Read by field name, not field position.
- Tolerate unknown sub-keys in `multi_tf_context` and `strategy_hints` (these are intentionally extensible).
- Validate `schema_version` matches your major version; warn (don't crash) on minor version skew.

---

## 4. `cross_level` — current cross-TF synthesis

```jsonc
{
  "alignment_strength": 0.67,           // [0,1] fraction of levels agreeing with dominant
  "dominant_trend": "bullish",          // "bullish" | "bearish" | "mixed"
  "primary_label": "near_zero_axis@1h", // strongest active label, format "<label>@<level>"
  "primary_confidence": 0.958,          // confidence of the primary_label
  "secondary_labels": [                 // next up to 5 labels by confidence
    ["high_position@D", 0.804],
    ["zero_stick@1h",   0.735]
  ]
}
```

**Use this** when you want a one-line "what's the market doing right now" view across all loaded timeframes.

`primary_label` is filtered to recent signals only (per-TF recency window: D=45 days, 1h=21 days, W=180 days). A stale 2021 signal will not appear here.

---

## 5. `levels` — per-TF state snapshots

One entry per timeframe in `bars_per_level`. Each entry (type `LevelFusionSummary`):

```jsonc
{
  "level_id": "D",                     // "1h" | "D" | "W" | ...
  "timestamp": "2026-05-22T20:00:00Z", // timestamp of the last bar at this level
  "trend_side": "bullish",             // "bullish" | "bearish" | "transition"
  "close": 738.80,
  "dif": 12.202,
  "dea": 13.490,
  "hist": -1.288,
  "ema52": 692.41,
  "form_confidences_local": { "high_position": 0.791, ... },  // per-level form scores
  "form_confidences_fused": { "high_position": 0.804, ... },  // after cross-TF propagation
  "sub_level": "1h",                   // adjacent lower TF in topology (or null)
  "super_level": "W",                  // adjacent higher TF (or null)
  "cycle_state": "in_cycle",           // "at_zero" | "in_cycle" | "completed"
  "segment_direction": "up",           // "up" | "down" | "none"
  "hidden_subtype": "none",            // "void" | "axis_kiss" | "axis_grip" | "none"
  "near_zero_perfect": false
}
```

**Use this** for indicator-style consumers (chart overlays, dashboards) that need raw state per TF.

`form_confidences_fused` is the version to use if you want cross-TF-informed confidence; `form_confidences_local` is the un-propagated baseline.

---

## 6. `signals` — divergence events with applied policy

List of `SignalOutput`. Sorted by `signal.candidate_bar_idx` ascending. Each entry:

```jsonc
{
  "signal": { /* DivergenceSignal — see §6.1 */ },
  "policy": { /* PolicyDecisionDTO — see §6.2 */ }
}
```

### 6.1 `signal` (DivergenceSignal)

```jsonc
{
  "level": "intra_cycle",           // "intra_cycle" | "inter_cycle" | "inter_segment"
  "subtype": "weakness",            // "standard" | "weakness" | "hidden"
  "direction": "bottom",            // "top" | "bottom"

  "level_id": "D",                  // which TF emitted (matches keys in `levels`)
  "timestamp": "2026-04-15T20:00:00Z",  // when the candidate event closed
  "candidate_bar_idx": 1198,        // positional index in primary_bars
  "reference_bar_idx": 1180,        // positional index of the reference event

  "container_type": "heap",         // "heap" | "cycle" | "segment"
  "container_segment_id": 14,
  "reference_id": 22,               // heap_id / cycle_id / segment_id
  "candidate_id": 24,

  "price_side": {
    "reference_value": 559.21,
    "candidate_value": 540.50,
    "is_new_extreme": true
  },
  "amplitude_side": {
    "reference_value": 8.31,
    "candidate_value": 4.92,
    "decay_ratio": 0.408
  },

  "confidence": 0.594,              // post-direction_gate confidence ∈ [0,1]
  "is_continuous_gap": false,       // for heap-level only; null for higher levels

  "multi_tf_context": {             // optional, present if context was attached
    "lower_tf_level_id": "1h",
    "lower_tf_side": "bullish",     // "bullish" | "bearish" | "transition"
    "lower_tf_cycle_state": "in_cycle",
    "lower_relation": "lagging",    // "lagging" | "leading" | "pivoting"
    "relation": "lagging",          // back-compat alias of lower_relation (will be removed in 2.0)
    "higher_tf_level_id": "W",
    "higher_tf_side": "bearish",
    "higher_tf_cycle_state": "in_cycle",
    "higher_relation": "opposing"   // "supporting" | "opposing" | "neutral"
  },

  "context_features": {             // optional, added in v1.3; null if detector couldn't compute
    "candidate_rejection_wick_ratio": 0.42,    // [0,1] — wick proportion on signal side
    "invalidation_level": 738.5,               // raw price; setup fails if broken in signal direction
    "prior_swing_distance_pct": 4.8,           // signed % from reference to candidate extreme
    "candidate_volume_ratio": 1.85             // extreme bar volume / trailing-20-bar mean
  }
}
```

**Field semantics**:
- `confidence` is **already gated** by `direction_gate`. It accounts for the calibrated top/bottom asymmetry. You can use it directly without re-applying the gate.
- `multi_tf_context` is optional. When present, semantics are described in `engine/divergence/multi_tf_context.py` docstring.
- `multi_tf_context.relation` is a back-compat key duplicating `lower_relation`. **New code should read `lower_relation`.** The `relation` key will be removed in schema 2.0.
- `context_features` is optional (added v1.3). Open-ended numeric dict carrying candle-geometry / price-action annotations on the bar that produced the price extreme (NOT necessarily the container's last bar). Does NOT modify `confidence`; consumers weight as they wish. Currently shipped keys:
  - `candidate_rejection_wick_ratio`: float ∈ [0, 1]. For top divergences, the upper wick as a proportion of total bar range (high − low); for bottoms, the lower wick. 0.0 = no rejection wick (or degenerate zero-range bar); 1.0 = bar is entirely wick (doji-like). Higher = stronger visible rejection.
  - `invalidation_level`: raw price. For tops, the extreme bar's high (if price re-prints above this, the rejection setup failed); for bottoms, the extreme bar's low. **Tip-stop recipe**: tip-stop placement = `invalidation_level ± 1-3 ticks` on the signal-opposite side. Engine doesn't assume per-instrument tick size; consumer adds their own buffer.
  - `candidate_volume_ratio`: positive float. Extreme bar's volume divided by trailing-20-bar mean (exclusive of the extreme bar). Above 1.0 = above-average volume; Brooks "signal bar with above-average volume" is the highest-quality reversal pattern. **Brooks-filter recipe**: combine with `candidate_rejection_wick_ratio > 0.4` for the "reversal bar with conviction" filter — divergence + visible rejection + above-average volume = highest-confidence cluster. Key absent when the `volume` column is missing or the lookback window underflows (early bars).
  - `prior_swing_distance_pct`: signed percent of the prior swing's magnitude as a fraction of the **reference** price (i.e., `(candidate_extreme − reference_extreme) / reference_extreme × 100`, with sign flipped for bottoms so positive = direction-consistent). Use **with** `signal.price_side.reference_value` (raw reference price) and `invalidation_level` (raw candidate extreme) to derive measured-move targets — the percent alone is convenient for sizing, the raw prices are needed for absolute target math. **Measured-move recipes** (let `R = reference_value`, `C = invalidation_level`, `Δ = C − R` for a top, `Δ = R − C` for a bottom; both produce a positive `Δ` aligned with the trade direction):
    - **1.0× MM target** = R (full retrace back to the start of the prior leg; the percent field is redundant here — just read `reference_value`)
    - **1.272× / 1.618× extension target** = `C − 1.272 × Δ` for tops (price moves down past R by 0.272 × Δ); symmetric `C + 1.272 × Δ` for bottoms
    - **0.5× / 0.618× partial target** = `C − 0.5 × Δ` for tops; `C + 0.5 × Δ` for bottoms (split-take ladder rung)
    - The percent field is most useful for **sizing decisions** that don't need absolute prices (e.g., "skip this signal if `prior_swing_distance_pct < 1%`, the swing is too tight to justify the spread").

    Key absent when reference price is unavailable or zero.
  - Future Z3/Z4 keys (volume signature, post-candidate confirmation, K-pattern combos) may extend this dict without a further version bump. Consumers should ignore unknown keys.

**Downstream execution patterns enabled by `context_features`** (added with session goal 2026-05-25):
- **Tight tip-stop on entry**: use `invalidation_level` + tick buffer for instant invalidation.
- **Measured-move take-profit**: use `prior_swing_distance_pct` for symmetric projection.
- **Split-take ladder**: divide MM distance into N tranches; scale out at e.g. 0.5×, 1.0×, 1.272×.
- **Brooks-style reversal-bar filter**: combine `candidate_rejection_wick_ratio` with high `confidence` for higher-win-rate sweet spots.
- **Dynamic stop raise**: as price moves in signal direction past intermediate split-take levels, ratchet stop above prior structural pivots (downstream tracks structural pivots; engine provides the entry-time `invalidation_level`).

### 6.2 `policy` (PolicyDecisionDTO)

```jsonc
{
  "weight": 1.20,                   // 0 = drop, 1 = baseline, >1 = boost
  "rule_id": "F2-strong-bottom",    // null if baseline
  "monitor_required": false,        // true → continued validation suggested
  "reason": "...",                  // human-readable explanation
  "strategy_hints": {               // optional advisory tags
    "options_asymmetric": "..."
  }
}
```

**Use this** to convert engine output to a final weight in your trading system. If you have your own policy, **ignore `policy` and read `signal.confidence` directly**.

### Policy is instrument-class-aware (added 2026-05-24)

`apply_policy(sig, instrument_class="us_equity")` returns weights calibrated per
instrument class. Supported values:

- **`us_equity`** (default — backward compatible): F1-F8 + B1, calibrated on
  5y × 10 US ETF/equity × 3-TF.
- **`cn_futures`**: 19-symbol CN futures calibration. Last revised Codex R5
  (2026-05-26) on 10y deep-data v2 sample (4.3x larger than R4). Different
  rule structure from US: F8 boost removed (confidence bands humped, not
  monotone); **no top de-weight on any sub-bucket** — R5 deep-data showed
  R4's CN-top-supp-fade rule (top+higher=supporting → 0.80) was a 2.4y
  sample artifact (basis collapsed from -1.59% to -0.10% with CI fully
  crossing zero) and was REMOVED. All top configurations now route to
  `CN1-top-passthrough` at weight 1.00. F8-cn-no-boost (bottom+weakness)
  remains pass-through 1.00 but with R5-refreshed magnitude (n=306,
  +1.19%, CI excludes zero) — earlier R4 magnitude (+3.81%) was inflated
  by sample window. **cn_futures is independent of `context_topology`** —
  pass `context_topology="B"` explicitly if you need the D+1h+15m context
  attached to signals.

### us_equity rules (default), in precedence order:

| rule_id | trigger | weight | hint | source |
|---|---|---|---|---|
| F2-strong-bottom | bottom + lower_relation=leading + higher_relation=opposing | 1.20 | — | Codex R1 |
| F3-candidate-counter-trend | confidence ∈ [0.65, 0.80) + higher_relation=opposing | 1.15 | monitor_required | Codex R1 |
| F4-options-asymmetric | top + lower_relation=leading + higher_relation=opposing | 1.00 | options_asymmetric | Codex R1 |
| **B1-top-higher-opposing** | **top + higher_relation=opposing** (residual after F4) | **1.30** | exit_policy + calibration_note | **Codex R3 (NEW)** |
| F1-top-lagging-soft | top + lower_relation=lagging | 0.70 | tight_stop_required | Codex R1 edge / R3 path-sensitive |
| F8-bottom-weakness-baseline | bottom + subtype=weakness | 1.10 | — | Codex R2 |
| (baseline) | otherwise | 1.00 | — | — |

### cn_futures rules, in precedence order:

| rule_id | trigger | weight | hint | source |
|---|---|---|---|---|
| F8-cn-no-boost | bottom + subtype=weakness | 1.00 | instrument_filter + universe | **Codex R5 (2026-05-26)** — on 10y deep-data v2 sample n=306, mean +1.19%, CI [+0.26%, +2.14%], hit 57.5%. Significant positive (CI excludes zero); R4's +3.81% claim was inflated by 2.4y sample window. Pass-through weight; no boost without dedicated walk-forward validation. |
| CN1-top-passthrough | **top (any higher_relation)** | 1.00 | direction_gate_calibration_mismatch + universe | **Codex R5 (2026-05-26)** — no CN top configuration has a statistically defensible de-weight on deep-data v2. Pooled top n=506, mean +0.34%, CI [-0.32%, +1.02%]; top+higher=supporting n=324, mean -0.10%, CI [-0.99%, +0.82%]. R4's CN-top-supp-fade rule (weight 0.80 for the supporting sub-bucket) was REMOVED in R5 — its basis was a 2.4y sample window artifact. |
| (baseline) | otherwise | 1.00 | instrument_filter + universe | — |

**Removed rules**:
- `CN-top-supp-fade` (was weight 0.80, R4 2026-05-24) — REMOVED by R5 (2026-05-26). Deep-data v2 sample (4.3x larger) showed the R4 basis (n=74, mean -1.59%) collapsed to n=324, mean -0.10%, CI fully crossing zero. Rule no longer emitted as a `rule_id` value; consumers that filtered on `rule_id == "CN-top-supp-fade"` should expect to see `"CN1-top-passthrough"` instead for the same signal configurations.

**CN consumer hints** (`strategy_hints`):
- `instrument_filter_recommendation`: exclude `j0`, `jm0` (coal complex; only
  negative-EV cluster in 19-symbol backtest — should be revalidated on v2)
- `preferred_universe`: index futures (IF/IH/IC/IM) outperform commodities
- `direction_gate_calibration_mismatch` (top signals, CN1-top-passthrough only):
  direction_gate's `cn_futures` table is pass-through; the hint surfaces this
  for consumers building outside the engine

**CN OOS evidence**: see `doc/codex-r5-verdict-2026-05-26.md` for the R5
deep-data verdict (gold standard). Earlier `doc/cn-policy-oos-2026-05-24.md`
3-split OOS results are SUPERSEDED — they were on the 2.4y sample that R5
proved overstated magnitudes. The R5 deep-data v2 walk-forward K=3 produces
**0 cells stable across both test folds**, confirming filter-tuning has hit
a structural ceiling. Future alpha must come from new detector types
(exhaustion / first-pullback per `doc/exhaustion-detector-spec-2026-05-26.md`).

**Strategy hints**: `strategy_hints` is intentionally open-ended. Today it carries `options_asymmetric` for capped-loss / asymmetric-payoff consumers. Future rules may add other hints (e.g. `requires_strict_stop`, `mean_reversion_only`). Consumers should ignore unknown hint keys.

### 6.3 `exhaustion_events` (ExhaustionEvent — added in v1.4)

Independent stream of **trend-exhaustion reversal candidates**. Targets
the 30–35% blind-spot bucket where all 3 TFs trend the same direction so
no MACD divergence container can form (diagnostic: run
`src/scripts/missed_swing_state.py`; spec:
[`doc/exhaustion-detector-spec-2026-05-26.md`](exhaustion-detector-spec-2026-05-26.md)).
Independent of `signals[]`: an exhaustion bar may coincide with a divergence
bar but is emitted as a separate object. Empty list is valid (no exhaustion
candidates in the window).

```jsonc
{
  "level_id": "D",
  "timestamp": "2026-04-21T20:00:00Z",
  "candidate_bar_idx": 1183,             // index in primary_bars (post reset_index)
  "direction": "top",                    // predicted reversal direction (opposite of segment)
  "segment_id": 47,
  "segment_direction": "up",             // direction of the MACD segment that's exhausting
  "bars_in_segment": 31,
  "n_completed_cycles": 1,               // diagnostic: cycles fully closed within this segment so far (T1 no longer gates on this)
  "wick_ratio": 0.72,                    // signal-direction wick / bar range; ∈ [0, 1]
  "body_half": "lower",                  // "upper" | "lower" | "middle" — where close sits in range
  "volume_ratio": 1.85,                  // bar.volume / trailing-20-bar mean; null when volume unavailable
  "multi_tf_alignment": {                // {level_id → "with_segment" | "against" | "neutral"}
    "D":  "with_segment",                //   primary always "with_segment" by construction
    "1h": "with_segment",                //   strict mode requires every entry == "with_segment"
    "W":  "with_segment"
  },
  "confidence": 0.78,                    // [0, 1], computed in-detector (no PolicyDecision wrapper at v1.4)
  "context_features": null               // forward-compat extension dict; unused at v1.4
}
```

**Trigger gates** (all five must pass under default strict configuration):

| Gate | Meaning | Default |
|---|---|---|
| T1 | `bars_in_segment ≥ min_bars_in_segment` | `20` (daily). Suggested: 50 for 1h, 200 for 15m. Spec's earlier "≥3 completed cycles" gate was retired 2026-05-27 after smoke-test on 10 US ETFs × 5y daily showed 0 segments reach 3 completions. |
| T2 | every foreign TF passed in has `trend_side` aligned to segment direction (strict_alignment=True skips the candidate when a foreign-TF state is uncomputable or against the segment) | strict |
| T3 | signal-direction wick ratio ≥ `min_wick_ratio` AND close in the opposite half of the bar range (Brooks-style reversal candle) | `min_wick_ratio=0.4` |
| T4 | bar's high (for tops) / low (for bottoms) ties or exceeds the segment-so-far extreme | always on |
| T5 | (optional) bar volume ≥ `volume_climax_threshold` × trailing-20-bar mean | `require_volume_climax=False`, threshold `1.5` |

**Confidence formula** (`engine.divergence.exhaustion._confidence`):

```
confidence = clip([0, 1],
    0.5
    + 0.10 × min(bars_in_segment / min_bars_in_segment, 5) / 5
    + 0.20 × max(0, (wick_ratio − min_wick_ratio)) / (1 − min_wick_ratio)
    + 0.10 × multi_tf_alignment_strength            // n_aligned / n_evaluated
    + 0.10 × min(max(volume_ratio − 1.0, 0), 1.0)   // when volume known
)
```

**Consumer guidance**:
- Treat ExhaustionEvents as **candidates for tight-stop / measured-move entries** on Brooks- or Xiao-style reversal-bar setups. Same execution patterns as Z1+Z2-enriched DivergenceSignals (tip stop at extreme bar; measured-move TP from prior leg).
- An exhaustion event firing on bar i does NOT guarantee the trend reverses there. A subsequent bar exceeding the candidate's extreme is the structural invalidation; consumers should track this just as with divergence signals.
- v1.4 ships **no PolicyDecision wrapper** for exhaustion events. Once OOS / walk-forward validation completes (planned for the next minor version), instrument-class-specific rules analogous to the divergence policy will be added.
- Same bar can produce multiple events (e.g., across topology variants) — dedupe on `(level_id, timestamp, direction)` if you need uniqueness.

---

## 7. Topology contract details

### Field `topology` at envelope root

Type: `string`. Values: `"A"` or `"B"` (more may be added in future minor versions).

When set to `"A"`:
- `signals[*].signal.multi_tf_context.lower_tf_level_id` = `"1h"`
- `signals[*].signal.multi_tf_context.higher_tf_level_id` = `"W"`

When set to `"B"`:
- `signals[*].signal.multi_tf_context.lower_tf_level_id` = `"15m"`
- `signals[*].signal.multi_tf_context.higher_tf_level_id` = `"1h"`

The semantic interpretation of `lower_relation` / `higher_relation` stays the same
regardless of topology — they describe *the relationship* between divergence
direction and the foreign TF's trend side. Only the foreign TF level changes.

### What this means for downstream consumers

- **Topology A consumer**: read `multi_tf_context["lower_relation"]` for 1h
  state, `higher_relation` for weekly state. F1-F8 rule semantics match what's
  in `engine/divergence/downstream_policies.py`.
- **Topology B consumer**: read `multi_tf_context["lower_relation"]` for 15m
  state, `higher_relation` for 1h state. The same rule_ids fire (F1-F8) but
  on different sub-populations of signals (the buckets are calibrated to B
  context). Specifically, F2/F4 fire under different empirical distributions;
  expect different rule statistics than the A-topology Codex verdicts.

### When to switch topology

Stay on A unless you're specifically running an options strategy with
limit-order entry + scaled exit. B's appeal is direction-accuracy on top
signals (63.6% vs A's 31.2%) but realizing this requires execution to handle
theta erosion on small-magnitude wins.

## 8. Stability examples

### What's safe to depend on
- `signals[*].signal.direction == "top"` — direction tokens are stable.
- `signals[*].policy.weight` — type is `float`, range is published.
- `levels[*].cycle_state` — tokens come from `{"at_zero", "in_cycle", "completed"}`.

### What may evolve (without breaking v1)
- New rules in `policy.rule_id` may appear.
- New optional keys in `multi_tf_context` may appear.
- New entries in `cross_level.secondary_labels`.

### What's NOT in v1 (will be added in v1.x or 2.x)
- `signals[*].forward_returns` — pre-computed forward returns at h=5/10/20. Currently downstream computes these from bars. Will be added if consumer demand justifies.
- `levels[*].divergence_history` — full per-level signal history. Currently only the strongest+most_recent is in the level state; full lists live in top-level `signals`. May be normalized later.
- `exhaustion_events[*].policy` — PolicyDecision wrapper analogous to `signals[*].policy`. Will be added once OOS / walk-forward validation gives instrument-class-specific weights. Until then, consumers read `confidence` directly.

---

## 9. Pinning recommendations

For production use:
1. Pin to `schema_version >= 1.0, < 2.0`.
2. Treat `monitor_required: true` signals as "live experiments" — log them separately for tracking.
3. Read `multi_tf_context.lower_relation` not `multi_tf_context.relation` going forward.
4. Don't rely on `signals` being non-empty — a stable / featureless market produces zero signals.
5. Treat `policy.weight == 0.0` as drop, but do not assume any rule_id produces 0.0 today (none currently do; F1 is 0.70).
6. **Check `topology` field** to confirm which calibration the rules apply against.
   For stock strategies: expect `"A"`. For options strategies that opt-in to
   B context, expect `"B"`. If you're caching results across topology
   switches, key by `(symbol, topology, system_ts)` not just symbol+time.
