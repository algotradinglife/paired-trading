# PA / Feitian M6 frozen historical cohort gate

Hermes task: `t_b68066e4` (`M6-HIST-001`)

This packet is the deterministic output of the frozen protocol at
`docs/research/pa-feitian-m6-historical-cohort-protocol-v1.json`. The replay
consumes only the pinned M4 scorecard/snapshot/decision-intent/manifest and the
four option contracts already selected in those artifacts. It does not run
`score_today`, discover contracts, scan the raw data directory, reselect a
contract, mutate decision intent, trade, execute, or perform M7 work.

## Interpretation correction

The evaluated 50% baseline and 30% sensitivity both retain the M5 fixed `2x`
target and ten-daily-bar horizon. They are **legacy M5 integration controls**,
not faithful 飞天 hypotheses. This packet tests artifact wiring and bounded
premium-path mechanics only. It does not test or refute a faithful 飞天 track.

The faithful track remains `coverage_gap_not_evaluated` and would require real
premium bars with decision-time shallow-OTM eligibility (approximately delta
`0.25–0.45`, DTE `20–60`), causal IV-rank, predeclared low-IV/range and other
regime splits, a runner without fixed TP, a stop-distance curve plus DD-line
structural-stop proxy, and pessimistic treatment of missing bid/ask. The pinned
paired-trading artifacts cannot currently reproduce those elements faithfully.

### Independent upstream research provenance

The following `trade-philosopher` documents were reviewed at source commit
`5802d0ff5d99819ad01ba9f3550b6a2d504f1e81` as independent, non-transferable
research inputs:

- `doc/pa-replication/feitian-h1-premium-space-2026-06-16.md`
- `doc/SYNTHESIS-AND-HANDOFF-2026-06-17.md`
- `doc/self-evolving-trader-methodology-2026-06-28.md`
- `doc/xiao-feitian-options-timing-system-2026-06-16.md`

Their relevant prior evidence is that faithful delta/DTE eligibility materially
changed conclusions; causal IV-rank, low-IV/range regime, and runner versus
fixed-target behavior require independent as-of reproduction; and bid/ask plus
the DD-line structural stop remain blockers. No upstream historical performance
metrics are imported into this packet.

Independently reproduced here: four-contract bounded coverage, identical-event
legacy M5 control replay, and the insufficient-sample gate. Merely prior and not
reproduced here: faithful selection effects, IV/regime effects, runner behavior,
and DD-line/bid-ask execution behavior.

## Gate result

- Source scorecard rows retained: `13`
- Eligible identical baseline/candidate events: `4`
- Excluded rows retained: `9`
  - outside frozen SHFE `ag`/`au` universe: `7`
  - no rank-1 decision-time selected option contract: `2`
- Baseline 50% stop: `4 observed`, mean premium R `-1.00090361445`
- Candidate 30% stop: `4 observed`, mean premium R `-0.841500172225`
- Paired descriptive mean difference: `+0.159403442225`
- Baseline/candidate premium-R win rate: `0.0` / `0.0`
- Gate: `insufficient_sample`
- Grouped results: suppressed (`n < 10` per group)
- OOS results: suppressed (requires at least two windows with `n >= 10` each)
- Strategy inference and M7 advancement: prohibited

The candidate difference is driven by one event; the other three differences
are zero. This is a bounded diagnostic, not evidence for a policy change.

## Pinned hashes

| Artifact | SHA-256 |
| --- | --- |
| Frozen protocol | `sha256:33a2a32a436a1b1ca8921809b86724ce7401672681952aac510b3375cf039875` |
| Coverage audit | `sha256:90ed911fcbd0c664979a93307906e98db8531269f3e71b8cb9e635a01051c701` |
| Baseline 50% outcome | `sha256:71e34e7fa1844f9138e38c19bd5f668b5ee293b25fdef8505861f2a44accf598` |
| Candidate 30% outcome | `sha256:5114c9b3ddc256907fd18738baa0acb82fe11f058861f3dc1856b1c7d32c04e4` |
| Cohort report | `sha256:f48952da3046161b2c21249c164c2caae206c66cbcac0662324cc9d210bf9e46` |
| Verifier | `sha256:06152eda96e77d54694787cc3f3f23eaa438f7f9c3dc4b467c3cd21a44b03d19` |

## Rebuild and verify

```bash
export QUANT_DATA_ROOT=/path/to/quant_data
export PA_FEITIAN_PYTHON=/path/to/python
node doc/repro/pa-feitian-m6-historical-cohort-2026-07-11/verify.mjs
```

The verifier requires an explicit runtime root, checks pinned hashes and public
path hygiene, rebuilds all four JSON outputs into a temporary directory,
compares them byte-for-byte, loads both M5 premium-outcome contracts, and
asserts the exclusion, sample, grouped/OOS, and no-M7 gates.

## Remaining architecture/data limit

There is only one immutable historical `score_today` artifact available to
this gate. The current `score_today` command uses `date.today()` for its window
and evaluates full loaded series, so it is not a safe historical as-of artifact
producer. A broader cohort requires a separately designed and frozen as-of
artifact production lane with pre-decision data truncation and causal
intraday-confirmation semantics. This task intentionally does not fabricate
that history from today’s store.
