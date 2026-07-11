# PA / Feitian M6 Candidate Recovery Evidence

Date: 2026-07-11

This packet evaluates one explicitly fixed retrospective exploratory exit-policy
candidate from recovered OptionStore daily bars. It leaves the original M5 and
M6 baseline packets unchanged. It is neither prospective preregistration nor a
production-policy approval.

## Candidate

`candidate_stop_30pct` holds the M5 target, holding horizon, daily-OHLC
ambiguity/gap semantics, and two-tick slippage constant, while changing only
the long-option premium stop from 50% to 30% of entry premium. The policy
declaration is fixed at `2026-07-11T12:00:00Z`, before its recorded traversal
at `2026-07-11T12:01:00Z`.

## Result

The candidate sidecar has three observed outcomes and one `data_blocked`
outcome. Its fourth contract requires a longer traversal window than the
baseline and encounters invalid daily OHLC. The screening report is therefore
`blocked`: the candidate observed-event set differs from the four-event
baseline, so no paired difference, ranking, confidence interval, or strategy
inference is emitted.

The candidate's descriptive pooled mean premium R is `-0.7886668963` across
its three observed events; it is not comparable evidence against the baseline.

## Rebuild

```bash
QUANT_DATA_ROOT=/runtime/path/to/quant-data \
PA_FEITIAN_PYTHON=/path/to/python \
node doc/repro/pa-feitian-m6-candidate-recovery-2026-07-11/verify.mjs
```

The verifier requires the four selected OptionStore daily files, rebuilds the
candidate M5 sidecar, baseline and candidate M6 artifacts, the controlled
screening/failure-mode reports, and dashboard copies. It validates hashes,
typed contracts, blocked-comparison semantics, artifact-only dashboard render,
and absence of local runtime paths.

## Key artifacts

| Artifact | SHA-256 |
| --- | --- |
| Candidate M5 sidecar | `sha256:9dbd7d9058dc2d4ed4a643447b8c4dc4ba27bad24a7e99078b310bd682a5628d` |
| Baseline M6 dataset | `sha256:6ebcef341f7cea43036c3e2b9b609661c9a828f0992ce5793221d5a8ae6c1fba` |
| Candidate M6 dataset | `sha256:1bb0aa8426aa5c65f00ae491b827308c4ddb1e0225c2fde8e361ad17bb99b1ad` |
| Screening report | `sha256:98156c33be21c899d1567e196ecb10029acc8c6045d7435b769d187961b2bf88` |
| Failure-mode report | `sha256:cf6a5b5f55ee99773e2f861a9ab2b132f12e2db347b4b322b7e9ff8faf9aded7` |

The `dashboard/` directory exposes two hash-bound review sets:

- `pa_feitian_run_manifest_baseline_screening_v1.json` references copied
  baseline dataset, baseline aggregate, and the formal screening report. It is
  the reviewer-facing entry point for the formal `blocked` decision.
- `pa_feitian_run_manifest_candidate_stop_30pct_v1.json` references copied
  candidate dataset, aggregate, and candidate failure-mode report. It keeps
  candidate data-quality detail separate from the baseline-linked screening
  provenance.

No dashboard manifest silently drops the formal screening artifact: it is
bound to the baseline/screening manifest whose dataset and aggregate hashes
match the report's provenance.
