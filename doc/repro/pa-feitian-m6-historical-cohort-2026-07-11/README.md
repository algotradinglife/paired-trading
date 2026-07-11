# PA / Feitian M6 frozen historical cohort gate

Hermes task: `t_b68066e4` (`M6-HIST-001`)

This packet is the deterministic output of the frozen protocol at
`docs/research/pa-feitian-m6-historical-cohort-protocol-v1.json`. The replay
consumes only the pinned M4 scorecard/snapshot/decision-intent/manifest and the
four option contracts already selected in those artifacts. It does not run
`score_today`, discover contracts, scan the raw data directory, reselect a
contract, mutate decision intent, trade, execute, or perform M7 work.

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
| Frozen protocol | `sha256:26334611239774812ebc42aa824aa6cf1a406e683110e57ee22ab72a78201cf9` |
| Coverage audit | `sha256:3091610774d7210bbbfda1b7e5a4be1d70a6da2ecdb7302b45e36cd8d5509cf1` |
| Baseline 50% outcome | `sha256:71e34e7fa1844f9138e38c19bd5f668b5ee293b25fdef8505861f2a44accf598` |
| Candidate 30% outcome | `sha256:5114c9b3ddc256907fd18738baa0acb82fe11f058861f3dc1856b1c7d32c04e4` |
| Cohort report | `sha256:b989da4fd1bbcf349993a27ec7d3d863aef29574dcb8ec1a3ac488b463e4556e` |
| Verifier | `sha256:af41a4c1c454bb47b43dcf26505d43721b77a309892c4d89ce50e1e4c2212d61` |

## Rebuild and verify

```bash
QUANT_DATA_ROOT=/mnt/c/Users/hhusl/quant_data \
PA_FEITIAN_PYTHON=/tmp/paired-trading-m6-venv/bin/python \
node doc/repro/pa-feitian-m6-historical-cohort-2026-07-11/verify.mjs
```

The verifier enforces the exact runtime root, checks pinned hashes and public
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
