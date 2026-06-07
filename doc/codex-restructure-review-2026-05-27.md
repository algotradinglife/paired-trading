# Codex restructure review

**Date**: 2026-05-27
**Trigger**: doc/restructure-review-packet-2026-05-27.md
**Codex note**: Write to this path was blocked by the read-only sandbox;
the verdict below was captured from the codex exec --json output stream.

## Per-question

**Q1 (layering soundness)**: The scheme is directionally sound, but
Layer 2 must be a real research data product, not a vague cache. It
should define versioned bars, features, unit metadata, swings, labels,
detector events, and provenance. Otherwise it just formalizes today's
script outputs.

**Q2 (holy-grail framing)**: Unsafe as stated. Swings are useful
retrospective labels, not stable causal inputs. Store them as
versioned, parameterized annotations, tagged as retrospective vs
causal. The walk-forward failures argue strongly against treating
extracted swings as a durable "truth layer."

**Q3 (strategy heterogeneity)**: Use a thin shared strategy protocol,
not one fat abstraction. US equity selection, US options, and CN
futures/options need different data, calendars, risk models, and
execution semantics. Let each strategy family own those differences.

**Q4 (cache / freshness)**: mtime is not enough. Every Layer 2
artifact should carry provenance: input hashes, provider, symbol,
timeframe, timestamp convention, calendar/session version, params,
code version, and generated_at. Parquet plus JSON manifests is a good
first step; DuckDB metadata is reasonable once querying manifests gets
annoying.

**Q5 (migration vs greenfield)**: Do not greenfield. Preserve
`AnalysisOutput` v1.4 and the test suite. Use a strangler refactor:
introduce time/provenance primitives, route one pipeline through them,
verify output parity or intentional deltas, then migrate scripts.

**Q6 (leak prevention pattern)**: All of the above, centered on
`ForeignTFView`. Callers should ask `state_at(cutoff_ts,
require_completed=True)` instead of slicing foreign bars directly. Add
Hypothesis/property tests for cutoff semantics and a static check for
suspicious `bars[timestamp <= ts]` patterns. Remove silent partial-bar
grace defaults.

**Q7 (visualization scope)**: Minimum useful visualization is an
audit panel: candles, MACD, divergence/exhaustion markers,
higher/lower TF context, forward-return outcome, and
artifact/provenance ids. Add filterable event tables and
OOS/walk-forward comparisons. Skip full dashboards, live controls, and
option payoff explorers until a strategy passes validation.

**Q8 (missing cross-cutting layer)**: Add a replay/audit/evaluation
plane. It should answer: what data was visible, what fired, what the
strategy would have done, what artifacts were used, and what later
happened. This is more important than generic telemetry.

**Q9 (additional)**: Keep labels separate from detectors. Labels may
use future confirmation; detectors must be causal. Add explicit
exchange calendars/session semantics before live CN expansion. Convert
scripts into thin CLIs over shared artifact readers/writers.

## Recommended order of operations

- Freeze `AnalysisOutput` v1.4 and `build_analysis_output` as
  compatibility boundaries.
- Add `BarSet` / `TimeFrameSpec` / `ForeignTFView`.
- Migrate multi-TF context and exhaustion lookups to the new time module.
- Add timing property tests and static checks.
- Add artifact manifests for raw bars, features, units, labels,
  detector events, and walk-forward outputs.
- Start with Parquet/CSV payloads plus JSON manifests; add DuckDB only
  if needed.
- Migrate one high-value script, likely exhaustion walk-forward, and
  compare against current CSVs.
- Move duplicated MACD/unit computation into shared artifact builders.
- Define separate strategy-family interfaces.
- Build the audit visualization after artifact ids exist.

## Things to NOT do

- Do not rewrite greenfield.
- Do not promote Layer 2 swings to immutable truth.
- Do not use mtimes as the cache contract.
- Do not let scripts independently resample, localize, or slice foreign TFs.
- Do not hide options, futures, and equity scanners behind one base class.
- Do not build dashboards before replay/audit/provenance exists.
- Do not ship fold-specific sweet spots without an ex-ante regime gate.
- Do not keep a default grace window that silently includes partial
  future bars.
