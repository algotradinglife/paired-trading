# PA / Feitian M5 Final Review Packet - 2026-07-11

Hermes card: `t_13d33bb6`

Branch: `integration/pa-feitian-v02-m5`

Base: `main` at `cf967bf`

Integration implementation HEAD before this packet: `e1c6142`

## Review Ask

Please perform the milestone-level final review for M5. Return exactly one of:

- `APPROVE_M5_FINAL`
- `BLOCK_M5_FINAL` followed by concrete blocking findings with file paths

Do not require M6 strategy selection, live trading, order execution, or a
larger outcome sample as an M5 blocker. Those are explicitly outside this
milestone.

## Objective

M5 adds an observation-only, reproducible premium-space outcome path:

```text
M4b snapshot v1 + decision-intent sidecar + manifest
  -> fixed pre-traversal premium outcome policy
  -> explicit OptionStore daily contract series
  -> pa_feitian_premium_outcome_v1 sidecar
  -> pa_feitian_run_manifest_v1 provenance and hashes
  -> copied dashboard artifacts
  -> artifact-only reviewer outcome view
```

The harness distinguishes option premium R from underlying R and preserves the
existing M4 snapshot and decision-intent semantics.

## Public Review Paths

- Final packet:
  `https://github.com/algotradinglife/paired-trading/blob/integration/pa-feitian-v02-m5/doc/repro/pa-feitian-m5-final-review-2026-07-11.md`
- M5 scope:
  `https://github.com/algotradinglife/paired-trading/blob/integration/pa-feitian-v02-m5/doc/design/pa-feitian-m5-premium-outcome-scope-2026-07-10.md`
- Real-data evidence:
  `https://github.com/algotradinglife/paired-trading/tree/integration/pa-feitian-v02-m5/doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10`
- Premium outcome schema:
  `https://github.com/algotradinglife/paired-trading/blob/integration/pa-feitian-v02-m5/doc/schemas/pa_feitian_premium_outcome_v1.schema.json`
- Harness implementation:
  `https://github.com/algotradinglife/paired-trading/blob/integration/pa-feitian-v02-m5/src/engine/pa_feitian/premium_outcome_harness.py`
- Dashboard implementation:
  `https://github.com/algotradinglife/paired-trading/blob/integration/pa-feitian-v02-m5/frontend/pa-feitian-dashboard/app.mjs`

## Integrated Workstreams

1. Scope: `coordination/pa-feitian-m5-scope` (`21515d0`)
2. Contract: `shared/pa-feitian-m5-outcome-contract` (`5a6e2c9`)
3. Strategy: `strategy/pa-feitian-m5-premium-outcome` (`5c74dd4`)
4. Frontend: `frontend/pa-feitian-m5-premium-outcome` (`0e1febd`)
5. Real data: `data/pa-feitian-m5-premium-outcomes` (`db28301`)
6. Integration: `integration/pa-feitian-v02-m5` (`e1c6142` before this packet)

Intermediate contract, strategy, frontend, data, and integration reviews were
owned by Codex. ChatGPT is intentionally used only for this final milestone
gate.

## Contract Boundary

M5 introduces a separate `pa_feitian_premium_outcome_v1` sidecar. It does not
add posterior fields to `pa_feitian_snapshot_v1` or
`pa_feitian_decision_intent_v1`.

The outcome sidecar records:

- immutable source snapshot, decision-intent, policy, and contract references;
- selected option contract and normalized policy parameters;
- entry and exit evidence with hashes and timestamps;
- `observed`, `ambiguous`, `data_blocked`, or `not_evaluable` status;
- premium-space exit reason, realized premium R, MFE, MAE, and warnings;
- explicit observation-only and daily-bar limitations.

The existing manifest schema gains an optional premium-outcome artifact and
matching hash. Existing manifests remain valid. Model validation requires the
artifact kind and output hash to agree with the referenced sidecar.

## Outcome Policy

The deterministic v1 policy is fixed before posterior traversal:

- consume only the explicit M4 snapshot, decision-intent, and manifest;
- do not rerun `score_today` or reselect an option contract;
- use the first valid daily option bar strictly after decision time;
- model a long premium entry at daily open plus two ticks;
- use an entry-relative `0.5` premium stop and nearest normalized target,
  defaulting to `2R`;
- traverse at most ten post-decision daily bars;
- mark same-bar stop and target touches as `ambiguous` because intraday order is
  unknowable from daily OHLC;
- mark missing or invalid market evidence as `data_blocked`;
- mark model-ineligible intent as `not_evaluable` rather than inventing a
  trade;
- keep premium R separate from any underlying R field.

MFE and MAE are daily-bar envelope observations, not executable tick-path
claims.

## Real OptionStore Evidence

Runtime data is supplied through `QUANT_DATA_ROOT`; committed provenance uses
the public label `external://optionstore/quant-data`. No machine-local absolute
data path is committed.

All four selected M4b historical contracts were found and evaluated from real
OptionStore daily series:

| Contract | Decision UTC | Entry UTC | Exit UTC | Status | Exit reason |
| --- | --- | --- | --- | --- | --- |
| `au2606c1152` | `2026-03-13` | `2026-03-16` | `2026-03-19` | `observed` | `premium_stop` |
| `au2606c1136` | `2026-03-18` | `2026-03-19` | `2026-03-20` | `observed` | `premium_stop` |
| `ag2607c19900` | `2026-05-15` | `2026-05-18` | `2026-05-26` | `observed` | `premium_stop` |
| `ag2608c18800` | `2026-06-02` | `2026-06-03` | `2026-06-08` | `observed` | `premium_stop` |

The second outcome has realized premium R `-1.0036144578`, demonstrating that
a gap can exceed the modeled stop. These observations do not assert that any
trade was approved or executed. One source setup remains `reject`; M5 observes
the fixed selected contract path without rewriting the prior decision.

The deterministic golden test fixture separately covers all four statuses:
`observed`, `ambiguous`, `data_blocked`, and `not_evaluable`.

## Artifact Hashes

| Artifact | SHA-256 |
| --- | --- |
| Frontend snapshot v1 | `sha256:01055e4c28d402812eed9bf602fb5f57a8ce5c9a872e8671c337af2da900bbcf` |
| Frontend decision intent v1 | `sha256:340611f099007d06754a205b99c0cd7c7de989360e428a8036528486fcd711f0` |
| Frontend premium outcome v1 | `sha256:addc74e48d19b9e437f639ff336f9fa0c1c1c0b5a1bdea9511be88087fe8149e` |
| Frontend run manifest v1 | `sha256:c80365478605ee051fbc2a8b824c796f6f5d16b50b8354271b2d3282c723f994` |
| Real-data verifier | `sha256:a112485eced71aed6e7c46729edb38256b555f8bca5ae45b517746c445b61008` |

The verifier checks source/dashboard/frontend copy equality, schema validity,
manifest links, file hashes, selected-option bar hashes, timestamps,
no-lookahead inputs, golden status coverage, frontend rendering, public path
hygiene, and obvious token/private-key patterns.

## Frontend Boundary

The dashboard reads only copied snapshot, manifest, decision-intent, and
premium-outcome JSON artifacts. It does not import or scan market stores.

The outcome review surface renders:

- observed status and exit reason;
- entry, stop, target, exit, premium R, MFE, and MAE;
- contract and policy provenance;
- source/sidecar hash status and reviewer warnings;
- defensive states for missing, malformed, mismatched, and unavailable
  outcome artifacts.

Default committed dashboard fixtures form one coherent real-data artifact set.
Synthetic mixed-status fixtures remain test-only.

## Verification

Python contract, strategy, manifest, builder, and M5 tests:

```bash
PYTHONPATH=src "${PA_FEITIAN_PYTHON}" \
  -m pytest src/tests/test_pa_feitian*.py src/tests/test_eval_tbreak_premium.py -q
```

Result: `87 passed`

Scoped lint:

```bash
"${PA_FEITIAN_PYTHON}" \
  -m ruff check src/engine/pa_feitian src/scripts/build_pa_feitian_premium_outcomes.py \
  src/tests/test_pa_feitian_manifest.py src/tests/test_pa_feitian_premium_outcome.py \
  src/tests/test_pa_feitian_premium_outcome_harness.py
```

Result: `All checks passed!`

Frontend smoke:

```bash
cd frontend/pa-feitian-dashboard && npm run smoke
```

Result: `19 passed`

Real-data deterministic verifier:

```bash
QUANT_DATA_ROOT="${QUANT_DATA_ROOT}" \
PA_FEITIAN_PYTHON="${PA_FEITIAN_PYTHON}" \
node doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/verify.mjs
```

Result: `ok: true`, four real observed outcomes, frontend artifacts loaded,
rendered HTML length `137285`, and byte-stable rebuild.

Additional results:

- JSON Schema and local reference validation: passed
- source/dashboard/frontend hash and copy checks: passed
- public local-path and token/private-key scans: clean
- `git diff cf967bf..HEAD --check`: clean
- deterministic verifier rebuild left tracked JSON artifacts unchanged

## Changed Areas

- `doc/design/pa-feitian-m5-premium-outcome-scope-2026-07-10.md`
- `doc/schemas/pa_feitian_premium_outcome_v1.schema.json`
- `doc/schemas/pa_feitian_run_manifest_v1.schema.json`
- `src/engine/pa_feitian/premium_outcome.py`
- `src/engine/pa_feitian/premium_outcome_harness.py`
- `src/engine/pa_feitian/manifest.py`
- `src/scripts/build_pa_feitian_premium_outcomes.py`
- `src/tests/test_pa_feitian_premium_outcome*.py`
- `frontend/pa-feitian-dashboard/`
- `doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/`

## Known Non-blocking Limits

- Real evidence contains four historical outcomes and all four hit the premium
  stop. This proves the artifact and evaluation path, not strategy edge.
- The source market series currently ends around `2026-06-08`; fresh daily
  operation depends on updated upstream data.
- Daily OHLC cannot establish intraday stop/target ordering or executable
  bid/ask fills. Ambiguity is surfaced rather than guessed.
- The v1 model assumes zero commission and fees and normalizes by premium/tick
  movement; it is not cash PnL accounting.
- M5 does not aggregate EV, win rate, or failure modes, rank trace nodes, tune
  policies, or select strategies. Those belong to M6.

## Non-goals Preserved

- no live trading
- no order execution
- no broker integration
- no automatic reviewer override
- no frontend raw market scan
- no `score_today` rerun or contract reselection in the outcome harness
- no mutation of snapshot v1 or decision-intent v1 semantics
- no M6 EV/ranking/strategy-selection conclusions

## Merge Gate

Keep the pull request in draft until ChatGPT returns `APPROVE_M5_FINAL`. After
that verdict, normal repository checks may be reconfirmed, the PR may be marked
ready, and it may be merged into `main`.
