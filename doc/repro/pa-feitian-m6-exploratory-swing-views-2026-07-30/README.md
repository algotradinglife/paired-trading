# M6 exploratory historical swing views

This packet completes the Data handoff for Issue #53. It gives Strategy a
deterministic, public-safe view of historical swing shape, activity, quality,
coverage, and freshness for the six candidate families audited in Issue #43.

This is exploration only. It contains no strategy outcomes, PnL, win rate, EV,
profitability ranking, contract recommendation, or execution claim. It does not
produce preregistered evidence, authorize `P1-EXP-001` or `P1-EXP-002`, establish
live/shadow readiness, or unblock Issue #51.

## Method

The builder reads the explicit `QUANT_DATA_ROOT` daily underlying interface in
read-only mode. It never refreshes or mutates the source. Each anonymous
underlying series is first frozen at the 2026-07-30 audit date, then divided
into non-overlapping windows of 20 completed daily observations. Post-audit rows
are excluded before inventory and partitioning, future-only files are excluded
from the frozen inventory, partial final windows are excluded, and contracts
are never stitched or resampled.

The artifact publishes two explicitly labeled populations. `all complete`
describes every 20-observation underlying window after the cutoff.
`representative eligible` contains only clean complete windows wholly inside
the audited daily option-premium coverage. Representative `quiet`, `typical`,
and `volatile` views are nearest to the eligible population's within-family
20th, 50th, and 80th total-excursion percentiles. This is a descriptive regime
slice, not a family, contract, or profitability ranking.

| Family | All complete | All clean | Representative eligible | All-clean excursion p20 | p50 | p80 | Eligible excursion p20 | p50 | p80 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SHFE.au | 405 | 405 | 186 | 3.510439 | 5.513659 | 8.238342 | 4.74125 | 7.125828 | 13.218862 |
| SHFE.ag | 651 | 651 | 319 | 7.244354 | 10.453508 | 16.309131 | 7.701257 | 12.267551 | 25.859188 |
| CZCE.TA | 379 | 351 | 26 | 6.718255 | 10.287908 | 15.228216 | 10.558009 | 13.208553 | 20.643877 |
| CZCE.MA | 379 | 345 | 30 | 6.498547 | 9.177489 | 14.301453 | 8.749162 | 9.895464 | 18.577276 |
| SHFE.cu | 750 | 750 | 324 | 4.200039 | 6.531935 | 10.85014 | 3.864811 | 6.935961 | 12.074405 |
| DCE.i | 662 | 662 | 109 | 8.514633 | 13.264768 | 24.679266 | 5.916405 | 7.157058 | 9.890476 |

Each public representative includes a deterministic 20-bar OHLC path indexed
to the first completed bar's open at 100. This makes the swing shape directly
inspectable without publishing raw prices. The views also expose dates and
normalized aggregates:

- net percentage change;
- total excursion percentage;
- annualized realized variability;
- median normalized bar range;
- up-bar share; and
- nonzero observed activity share.

They omit raw OHLC values, raw rows, source filenames, raw contract identifiers,
local paths, usernames, and credentials.

After the underlying windows are frozen, the builder overlays every anonymous
daily option series observed inside the same family and date range. It reports
distinct-date coverage percentiles, activity, and input quality. Only a series
with exactly one coherent positive observation on every one of the 20 specified
underlying dates enters the comparable premium path distributions. Duplicate
dates and incomplete fragments, including two-point fragments, are counted but
excluded. The option data cannot influence window selection. Signed premium
path change describes the same historical window; it is not a future outcome,
a selected leg, or a strategy result.

## Representative windows

The option coverage column is the p20/p50/p80 number of distinct specified
dates observed per anonymous series. `Complete comparable` is the number of
series admitted to the same-length premium path distribution.

| Family | Slice | Window | Underlying excursion | Underlying variability | Normalized bars | Option series | Option date coverage p20/p50/p80 | Complete comparable | Path status |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| SHFE.au | quiet | 2025-02-17 to 2025-03-14 | 4.74125 | 10.094746 | 20 | 364 | 20/20/20 | 134 | available |
| SHFE.au | typical | 2024-05-20 to 2024-06-17 | 7.125245 | 17.072629 | 20 | 188 | 20/20/20 | 50 | available |
| SHFE.au | volatile | 2025-03-21 to 2025-04-18 | 13.218862 | 17.654177 | 20 | 578 | 3/20/20 | 93 | available |
| SHFE.ag | quiet | 2025-06-17 to 2025-07-14 | 7.718894 | 18.417789 | 20 | 478 | 20/20/20 | 94 | available |
| SHFE.ag | typical | 2024-04-11 to 2024-05-14 | 12.267551 | 26.61903 | 20 | 100 | 20/20/20 | 24 | available |
| SHFE.ag | volatile | 2025-09-11 to 2025-10-16 | 25.854657 | 26.240711 | 20 | 826 | 10/20/20 | 78 | available |
| CZCE.TA | quiet | 2026-01-12 to 2026-02-06 | 10.558009 | 27.632817 | 20 | 83 | 3/20/20 | 1 | available |
| CZCE.TA | typical | 2025-12-16 to 2026-01-14 | 13.159041 | 21.265159 | 20 | 48 | 16.2/20/20 | 0 | unavailable |
| CZCE.TA | volatile | 2026-03-17 to 2026-04-14 | 20.643877 | 60.923298 | 20 | 289 | 20/20/20 | 16 | available |
| CZCE.MA | quiet | 2025-11-17 to 2025-12-12 | 8.853119 | 17.892814 | 20 | 44 | 20/20/20 | 0 | unavailable |
| CZCE.MA | typical | 2026-04-20 to 2026-05-20 | 9.82431 | 28.918063 | 20 | 376 | 20/20/20 | 64 | available |
| CZCE.MA | volatile | 2026-03-20 to 2026-04-17 | 18.065693 | 64.666708 | 20 | 374 | 19/20/20 | 33 | available |
| SHFE.cu | quiet | 2025-06-17 to 2025-07-14 | 3.870211 | 9.660994 | 20 | 456 | 20/20/20 | 73 | available |
| SHFE.cu | typical | 2024-08-09 to 2024-09-05 | 6.902405 | 13.763584 | 20 | 404 | 20/20/20 | 95 | available |
| SHFE.cu | volatile | 2024-07-16 to 2024-08-12 | 12.043642 | 18.501004 | 20 | 466 | 12/20/20 | 84 | available |
| DCE.i | quiet | 2025-08-12 to 2025-09-08 | 5.965147 | 20.226496 | 20 | 20 | 16/18/20 | 3 | available |
| DCE.i | typical | 2026-04-22 to 2026-05-22 | 7.157058 | 15.699863 | 20 | 206 | 20/20/20 | 86 | available |
| DCE.i | volatile | 2025-08-15 to 2025-09-12 | 9.859155 | 20.260179 | 20 | 20 | 19/19.5/20 | 3 | available |

Every representative underlying window is clean under the frozen quality rule
and stale at the fixed 2026-07-30 audit date. Every option overlay is marked
invalid because more than 20% of its observations violate the overlay rule.
TA-typical and MA-quiet publish no path distribution because no option series
passes the full 20-date comparable-path rule. Available path distributions use
only complete coherent positive series and retain the blocking overlay-quality
flag; they are inspection aids, not validated option histories.

## Availability and caveats

Issue #43 establishes underlying and option-premium OHLC presence for all six
families at daily, hourly, 15-minute, and 5-minute cadence. This packet binds
that artifact by SHA-256 rather than rescanning or copying private inputs.

| Family | Daily underlying files | Daily option files | Daily option activity share | Daily option OHLC violations |
| --- | ---: | ---: | ---: | ---: |
| SHFE.au | 40 | 1,768 | 82.1972% | 106,232 |
| SHFE.ag | 65 | 3,170 | 81.6539% | 174,034 |
| CZCE.TA | 36 | 379 | 89.9349% | 0 |
| CZCE.MA | 36 | 438 | 86.0788% | 0 |
| SHFE.cu | 72 | 1,490 | 78.9583% | 91,378 |
| DCE.i | 77 | 214 | 39.0109% | 10,140 |

The activity share is the proportion of observations with any nonzero observed
volume, turnover, or open interest. It has no selection threshold and must not
be read as a liquidity or performance rank.

The frozen underlying scan produced 3,226 complete windows, of which 994 representative-eligible
clean windows fall wholly inside the audited daily option coverage. TA
contributed 23 messy and five invalid windows; MA
contributed 31 messy and three invalid windows. The public artifact includes one
deterministic example each of clean, messy, invalid, and stale input. Messy and
invalid windows are excluded from both representative selection and normalized
paths.

The strict overlay quality rule differs from Issue #43's OHLC-coherence count.
An all-zero premium row is geometrically coherent but is not a valid positive
premium path, so the overlay records it as nonpositive rather than as an OHLC
geometry violation. The machine artifact preserves separate counts for
nonpositive/missing observations, incoherent OHLC observations, duplicate
dates, incomplete fragments, and two-point fragments.

## Strategy handoff

Inspect the quiet, typical, and volatile views for every family, keeping the
candidate roles intact:

- AU/AG are the continuity group; interpret their views alongside the large
  daily option-premium OHLC-quality caveat.
- TA/MA are the mainstream group; retain their underlying-window quality flags
  and do not mistake zero coherence violations in the broad audit for valid
  positive premium paths in every selected window.
- CU/i are non-CZCE controls; preserve CU's option-quality caveat and i's lower
  observed option-activity share.

These groups are balanced inspection lanes, not recommendations or rankings.
The appropriate next output is a research question or a separately frozen
protocol. The views themselves must not be promoted into experiment evidence.

No local-only artifact is required. The committed machine artifact contains all
18 normalized 20-bar paths, so deterministic rendering does not require private
prices. Any separate chart rendered from private data, together with source
rows, filenames, identifiers, and paths, remains outside this packet and outside
review.

## Reproduce

From the repository root, with the data root supplied explicitly at runtime:

```sh
PYTHONPATH=src python3 \
  src/scripts/build_pa_feitian_exploratory_swing_views.py \
  --contract \
    docs/research/pa-feitian-m6-exploratory-swing-views-contract-v1.json \
  --candidate-audit \
    doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json \
  --data-root "$QUANT_DATA_ROOT" \
  --output \
    doc/repro/pa-feitian-m6-exploratory-swing-views-2026-07-30/exploratory_swing_views_v1.json

PYTHONPATH=src python3 -m pytest \
  src/tests/test_pa_feitian_exploratory_swing_views.py -q

node \
  doc/repro/pa-feitian-m6-exploratory-swing-views-2026-07-30/verify.mjs
```

Set `PA_FEITIAN_PYTHON` if the project interpreter is not named `python3`.
Set `PA_FEITIAN_REGENERATE=1` together with `QUANT_DATA_ROOT` to make the
verifier require byte-identical regeneration from the external interface. The
CLI rejects outputs inside the read-only data root or equal to either input
artifact, and replaces the output atomically from a same-directory temporary
file.
