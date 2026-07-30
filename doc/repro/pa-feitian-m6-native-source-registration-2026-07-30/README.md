# P1-EXP-002 native-source registration audit

## Verdict

`data_blocked`

Issue #50 is complete, but this audit did **not** register a native-source
manifest and did not change the frozen historical gate contract. Issue #51
remains blocked.

The read-only audit captured and hashed 978 contract-level underlying source
files across all 18 required family/cadence cells. The inventory contains
2,702,545 rows and is bound by both a private-inventory digest and a
public-safe source-membership digest. Every source file was read into one
immutable byte view before hashing and parsing. Stable no-follow directory
and file descriptors prevent a path or symlink swap from redirecting that
capture, and the CLI refuses to place its output anywhere below the source
root.

Registration fails closed for three independent reasons:

1. The 12 intraday cells have no bound provider, timestamp-semantics, or
   bar-position metadata. Embedded Parquet metadata is observational only and
   cannot self-certify provenance; the reviewed contract contains no approved
   provider-metadata digest. The stored timestamp therefore cannot be asserted
   to mean a completed bar end.
2. Of 2,547,576 rows at or after the frozen history start, 521,090 intraday
   rows do not match the frozen completed-session endpoint grid. Mixed clock
   grids occur in train, validation, and holdout periods, so they are not a
   recent-only anomaly.
3. Two daily cells contain 169 OHLC-coherence findings after the frozen
   history start. The merged #50 gate requires zero findings.

No row was silently shifted, dropped, repaired, resampled, or approved. The
candidate source version therefore has zero materialized private snapshot
cells, no `pa_feitian_m6_native_source_version_manifest_v1` hash, and no
representative formal `allow`.

## Source accounting

| Measure | Result |
| --- | ---: |
| Required matrix cells | 18 |
| Captured source files | 978 |
| Captured source rows | 2,702,545 |
| Rows before the frozen history start | 154,969 |
| Candidate rows at/after the frozen history start | 2,547,576 |
| Rows on an authorized endpoint after daily normalization | 2,026,486 |
| Unexplained timestamp rows | 521,090 |
| OHLC-coherence findings | 169 |
| Files with bound intraday bar-end metadata | 0 |

The public artifact reports family/cadence counts, ranges, stage coverage,
clock-grid aggregates, quality counts, and hashes. It contains no source
filenames, contract identifiers, local paths, raw rows, option data, or
strategy outcomes.

## Why this is `data_blocked`

The semantic mismatch alone would require a reviewed contract revision. The
independent OHLC findings also violate the already-frozen zero-finding gate,
so the combined verdict is `data_blocked`.

Two next actions are required before registration can be retried:

1. repair or replace the invalid required source cells under a new immutable
   source inventory; and
2. define and review a lossless source-specific timestamp normalization that
   binds provider bar-start/bar-end semantics and accounts for every mixed-grid
   row.

Deriving new hourly bars, shifting timestamps, or excluding a clock grid is
not authorized by this issue without that reviewed source contract.

## Reproduction

Public packet validation:

```bash
node doc/repro/pa-feitian-m6-native-source-registration-2026-07-30/verify.mjs
```

Byte-identical real-root rebuild:

```bash
node doc/repro/pa-feitian-m6-native-source-registration-2026-07-30/verify.mjs \
  --data-root "$QUANT_DATA_ROOT"
```

The real-root rebuild reads only the `daily`, `hour`, and `min15` direct
children selected by the frozen contract filename grammar. It performs no
refresh or mutation.

## Claim boundary

- no strategy event or outcome was materialized or read;
- no option, IV, bid/ask, delta, M7/M8, or execution input was accessed;
- no raw source row, filename, contract identifier, or local path is
  committed;
- Issue #50 remains Done; its contract was not weakened;
- Issue #51 remains blocked until a later reviewed source version is actually
  registered.
