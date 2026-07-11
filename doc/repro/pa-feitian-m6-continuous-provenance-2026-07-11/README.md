# PA / Feitian M6 continuous causal-provenance packet

Hermes task: `t_6df19e2b`

This packet follows the merged `M6-HIST-002A` audit. It makes no performance,
selection, proxy, strategy, execution, M7, or promotion claim.

## Result

Two of the six frozen candidate byte streams can be reconstructed exactly:

| Candidate | Result | Raw inputs | Prefix checks |
| --- | --- | ---: | ---: |
| `SHFE.au0.5min.parquet` | exact Parquet bytes reproduced | 40 daily + 40 min5 | 29 frozen-decision/roll/final cutoffs |
| `SHFE.ag0.5min.parquet` | exact Parquet bytes reproduced | 65 daily + 65 min5 | 13 frozen-decision/roll/final cutoffs |

The manifest pins every raw input hash, the exact committed outer generator
and continuous-source blobs, the maximum raw-observation cutoff (`2026-06-08 15:00
Asia/Shanghai`), the naive-local period-end contract, the prior-session
OI/volume rule, three-session confirmation, and a canonical hash of each
trading-date roll schedule. Regeneration with the pinned raw bytes reproduces
both original Parquet files byte-for-byte, not merely row values.

The historical wall-clock execution time is not proven and is explicitly
`unverified`; filesystem modification times are not promoted to provenance.

This is a derived-artifact binding only. The raw Parquets have no acquisition
manifest binding vendor response identity, query time, or observation
availability. Therefore neither underlying is eligible for `score_today`.

The embedded `main_month` and `is_roll` columns are also quarantined. The
outer generator joins the causal schedule using each bar's calendar date and
then forward/back-fills. Most observed changes consequently occur at calendar
midnight inside a CN night session. The verifier hashes the corrected
trading-date schedule, but does not rewrite or certify the embedded columns.

## Sources that remain unbound

No lineage manifest is created for the four date-only candidates:

- `SHFE.{au0,ag0}.option_ivskew.parquet`: no availability timestamp and no
  raw option-chain, maturity-query, rate, main-schedule, or build-query
  manifest.
- `SHFE.{au0,ag0}.regime.parquet`: the same date-only lineage/availability
  gaps, plus the observed generator classifies stress using the full-series
  ATR 80th percentile. That label is not prefix-causal.

The committed trade-philosopher documents at
`5802d0ff5d99819ad01ba9f3550b6a2d504f1e81` were inspected read-only and their
four protocol hashes verified. They reinforce that faithful use requires true
delta/DTE, option intraday bars, a formal DD-line, and bid/ask. Their research
claims and metrics are independent, non-transferable context and are not used
as provenance or performance evidence here. Neither external repository nor
external data was modified.

## Immutable evidence

| Artifact | SHA-256 |
| --- | --- |
| M6-HIST-002A protocol | `sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d` |
| Continuous provenance manifest | `sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3` |

The manifest records 210 exact raw inputs and pins generator commits
`804f48915767abbdb848fc54be52f1e85d076567` (quant) and
`af813b8c06f002433299bf86cc94a73a0c71a511` (paired-trading).

## Verify

```bash
QUANT_DATA_ROOT=/path/to/quant_data \
QUANT_REPO=/path/to/quant \
PAIRED_REPO=/path/to/paired-trading \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11/verify.mjs
```

The verifier reads the exact manifest-listed raw paths, committed Git blobs,
and six frozen candidates. It does not mutate an external repository or data
file. It rejects raw/candidate/generator drift, a different reconstructed
Parquet byte stream, roll-schedule drift, failed prefix checks, IV/regime
certification, score-input promotion, performance evaluation, or M7 advance.

## Exact next gate

Create an acquisition-time raw-source manifest binding every daily/min5 input
to immutable vendor response identities, query parameters and cutoff, plus
explicit observation availability. Generate corrected continuous artifacts
whose `main_month/is_roll` are keyed by trading date, and prove prefix
invariance at every trading-session cutoff before allowing underlying input
consumption.

Separately, rebuild IV with explicit availability timestamps and full raw
chain/maturity/rate/main-schedule lineage, and rebuild regime with a declared
expanding or trailing causal ATR threshold; prove prefix invariance for both.
Faithful Feitian remains blocked on decision-time delta/exact DTE, option
premiums at `<=15min`, a formal DD-line definition, and historical bid/ask.
