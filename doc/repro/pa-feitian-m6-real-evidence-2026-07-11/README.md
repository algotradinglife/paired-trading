# PA / Feitian M6 Real-Evidence Packet

Date: 2026-07-11

This is a retrospective exploratory evidence packet, not a prospective
preregistration. It contains a reproducible M6 projection of the existing M5
real sidecar and a blocked-evidence record for any alternative exit policy. It
does not synthesize, relabel, or evaluate a candidate outcome.

## Baseline evidence

The existing M5 real premium-outcome sidecar is the only outcome input. Its
four observed historical records are projected into the checked-in M6 baseline
dataset and aggregate artifacts.

- observed events: 4
- pooled mean premium R: `-1.00090361445`
- premium-R wins: 0
- bootstrap 95% interval: `[-1.00271084335, -1.0]`

This is historical descriptive evidence—not evidence of an edge or approval of
the M5 exit policy.

## Candidate evidence is blocked

The inspected runtime OptionStore root exists but its `daily/` directory has
zero files. The four selected M4b premium paths therefore cannot be reproduced
from raw data. No alternate M5 sidecar or candidate M6 dataset/aggregate was
created, and no result is imputed from the baseline sidecar.

The checked-in [candidate_availability_v1.json](candidate_availability_v1.json)
records this exact state as `data_blocked`: unavailable and inconclusive. It
does not name an evaluated candidate policy, compute a difference to baseline,
rank policies, or permit strategy approval. There is no M6 comparison code or
frontend in this packet.

## Exact recovery requirement

Before an alternative exit policy can be evaluated, recover the original daily
OptionStore OHLC series—with source provenance—for all four M4b-selected
contracts:

- `au2606c1152`
- `au2606c1136`
- `ag2607c19900`
- `ag2608c18800`

The recovered series must start strictly after the associated decision,
contain valid daily OHLC through each declared holding window, and reproduce
the existing M5 selected-option-bar SHA-256 evidence for the baseline wherever
applicable. Only then may a new fixed retrospective policy be declared before
its own traversal, with an explicit statement that it was not prospectively
preregistered. That recovery must produce a new M5 sidecar, M6 artifacts, and
verifier; this packet must not be amended to pretend it contained the missing
candidate evidence.

## Artifacts

| Artifact | Role |
| --- | --- |
| `source/pa_feitian_evaluation_dataset_baseline_v1.json` | Immutable four-row M6 baseline projection |
| `source/pa_feitian_evaluation_aggregate_result_baseline_v1.json` | Baseline aggregate and walk-forward diagnostics |
| `source/pa_feitian_run_manifest_baseline_evaluation_v1.json` | Typed provenance and source hashes |
| `candidate_availability_v1.json` | Baseline reference plus explicit blocked candidate evidence |
| `verify.mjs` | Rebuilds and verifies only the baseline artifacts and blocked state |

All artifact hashes are pinned in the configuration. No raw OptionStore series,
machine-local path, credentials, live trading, execution behavior, candidate
sidecar, or candidate M6 result is committed.

## Rebuild and verification

Set the runtime root and project Python explicitly:

```bash
QUANT_DATA_ROOT=/runtime/path/to/quant-data \
PA_FEITIAN_PYTHON=/path/to/python \
node doc/repro/pa-feitian-m6-real-evidence-2026-07-11/verify.mjs
```

The verifier requires the inspected `daily/` directory to be empty. It
rebuilds the baseline M6 dataset, aggregate, and manifest from the existing M5
real sidecar; validates typed contracts and hashes; and verifies that the
comparison configuration remains blocked and inconclusive. If daily data is
restored, the verifier fails deliberately so a new recovery packet is required.
