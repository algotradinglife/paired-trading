# PA / Feitian M6 Data-Quality Recovery Evidence

Date: 2026-07-11

This packet rebuilds the fixed retrospective `candidate_stop_30pct` after the
OptionStore `SHFE.ag2608C18800.parquet` daily history was repaired. It is a new
hash-pinned packet. The original M5 packet and the earlier M6 candidate-recovery
packet remain unchanged.

## Candidate

The candidate changes only the long-option premium stop from 50% to 30% of
entry premium. It retains the M5 2x target, ten-daily-bar horizon, daily-OHLC
ambiguity/gap semantics, and two-tick slippage. Its retrospective declaration,
registration, traversal, policy ID, and policy version are unchanged from the
earlier recovery packet; this is not prospective preregistration or a
production-policy approval.

## Verifier output

```json
{"ok":true,"candidate":"candidate_stop_30pct","candidate_statuses":["observed","observed","observed","observed"],"screening":"inconclusive","paired_events":4,"baseline_mean_premium_r":-1.0009036144499999,"candidate_mean_premium_r":-0.841500172225,"descriptive_mean_difference":0.15940344222499997}
```

## Result and comparison

All four baseline and candidate events are observed. The repaired fourth
candidate event now exits by `premium_stop`; there is no candidate
`data_blocked` outcome. Three candidate events exit by `premium_stop` and one
by `time_exit`.

The four-event descriptive pairing is:

| Event | Baseline premium R | Candidate premium R | Candidate - baseline |
| --- | ---: | ---: | ---: |
| au / 2026-03-13 | -1.0000000000 | -1.0000000000 | 0.0000000000 |
| au / 2026-03-18 | -1.0036144578 | -0.3660006889 | +0.6376137689 |
| ag / 2026-05-15 | -1.0000000000 | -1.0000000000 | 0.0000000000 |
| ag / 2026-06-02 | -1.0000000000 | -1.0000000000 | 0.0000000000 |
| Pooled mean | -1.0009036144 | -0.8415001722 | +0.1594034422 |

The `retrospective_exploratory` comparison contract retains all four matched
events and both OOS windows. Its event-paired mean difference is
`+0.1594034422`, median difference is `0`, and seeded 95% adjusted bootstrap
interval is `[0, 0.4782103267]`. The two OOS-window mean differences are
`+0.6376137689` (`wf_1`, one event) and `0` (`wf_2`, two events).

Screening is forcibly `inconclusive`, reviewer status remains `pending`, and
the report states that retrospective exploratory evidence cannot support
promotion or advance M7. These metrics are descriptive; they do not approve a
policy change or support a strategy inference.

## Rebuild

```bash
QUANT_DATA_ROOT=/mnt/c/Users/hhusl/quant_data \
PA_FEITIAN_PYTHON=/tmp/paired-trading-m6-venv/bin/python \
node doc/repro/pa-feitian-m6-data-quality-recovery-2026-07-11/verify.mjs
```

The verifier requires the four selected OptionStore daily files and rebuilds
only this packet's candidate M5 sidecar, baseline and candidate M6 artifacts,
screening/failure-mode reports, and dashboard copies. It validates pinned
hashes, typed contracts, retrospective no-promotion semantics, artifact-only
dashboard rendering, and absence of local runtime paths in pinned artifacts.

## Key artifacts

| Artifact | SHA-256 |
| --- | --- |
| Candidate M5 sidecar | `sha256:e3270e76178870dabf2f97424f4a01db93604d64458ee3c44eb4a0ed5f8a7d01` |
| Baseline M6 dataset | `sha256:70bad7e48391b71eb3cb01ad7482e5938d26c58d47e5fd518fe3338179592d1c` |
| Candidate M6 dataset | `sha256:dad77b16a6fc2b660b050999c2411e0916550c2903c3f8b343bae15e20b5133b` |
| Screening report | `sha256:5b3d8d51f8e7aaddd6bee8e04ed264a8beff10a5e06de74af84c4ba908563a2a` |
| Failure-mode report | `sha256:7c8dc57ec27dbe083b143391521aa681ec9bd2016e0a11774631b1d6801c4709` |

The `dashboard/` directory exposes separate candidate/failure-mode and
baseline/screening review sets. The baseline-linked manifest retains the formal
screening artifact; the candidate-linked manifest retains the repaired
candidate evidence and descriptive failure-mode detail.
