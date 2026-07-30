# M6 historical backtest data gate

This packet completes the Data handoff for Issue #50. It defines a versioned,
deterministic allow/deny gate that Engineer can integrate before a formal
`P1-EXP-002` historical run. It maps the public-safe capability audit from
Issue #43 and the exploratory swing views from Issue #53 without promoting
either artifact into formal experiment evidence.
It also binds the merged Issue #49 registry, registry lock, and canonical
`P1-EXP-002` design hash.

No formal run request is included, so this packet does not itself allow
`P1-EXP-002`. It contains no strategy outcomes, PnL, win rate, EV,
profitability ranking, registry mutation, or execution authorization, and it
does not unblock Issue #51.

## Mode boundary

| Mode | Append-only acquisition manifest | Exact filtered input binding | Additional requirements | Current gate status |
| --- | --- | --- | --- | --- |
| Historical replay | Not required | Required | Independently approved complete native source version, causal cutoff, authoritative exchange calendar, per-run freshness and quality checks | Blocked until a complete native source-version manifest is independently frozen into the contract |
| Prospective shadow | Required | Required | Point-in-time observability and current freshness | Blocked by stale interfaces and missing acquisition lineage; denied for historical-only `P1-EXP-002` |
| Live | Not sufficient | Required by any future operational gate | Execution controls outside this Data gate | Denied |

The absence of an append-only acquisition manifest is therefore not a
historical-replay denial by itself. Historical replay makes only a
finalized-vintage claim; it does not claim that the vendor interface was
observable at the original decision time. Shadow and live use are stronger,
separate claims and remain blocked.

## Exact causal binding

A formal request must bind all three:

1. an independently approved manifest for one finalized, immutable native
   source version across the complete six-family-by-three-cadence matrix;
2. each complete native source snapshot in that version by SHA-256, full row
   count, and minimum/maximum native observation timestamp; and
3. the full content of every row retained after applying the frozen history
   start and declared decision
   cutoff, using canonicalization
   `pa_feitian_filtered_json_rows_v1`, by SHA-256 and row count.

The filter is applied before any feature or signal derivation. The filtered
hash covers every field and value in the retained rows, not merely filenames,
contract membership, date ranges, row counts, or inventory metadata. A
membership-only hash is explicitly insufficient. Future rows may exist in a
source snapshot, but none may enter the causally filtered content.

The approved manifest digest is a contract trust root, not another digest the
request may self-issue. The committed contract intentionally has no approved
manifest yet, so it fails closed for every formal request until Data freezes a
complete native version. A caller-truncated recent-only archive cannot become
eligible by publishing a new manifest because its digest will not equal the
contract-approved digest.
The evaluator also pins the canonical SHA-256 of this committed contract in
code. Passing a copied contract that merely replaces the approved source
manifest field fails before any evidence is evaluated; registering a source
version therefore requires a reviewed code-and-contract change.

The evaluator does not trust request-supplied digests. Each private immutable
snapshot is a `pa_feitian_causal_underlying_snapshot_v1` JSON envelope that
binds its family, native cadence, and rows. The evaluator reopens every
snapshot, proves that it exactly matches the approved full-version cell, then
deterministically extracts every row from
`2021-06-01T00:00:00+08:00` through the cutoff. It independently recomputes
the filtered hash, row
count, timestamp range, composite-key duplicates, OHLC checks, and finite
nonnegative volume/open-interest checks. The row allowlist excludes forward
outcomes, options, PnL, and execution fields. Duplicate detection uses
`contract_id` plus `datetime`, so simultaneous rows for distinct contracts are
not falsely treated as duplicates.

All filtered-content, quality, cadence, and roll-linkage checks consume that
same extracted row set. Rows before the frozen history start can never supply
cadence or selected-contract evidence. Genuine missing bars and contracts
that list after the history start remain present as gaps or late listings; the
gate does not fill them, and Issue #51 must abstain when its preregistered
history requirements are not met.

Every timestamp must be timezone-aware. Each binding declares exchange
observation-time semantics, source timezone, decision cutoff, required-through
timestamp, and observed minimum/maximum timestamps. Historical freshness is
measured against that run's required-through timestamp and cutoff, with a
maximum seven-calendar-day coverage lag. The audit's current stale status does
not automatically reject an older historical window.

## Engineer allow/deny surface

The request and decision schemas are fixed in
`docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json`.
Unknown or missing fields fail closed. An `allow` decision requires zero reason
codes. Every decision includes the canonical request SHA-256 and a public-safe
summary of each evaluated binding's source snapshot and filtered-content
digests, row count, cutoff, maximum observation timestamp, coverage lag, and
freshness classification. The decision is therefore traceable to the exact
evaluated input without publishing source rows.

For the frozen design, an allow decision requires exactly 18 independently
verified underlying bindings: all six families at native `daily`, `hour`, and
`min15` cadence. Every binding uses the same exact 15:00 Asia/Shanghai
decision cutoff and contains an observation at that cutoff. `min5` and all
option-premium inputs are prohibited. The request also binds exact
native-source-version, exchange-session-calendar, and causal-roll-ledger
artifacts. The calendar is not caller-authored evidence: the evaluator
rebuilds it byte-for-byte from `exchange_calendars==4.13.2`, the repository's
`cn_night_session_v1` patch, and the frozen XSGE/XZCE/XDCE versions. Sundays,
holidays, or false opens/closes fail closed. Daily/hour/min15 cadence evidence
is checked against family-specific night/day trading-session slots rather than
nominal wall-clock deltas, so legitimate overnight, lunch, holiday, and
weekend gaps are preserved. A Friday night segment may feed Monday, but it
ends on Saturday morning and never spans a weekend; long-holiday reopenings
without exchange-specific evidence fail closed to day-session slots. The
evaluator also checks roll-ledger schema,
digest, cutoff chronology, exact session, and
exchange/family/selected-contract linkage. The resulting
public-safe manifest binds the registry, lock, canonical design, canonical
data-gate contract, approved native source version, all filtered inputs,
calendar, and roll ledger.

Each request covers exactly one decision timestamp. A multi-date formal run
must retain exactly one allow decision for every materialized decision
timestamp; a final-cutoff request cannot be reused as evidence for earlier
dates. This keeps calendar publication, roll selection, exact close, and
filtered inputs causal at every decision without introducing live append-only
requirements.

This Data gate verifies the roll-ledger artifact's identity, causal
availability, decision session, family coverage, and linkage to native
cutoff rows. It deliberately does not recompute the registry's OI/volume
leadership, tie, confirmation, reset, or effective-session strategy rules.
That semantic validation belongs to the Issue #51 strategy implementation,
which remains blocked and unauthorized by this packet. A Data `allow`
therefore cannot by itself authorize event materialization or outcome access.

A request is denied when any required binding:

- supplies only an inventory or membership hash instead of the exact source
  snapshot and causally filtered content hashes;
- lacks the independently approved complete native source version, supplies a
  caller-truncated prefix, or changes the approved source manifest;
- contains null timestamps, duplicate composite keys, OHLC-coherence
  violations, nonfinite/negative volume or open interest, or post-cutoff rows;
- is stale relative to its own required historical coverage, extends beyond
  the decision cutoff, or uses unverifiable timestamp semantics;
- lacks the exact scheduled close, full 6-by-3 matrix, verified calendar, or
  verified causal roll ledger;
- reads option premium, expiry, IV history, historical bid/ask, contract
  delta, forward outcomes, PnL, or execution fields; or
- substitutes, proxies, imputes, or synthesizes missing IV, bid/ask, or delta.

The gate also denies outcome access or outcome-based instrument selection,
source refresh, operational execution claims, and malformed requests.
Unavailable bid/ask, delta, IV, expiry, or close evidence is never synthesized.

## Candidate capability mapping

All six candidate families expose audited underlying and option-premium OHLC
interfaces at daily, hourly, 15-minute, and 5-minute cadence. Availability is
not an allow decision: every formal run still needs its own exact causal input
binding and zero-quality-finding slice.

The daily audit and Issue #53 exploration map as follows:

| Family | Role | Underlying files / rows / OHLC findings | Option files / rows / OHLC findings | Complete swing windows | Representative-eligible clean windows |
| --- | --- | ---: | ---: | ---: | ---: |
| SHFE.au | continuity candidate | 40 / 8,462 / 0 | 1,768 / 226,083 / 106,232 | 405 | 186 |
| SHFE.ag | continuity candidate | 65 / 13,408 / 0 | 3,170 / 313,625 / 174,034 | 651 | 319 |
| CZCE.TA | mainstream candidate | 36 / 7,725 / 63 | 379 / 25,494 / 0 | 379 | 26 |
| CZCE.MA | mainstream candidate | 36 / 7,725 / 32 | 438 / 29,394 / 0 | 379 | 30 |
| SHFE.cu | non-CZCE control | 72 / 15,397 / 0 | 1,490 / 184,196 / 91,378 | 750 | 324 |
| DCE.i | non-CZCE control | 77 / 14,003 / 0 | 214 / 19,756 / 10,140 | 662 | 109 |

The broad daily option audit records substantial OHLC findings for AU, AG, CU,
and i; TA and MA have findings in the daily underlying audit. Those aggregate
findings do not deny every possible slice, but any finding inside a proposed
formal slice does deny that request.

Issue #53 contributes 18 normalized descriptive views and its window counts.
It produces no exact formal-run input binding. All three representative option
overlays for every family retain an invalid quality status, including overlays
that have a complete-path descriptive distribution. They remain inspection
aids, not formal option histories.

The bound capability audit reports exact exchange expiry unavailable and
causal IV history, historical bid/ask, and contract delta unavailable. A
formal `P1-EXP-002` request records these limitations but does not consume the
fields. The gate denies any request that attempts to add them rather than
inventing a proxy.

## P1-EXP-002 handoff

Issue #49 has frozen the exact interfaces, cadences, capabilities, timestamps,
and causal support consumed by `P1-EXP-002`. Engineer may integrate this
evaluator and construct the exact request, but the baseline status is
`blocked_no_approved_native_source_version` because this public packet contains
neither private input snapshots nor an independently frozen complete native
source-version manifest. Registering that manifest is a Data provenance step;
it does not authorize strategy or outcome work.

An allow decision authorizes only the declared Data input for finalized-vintage
historical replay. It does not authorize outcomes, change the hypothesis
registry, confer shadow/live readiness, authorize execution, or make a
point-in-time vendor-observability claim.

## Reproduce

The public profile is rebuilt entirely from committed, SHA-bound evidence; no
private data root is needed:

```sh
PYTHONPATH=src python3 \
  src/scripts/build_pa_feitian_historical_backtest_gate.py \
  --contract \
    docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json \
  --repo-root . \
  --output \
    doc/repro/pa-feitian-m6-historical-backtest-data-gate-2026-07-30/historical_backtest_data_gate_profile_v1.json

PYTHONPATH=src python3 -m pytest \
  src/tests/test_pa_feitian_historical_backtest_gate.py -q

node \
  doc/repro/pa-feitian-m6-historical-backtest-data-gate-2026-07-30/verify.mjs
```

The evaluator CLI additionally requires one
`--source-snapshot BINDING_ID=PATH` argument for every matrix cell plus
`--native-source-version-manifest`, `--exchange-session-calendar`, and
`--causal-roll-ledger`; it recomputes all
bindings before deciding. Set `PA_FEITIAN_PYTHON` when the project interpreter
is not named `python3`. The builder and evaluator reject an output equal to an
input, reject a symlink output, and replace output atomically through a
same-directory temporary file.
