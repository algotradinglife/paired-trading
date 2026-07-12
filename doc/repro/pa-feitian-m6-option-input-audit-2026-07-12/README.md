# PA / Feitian M6 historical option-input capability audit

> **M6 bare-K boundary correction (Hermes `t_3bf64f0c`):** this packet remains
> an immutable record of the earlier faithful-replication capability audit,
> but its bid/ask, delta, exact-expiry/DTE, and append-only-lineage gates do not
> apply to the separate exploratory historical premium-K-line lane. Bid/ask and
> contract delta are absent and must not be proxied; finalized historical replay
> is allowed with strict event-time truncation and explicit non-claims about
> spreads, slippage, fills, execution, and operational observability. See the
> frozen `pa-feitian-m6-liquid-premium-eligibility-contract-v1.json` and its
> public evidence packet. A faithful frozen DD-line remains a separate missing
> input for any faithful Feitian claim.

Hermes task: `t_4c2ae680`

The audit contract was committed before external data was inspected or this
evidence was generated. The packet is a read-only capability inventory for AU
and AG over the frozen 2025-01-02 through 2026-06-08 window. It performs no
option-leg selection, performance calculation, proxying, policy change, M7,
M8, or execution work.

## Exact evidence counts

The three declared bar roots each contain 5,040 AU/AG-prefixed Parquet files:
4,935 parse as option contracts and 105 are rejected as non-option files. The
same 4,935-contract set is present in min5, min15 and daily, for 14,805 parsed
bar-file observations total. The set contains 3,167 AG and 1,768 AU contracts.

| Root | Parsed files | Files overlapping window | Total rows | Rows in window | Unique window calendar dates per product | Files with a 15:00 row in window |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| min5 | 4,935 | 4,470 | 56,032,755 | 46,116,489 | 409 | 4,434 |
| min15 | 4,935 | 4,470 | 20,285,650 | 16,703,388 | 409 | 3,706 |
| daily | 4,935 | 4,473 | 539,375 | 442,231 | 344 | 0 |

All 14,805 bar files are timestamp-ordered with zero duplicate timestamps.
All bar timestamps are timezone-naive. The observed range is 2023-11-22
through 2026-06-17; the audit reports window counts separately and does not
treat rows after the frozen boundary as evidence for an earlier decision.

There are zero AU/AG `*.greeks.parquet` siblings. Two continuous IV-skew files
contain 934 rows total, 687 in the frozen window (AU 343, AG 344). They are
date-only aggregates: they have no contract-bound delta, expiry, bid, ask,
availability timestamp, or query cutoff.

## Capability result

Of the six separately audited capabilities, zero are proven, two are
`data_present_but_unverified`, and four are `missing`:

- min5/min15 premium bars and filename-level contract/month parsing are
  present but unverified because timestamp semantics, decision-time chain
  membership, historical availability, and append-only lineage are absent.
- exact exchange expiry/DTE, contract-bound decision-time delta, historical
  bid/ask, and a frozen faithful PA/Feitian DD-line definition are missing.

The faithful option corpus is therefore **blocked**, not warranted for
generation now. The next gate is to freeze authoritative AU/AG contract
metadata with exact expiry and DTE convention; acquire contract-bound delta
and historical bid/ask with append-only availability timestamps and query
cutoffs; and freeze a faithful intraday DD-line formula before corpus work.

## Immutable evidence

| Item | SHA-256 |
| --- | --- |
| Frozen audit contract | `sha256:03afcc9b5760eab50ea66f0163ef17e46c8ecc2f3924fd1ca9e7939142bc861b` |
| Capability audit artifact | `sha256:892b0926913bff0665c080dd6a5ba8459ccfe0ca3c4e91cb1441706a778b2753` |
| Parsed contract set | `sha256:1763a5d704c4a03ce7a930db00cdbfd784edbeed86c23803c77c651e7e8408ec` |

## Verify

```bash
QUANT_DATA_ROOT=/path/to/quant-data \
QUANT_REPO=/path/to/quant-repository \
PAIRED_REPO=/path/to/paired-trading \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-option-input-audit-2026-07-12/verify.mjs
```

The verifier checks the frozen hashes and boundaries, regenerates the audit
from the declared relative roots, and requires byte-identical JSON. External
data and repositories are opened read-only; raw source bytes and local paths
do not enter the committed artifact.
