# Codex architecture review — v0.1

**Reviewer**: Codex CLI
**Target**: `doc/architecture-2026-05-27.html` (v0.1 DRAFT)
**Date**: 2026-05-27
**Verdict**: **v0.1 needs revision before freezing — see Major items**

> Codex sandbox was read-only and could not write this file itself.
> Captured from the codex exec --json stream and saved by Claude.

## 1. Internal Consistency — **Major**

The high-level layering is consistent, but several contract details
contradict the migration/example sections:

- `Data Layer` says it publishes provenance manifests, while the
  manifest schema says "Layer 2+" only. Bars need first-class manifests
  too, otherwise derivation/audit chains start with an unversioned root.
- `ForeignTFView` API exposes `state()`, but migration Step 1 says
  `state_at`. More importantly, the detector contract is
  `detector(bars, derivations, cutoff_ts)`, while the example passes
  explicit `higher_tf` / `lower_tf` views. The detector signature
  should include foreign views or a context object.
- Audit plane claims to record what the strategy would do, but the
  concrete blob is event-only. Strategy decisions/trade intents need
  their own audit/trace contract, or the claim should be narrowed.
- "Every step independently shippable" conflicts with the actual
  dependency chain: Step 6 depends on Step 1/3/4, Step 7 depends on
  Step 4/5/6, Step 10 depends on broad Step 4 adoption.

## 2. Completeness Against Earlier Q1-Q9 Verdicts — **Minor**

The document captures the big decisions: live execution out of scope,
strategy isolation, local-only visualization, detector/label/policy
separation, ForeignTFView, provenance, audit, and strangler migration.

The main dropped/under-specified pieces are acceptance criteria: how
to prove a leak fix changed expected outputs intentionally, how regime
selection avoids becoming another tuned filter, and what exact envelope
compatibility means when audit moves v1.4 to v1.5.

## 3. API Design Soundness — **Major**

`ForeignTFView` is directionally right, but underspecified for
performance and correctness:

- `state()`/`state_at` cannot just recompute MACD/units on every
  cutoff-truncated slice. It needs either a `DerivedStore`/cache keyed
  by `(artifact, cutoff_ts, params)` or precomputed causal derivations
  with prefix-safe lookup.
- `require_completed=True` needs exchange-calendar awareness, session
  close times, early closes, CN night sessions, and provider latency
  semantics. `last_completed_ts` alone is not enough.
- `BarFrame` should include or reference `exchange`, `calendar_version`,
  `adjustment_mode`, `regular/extended session policy`, source query/as-of,
  and payload hash.
- Provenance manifests need payload hash, output row range,
  dependency/package versions, dirty-worktree flag, source query, and
  calendar version.
- Event audit blob needs `event_id`, `detector_id`, detector params
  hash, event schema version, primary/foreign artifact ids, regime
  artifact id, and policy/strategy trace links.

## 4. Migration Feasibility — **Major**

The ordering is close but not yet safe as a plan:

- Step 1 depends on `BarFrame`, but `BarFrame` loaders are Step 3. Add
  a minimal adapter/BarFrame shim to Step 1 or move loader
  normalization earlier.
- Step 2 lint cannot be global on day one unless there is an allowlist
  for unmigrated legacy code.
- Step 6's research gate should not block architecture migration
  unless the regime hypothesis is pre-registered.
- Step 7 is under-scoped: audit backfill and envelope versioning are
  not a 2-day low-risk change.
- Step 8 is materially underestimated. "US options 5min PA from
  scratch" is not a 5-7 day architecture migration item unless the
  strategy rules, data, option chain assumptions, execution model, and
  walk-forward harness already exist. Split it into "strategy module
  skeleton + wiring" and "actual strategy research."

## 5. Test Migration — **Major**

The test map covers current obvious files, but it misses the tests
that enforce the new architecture:

- Import graph / transitive import tests.
- BarFrame validation and timestamp normalization fixtures.
- Calendar edge cases: DST, early close, CN night session, holidays.
- Resample no-leak tests for weekly/daily/intraday.
- Manifest hash invalidation and cache-hit/cache-miss tests.
- Audit schema tests, retroactive rebuild tests, and event lineage
  tests.
- Negative lint fixtures for forbidden direct slicing, `pd.resample`,
  `datetime.now`, and label imports.

"Coverage can never decrease" is achievable only if old tests remain
until replacements land and coverage is measured against meaningful
modules. Some behavior should intentionally change because old behavior
leaked, so regression diffs need golden "changed for known reason"
fixtures.

## 6. Type-Level Enforcement — **Major**

Ruff/AST checks are useful but not sufficient alone.

Gotchas: transitive imports, re-exported labels through helper modules,
`importlib`, `__import__`, `getattr`, `TYPE_CHECKING`, pandas
`.query()`/`.eval()`, renamed DataFrames, and direct slicing patterns
that do not literally match `bars[bars['timestamp'] <= cutoff]`.

Use layered enforcement: import graph tests or `import-linter`, AST
lint for known leak patterns, CI fixtures that must fail, and no
casual `# type: ignore[label-leak]` escape hatch. Any exception should
be a reviewed allowlist entry, not an inline bypass.

## 7. Anti-Patterns Adequacy — **Minor**

The list is strong and matches the main leak/overfitting/scope-creep
failures.

I would add:

- Choosing "favorable regime" after looking at test fold outcomes.
- Redefining R5 or fold boundaries after seeing results.
- Accepting regime subsets with too-small `n`.
- Backfilling audit blobs from current data without marking them
  retroactive/inferred.
- Letting shared `utils/` become a hidden cross-strategy abstraction.
- Changing provider/calendar/adjustment mode without manifest
  invalidation.

## 8. Risks And Missing Concerns — **Major**

Biggest overlooked risk: regime context becomes a new overfitting
surface. The doc correctly identifies regime as the response to
walk-forward failure, but the validation gate is not well-defined
enough to prevent cherry-picking.

Specifics:

- Step 8 estimate is not realistic for US options 5min PA from
  scratch. Treat 5-7 days as "skeleton and first toy backtest," not a
  validated strategy.
- The Step 6 gate needs pre-registration: which failed cells, what
  defines favorable regime, minimum sample size after subsetting, how
  many hypotheses are tested, and whether the same folds remain
  untouched.
- Audit backfill cannot be "auto produce" unless all old artifacts can
  be deterministically rebuilt from pinned data/code. Otherwise
  backfilled audits must be marked `retroactive=true` /
  `confidence=inferred`, and old artifacts should not be presented as
  originally audited.

## 9. Anything Else Worth Flagging — **Minor**

Move exchange calendar choice from "open question" into an early
dependency, because it underpins BarFrame, ForeignTFView, partial bars,
and regime correctness.

Also add per-step exit criteria: schema changes, regression diff
expected/allowed, new tests required, and rollback/deprecation policy.
That will make the design doc executable instead of just directionally
correct.

---

**Final verdict**: v0.1 needs revision before freezing — see Major
items above.
