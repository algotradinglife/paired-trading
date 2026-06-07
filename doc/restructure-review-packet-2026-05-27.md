# Architectural Restructure Review Packet — macd-momentum

**Reviewer**: Codex CLI (independent architecture review)
**Author**: Han
**Date**: 2026-05-27
**Status**: discussion only — NO code yet.

## 1. Why we're asking

The project started as a faithful implementation of Song Jianyi MACD momentum
theory; over the past few weeks it has grown into:
- multi-source ingest (polygon, qveris, TqSdk) with credential management
  (macOS keychain) and a 14y deep-CN backfill
- a layered engine (`src/engine/`): features → units → divergence + exhaustion
  detectors → multi-TF context → downstream policies → output envelope (v1.4)
- ~40 unit tests, plus a suite of ad-hoc analysis scripts under `src/scripts/`
- ground-truth swing labels via ZigZag + recall coverage reports

A handful of incidents in the past 48 hours expose layering pain we want a
ground-up rethink for before adding more strategies:

1. **Multi-TF look-ahead leak (3 times in a row)**: synth-weekly bar
   timestamps, `data/raw/*_weekly.json` start-of-week stamps, then
   `pd.resample('W-FRI')` label-vs-actual-Friday off-by-4h. Each instance
   silently inflated bottom-side precision numbers. The engine's own
   `enrich_with_higher_tf` has the same flaw at intraday grace=30min and
   may have biased divergence policy F2/F3/B1 calibration.
2. **In-sample sweet spots routinely fail walk-forward K=3**: same R5
   conclusion seen on divergence policy now repeats for the new
   exhaustion detector. 5 cells (conf/wick/volume × bucket) → 2 PASSes
   across 20 test folds, on different folds and different axes (no rule
   captures both). Filter tuning has hit a structural ceiling on this
   engine architecture.
3. **Per-symbol-per-TF MACD computation is re-run script-by-script** with
   no caching. The B-topology v2 backfill + walk-forward harness duplicate
   work that the main `build_analysis_output` already computes.

## 2. User's proposed re-layout

A 4-layer architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 5: Visualization panels (per-strategy dashboards)         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 4: Strategies                                             │
│   - US options 5min price action                                │
│   - CN futures/options "飞天期权" (Xiao Chunxin framework)      │
│   - US equity selection (scanner-style)                         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: Detectors                                              │
│   - "naked K" / candle-geometry detectors                       │
│   - indicator-based detectors (MACD, EMA, RSI, ...)             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: Cleaned middle dataset                                 │
│   - extracted segments / swings — "the holy grail the algo      │
│     tries to catch" — pre-computed and stored                   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: Data interface + storage + on-demand live updates      │
│   - polygon, qveris, TqSdk, with consistent timezone semantics  │
└─────────────────────────────────────────────────────────────────┘
```

Notable framings the user used:
- Middle layer is called "the holy grail the algorithm tries to catch"
- Strategies fan out: US options 5min, CN options Xiao, US equity selection
- Visualization is one panel per strategy on top
- Data layer must handle "on-demand live updates" alongside historical store

## 3. Existing module map (so reviewer knows what's already there)

```
src/engine/
  features/       # MACD, EMAs, stream computations
  units/          # heaps / cycles / segments — vector-unit metadata
  divergence/     # detector, comparator, direction_gate, multi_tf_context,
                  # exhaustion (new v1.4), downstream_policies
  fusion/         # level_state, alignment, snapshot
  labels/         # swing_labeler (ZigZag ground truth)
  output/         # envelope (v1.4), build_analysis_output, topology

src/scripts/      # analyze_*, walk_forward_*, fetch_*, oos_validate_*,
                  # missed_swing_state, swing_coverage_report
src/data/raw/     # *_daily.json, *_60.json, *_15.json, *_weekly.json
src/data/review/  # backtest result CSVs (cn_b_topology_signals_all_v*,
                  # exhaustion_pool_*, mined_patterns_*, ...)
src/tests/        # 173 pytest tests (incl. 40 for exhaustion)
doc/              # contracts, OOS verdicts, recall/precision/walk-forward
                  # reports
```

Topology contract: AnalysisOutput envelope v1.4 with `topology: A|B`,
`instrument_class: us_equity|cn_futures`, `signals: list[SignalOutput]`,
`exhaustion_events: list[ExhaustionEvent]`. Stable API for downstream
consumers.

## 4. Specific questions for Codex review

Please address each carefully.

**Q1 — Layering soundness**: Does this 4-layer scheme make architectural
sense for a trading-research codebase, or is the layer separation more
formal than substantive (e.g. Layer 2 is just a cache of Layer 1+3
outputs, not a real abstraction)?

**Q2 — "Holy grail middle layer" framing**: The user calls Layer 2
extracted segments/swings "the holy grail the algorithm tries to
catch". Given the walk-forward findings — every single-axis cell on
the exhaustion detector is regime-conditional, sweet spots are
2024-2026 tail artifacts — is treating swing extraction as a stable
input layer epistemically safe, or does it bake in survivorship of an
in-sample assumption?

**Q3 — Strategy heterogeneity**: US options 5min, CN options Xiao, US
equity selection — these have very different latency requirements,
data needs (option chain + greeks for options; bar data only for
equity), and execution semantics (capped-loss for options;
size+leverage for futures). Is one "strategy layer" abstraction
sensible, or should we recognize that "strategy" means three different
things here and design accordingly?

**Q4 — Cache / freshness boundary**: Layer 2 implies pre-computed
cleaned data. With live-update Layer 1 on top, where does cache
invalidation live? Should every Layer 2 artifact carry a provenance
hash of its Layer 1 inputs, or is mtime-based invalidation enough? Is
DuckDB / Parquet partitioning over-engineering for a single-developer
trading-research project?

**Q5 — Migration cost vs greenfield**: Given how much already works
(40 exhaustion tests, ~173 pytest tests overall, stable envelope v1.4
contract, codex-reviewed CN policy), what's the SAFE incremental path
to this 4-layer structure? Is a from-scratch greenfield worth the
risk, or should we do a refactor-in-place that preserves the envelope
contract and test suite?

**Q6 — Three repeated leaks**: The multi-TF timing leak class of bug
appeared 3 times in 48 hours and would have shipped to production if
codex hadn't caught it twice. What architectural pattern (NOT just a
code fix) would prevent the next variant? E.g.:
- A `ForeignTFView` abstraction that takes a `cutoff_ts` and is
  contractually obligated to return only fully-completed bars
- Property-based tests (Hypothesis) on the timing semantics
- A linter / static analysis pass that flags suspicious
  `bars[bars['timestamp'] <= ts]` patterns
- All of the above?

**Q7 — Visualization scope**: One dashboard per strategy is appealing
but visualization easily eats engineering time. Recommend a Pareto cut
— what's the minimum viable visualization that's actually useful for
this kind of research codebase, and what's the "would be nice but skip
unless explicitly asked" tier?

**Q8 — What's missing from the user's diagram**: Is there a 6th layer
or cross-cutting concern (telemetry, replay, alerting, audit log of
"what fired when") that the diagram doesn't show but should?

**Q9 — Anything else worth flagging** before any code change ships.

## 5. Expected output

```markdown
# Codex restructure review

## Per-question
Q1 (layering soundness): ...
Q2 (holy-grail framing): ...
Q3 (strategy heterogeneity): ...
Q4 (cache / freshness): ...
Q5 (migration vs greenfield): ...
Q6 (leak prevention pattern): ...
Q7 (visualization scope): ...
Q8 (missing cross-cutting layer): ...
Q9 (additional): ...

## Recommended order of operations
- (concrete sequence)

## Things to NOT do
- (concrete antipatterns)
```

Save to `doc/codex-restructure-review-2026-05-27.md`.
