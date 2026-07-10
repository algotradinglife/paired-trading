# PA / Feitian M5-DATA-001 Real Premium Outcomes

Date: 2026-07-10

Scope: M5-DATA-001 only. This packet records real OptionStore premium-path
coverage for the four M4b PA / Feitian selected contracts. It does not tune
policy parameters, reselect contracts, change decision intent, claim exact tick
execution, or add M5 frontend features.

## Inputs

- M5 scope: `doc/design/pa-feitian-m5-premium-outcome-scope-2026-07-10.md`
- Final harness commit: `5c74dd4964c814f1daefa09dc9f45ac3bfcc5788`
- Recorded OptionStore root label: `external://optionstore/quant-data`
- Runtime OptionStore root mapping: set `QUANT_DATA_ROOT` in the local shell
  before rebuilding or verifying this packet.
- M4b source manifest:
  `doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_run_manifest_with_decision_intent_v1.json`
- M4b source snapshot:
  `doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_snapshot_v1.json`
- M4b decision intent:
  `doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json`

Fixed timestamps:

- `generated_at_utc`: `2026-07-10T00:00:00Z`
- `policy_declared_at_utc`: `2026-07-10T00:00:00Z`
- `traversal_started_at_utc`: `2026-07-10T00:01:00Z`

## Artifacts

| Path | Role | SHA-256 |
| --- | --- | --- |
| `source/pa_feitian_premium_outcome_v1.json` | Source M5 premium outcome sidecar | `sha256:addc74e48d19b9e437f639ff336f9fa0c1c1c0b5a1bdea9511be88087fe8149e` |
| `source/pa_feitian_run_manifest_with_premium_outcome_v1.json` | Source M5 run manifest | `sha256:2a0b3bfdf2b1c605ba9f4d1817dbe74847d9b90c3786b51b96c69137c5d782a4` |
| `dashboard/pa_feitian_premium_outcome_v1.json` | Dashboard premium outcome copy | `sha256:addc74e48d19b9e437f639ff336f9fa0c1c1c0b5a1bdea9511be88087fe8149e` |
| `dashboard/pa_feitian_run_manifest_v1.json` | Dashboard-facing M5 manifest copy | `sha256:54e53eb8203b26da9519106ab27e6c21b2ba64edfb64439e212f42b19492ebda` |
| `verify.mjs` | Evidence verifier | `sha256:a112485eced71aed6e7c46729edb38256b555f8bca5ae45b517746c445b61008` |

## Real Outcomes

All four M4b selected contracts were found under the explicit OptionStore daily
root and evaluated as observed daily premium-stop outcomes. Source snapshot
statuses remain unchanged.

| Signal | Source status | Decision state | Contract | M5 status | Exit | Entry UTC | Exit UTC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `paft_scorecard_0001_kq_m_shfe_au_20260313000000` | `data_blocked` | `watch` | `au2606c1152` | `observed` | `premium_stop` | `2026-03-16T00:00:00Z` | `2026-03-19T00:00:00Z` |
| `paft_scorecard_0002_kq_m_shfe_au_20260318000000` | `keep` | `watch` | `au2606c1136` | `observed` | `premium_stop` | `2026-03-19T00:00:00Z` | `2026-03-20T00:00:00Z` |
| `paft_scorecard_0003_kq_m_shfe_ag_20260515000000` | `data_blocked` | `watch` | `ag2607c19900` | `observed` | `premium_stop` | `2026-05-18T00:00:00Z` | `2026-05-26T00:00:00Z` |
| `paft_scorecard_0004_kq_m_shfe_ag_20260602000000` | `drop` | `reject` | `ag2608c18800` | `observed` | `premium_stop` | `2026-06-03T00:00:00Z` | `2026-06-08T00:00:00Z` |

The sidecar records daily OHLC evidence only. It does not claim exact tick
ordering or executable bid/ask fills.

## Golden Status Coverage

The real M4b contracts are all `observed`. The verifier explicitly checks the
existing premium outcome fixture at
`src/tests/fixtures/pa_feitian_premium_outcome_v1.json` for the full golden
status surface:

- `observed`
- `ambiguous`
- `data_blocked`
- `not_evaluable`

No extra arbitrary status fixture is duplicated in this evidence directory.

## Rebuild Command

Use the main repo venv through `PA_FEITIAN_PYTHON`, and map the recorded
OptionStore label with `QUANT_DATA_ROOT`:

```bash
PYTHONPATH=src "${PA_FEITIAN_PYTHON}" \
  src/scripts/build_pa_feitian_premium_outcomes.py \
  --snapshot doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_snapshot_v1.json \
  --decision-intent doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_decision_intent_v1.json \
  --source-m4-manifest doc/repro/pa-feitian-m4b-real-data-artifacts-2026-07-10/source/pa_feitian_run_manifest_with_decision_intent_v1.json \
  --quant-data-root "${QUANT_DATA_ROOT}" \
  --quant-data-root-label external://optionstore/quant-data \
  --out doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_premium_outcome_v1.json \
  --manifest-out doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/source/pa_feitian_run_manifest_with_premium_outcome_v1.json \
  --frontend-outcome-copy doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/dashboard/pa_feitian_premium_outcome_v1.json \
  --generated-at-utc 2026-07-10T00:00:00Z \
  --policy-declared-at-utc 2026-07-10T00:00:00Z \
  --traversal-started-at-utc 2026-07-10T00:01:00Z \
  --source-commit 5c74dd4964c814f1daefa09dc9f45ac3bfcc5788
```

The dashboard manifest is a deterministic path-adjusted copy of the source M5
manifest. It points `decision_intent_artifact.path` at the existing M4b
dashboard decision-intent copy and `premium_outcome_artifact.path` at the new
dashboard premium outcome copy.

## Verification

```bash
node doc/repro/pa-feitian-m5-data-real-premium-outcomes-2026-07-10/verify.mjs
```

The verifier checks:

- byte-identical rerun of the real-data build with fixed paths, timestamps, and
  source commit;
- schema validity for source/dashboard/frontend M5 manifests and premium sidecars;
- all four selected real contracts, original source statuses, M5 observed
  statuses, exit timestamps, and selected-option bar hashes;
- no-lookahead timestamp ordering and decision-time input references;
- source-to-dashboard premium outcome copy and existing M4b snapshot/decision
  copies;
- `data_access.status == real_data_available` and the recorded OptionStore
  label;
- existing golden fixture status coverage for `observed`, `ambiguous`,
  `data_blocked`, and `not_evaluable`;
- frontend fixture copy hashes, real premium-outcome render compatibility, and
  artifact-only dashboard boundary;
- absence of obvious public token/private-key patterns in this packet;
- absence of local runtime path fragments in this packet.
