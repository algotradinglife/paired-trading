# PA / Feitian M6 finalized-vintage underlying signal corpus

Hermes task: `t_715f7397`

This packet is the first expanded capability enabled by `M6-HIST-003`. The
contract was committed before this artifact was generated. It freezes the
2025-01-02 through 2026-06-08 range, AU/AG products, every causal-schedule
session at 15:00 Asia/Shanghai, D/W/60/15 aggregation, strict-prior-20
descriptive signals, numeric rounding, and output schema.

## Corpus and coverage

| Product | Requested decisions | Included records | Excluded | Supported series |
| --- | ---: | ---: | ---: | ---: |
| AU | 344 | 333 | 11 | 1,332 |
| AG | 344 | 337 | 7 | 1,348 |
| **Total** | **688** | **670** | **18** | **2,680 / 2,752** |

All 18 exclusions are causal-schedule sessions for which the exact pinned
continuous file has no 15:00 local source bar. Nothing is filled, proxied, or
reselected. Included coverage is 97.38% of requested decision-level series.
The last included decision is 2026-06-05; the frozen 2026-06-08 boundary is
retained and excluded by the same exact-close rule.

Every included record carries the exact continuous-source hash,
raw-input-set hash, causal roll-ledger hash and causal main month. The corpus
ignores the candidate files' quarantined embedded `main_month/is_roll`
columns. For each decision, rows are first truncated to the frozen 260-day
lookback and `timestamp <= decision_ts_utc`; only then are causal sessions
mapped and D/W/60/15 bars aggregated. The current aggregate is excluded from
its own prior-20 baseline.

## Descriptive boundary

The artifact contains underlying OHLCV/OI bar summaries, bar shape and close
location, strict-prior-20 range/breakout diagnostics, causal EMA alignment,
and coverage/exclusion counts only. It makes no strategy, selection,
profitability, downstream milestone, or operational claim.

This is `retrospective_finalized` research. Current finalized bytes can contain
later corrections; historical vendor visibility, deletions, restatements and
survivorship are unproven. Filesystem timestamps and maximum observation
timestamps are not acquisition evidence. Operational observability remains
blocked pending the M8 append-only acquisition lineage.

## Immutable evidence

| Artifact | SHA-256 |
| --- | --- |
| Frozen corpus contract | `sha256:e35d4567792a386270989b47af31d4e2e23d76b632eff92cabc6188f8ba37c34` |
| Corpus JSON file | `sha256:cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080` |
| Canonical corpus payload | `sha256:3a0078d4bd2bb2f141b8175479afad6554a705b538796e59a7ab8e69effafe02` |

## Verify

```bash
QUANT_DATA_ROOT=/path/to/quant_data \
QUANT_REPO=/path/to/quant \
PAIRED_REPO=/path/to/paired-trading \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-underlying-corpus-2026-07-12/verify.mjs
```

The verifier reads only the contract-listed candidate paths and the 210 paths
listed by the pinned provenance manifest. It checks exact candidate/raw hashes,
pinned generator blobs, causal roll-ledger hashes, deterministic regeneration,
future timestamp ordering, the scope boundary, and the fixed coverage funnel.
It does not use filesystem discovery, environment time, or Parquet rewriting.

## Next option-evaluation gate

Before any separate option-premium evaluation, freeze and hash-pin a
decision-time option corpus at 15-minute cadence or finer with explicit
contract/maturity lineage and availability, exact exchange expiry and
decision-time delta/DTE, a formal DD-line definition, and historical bid/ask.
That new corpus must pass its own timestamp truncation, future-row invariance,
and deterministic verifier. This underlying packet neither supplies that gate
nor authorizes evaluation, candidate selection, M7, or execution.
