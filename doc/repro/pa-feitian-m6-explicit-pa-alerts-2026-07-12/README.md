# PA / Feitian M6 explicit historical PA alerts

Hermes task: `t_1bf2484e`

This public-safe packet materializes 11 explicit daily H2-bottom PA alerts
from 670 hash-pinned, finalized-vintage AU/AG underlying records. The
materialization contract was committed at
`a63cdec3ec82b1b2a475ce561626310ca6c1a1cc` before the historical records were
scanned.

## Exact alert source

The only alert authority is `PABottomDetector` at paired-trading revision
`792cb9a0c47cd6cb20c5da4340008481e7a7bd1f`. Its two implementation files,
constructor parameters, literal `PASignal` pattern/direction, input corpus,
decision cutoff, missing-data behavior, identities, and rejection tests are
frozen in the contract. The materializer uses only each bound daily bar's
OHLCV and timestamps. It does not read the corpus's descriptive D/W/60/15
diagnostics or convert generic candlestick shapes into alerts.

| Product | Bound daily records | Explicit alerts |
| --- | ---: | ---: |
| AU | 333 | 7 |
| AG | 337 | 4 |
| **Total** | **670** | **11** |

These are `retrospective_finalized` alerts. They do not prove which source
bytes were observable historically. Missing source decisions remain missing;
nothing is filled, proxied, reselected, or recovered from raw data.

## Immutable evidence

| File | SHA-256 |
| --- | --- |
| Materialization contract | `sha256:e4ba463a12d96a2e23843d7d8e44be35a7758a3f034c353ea72495d8c8a6382e` |
| Bound underlying corpus | `sha256:cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080` |
| Explicit alert corpus | `sha256:f993eb8ff11afcd1edd673f4c21f5a4334dcdb086c53410c7eef62a84633cbe2` |

## Verify

Run with a Python environment containing the repository dependencies:

```bash
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-explicit-pa-alerts-2026-07-12/verify.mjs
```

The verifier checks the pre-scan freeze commit, every bound input and strategy
source hash, the exact output schema and public-safe boundary, and byte-for-byte
deterministic regeneration. Focused tests additionally exercise diagnostic
non-use, cutoff rejection, expanding-prefix equivalence, future-row
invariance, and identity/field rejection.

## Boundary and next gate

An alert starts observation only. This packet contains no option or premium
path, contract membership, bare-K or DD-line confirmation, Greeks, delta,
DTE, bid/ask, modeled price, outcome, PnL, win rate, tuning, M7/M8, or
execution result.

The next gate is to use only this hash-pinned corpus as the explicit alert
input to the already frozen bare-K protocol. Hash-pinned per-unit eligibility
membership and an authentic machine-testable bare-K or DD-line definition
remain separate blockers.
