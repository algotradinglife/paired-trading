# PA / Feitian M6 liquid-premium OHLC evidence

Hermes task: `t_3bf64f0c`

The eligibility contract was frozen and committed as `315bf4f` before any
external repository or option-bar inspection. This packet classifies every
AU/AG option contract-local-date unit in the frozen 2025-01-02 through
2026-06-08 window at 5-minute and 15-minute cadence. Thresholds were not
selected or revised from premium paths, outcomes, or strategy performance.

## Exact M6 boundary

This is an exploratory naked-option premium-K-line lane. Historical bid/ask
and contract delta are absent, are not model inputs, and are neither required
nor proxied. Exact expiry/DTE is optional metadata when explicit, not an
eligibility gate. Finalized historical rows are permitted for M6 research when
all metrics are strictly truncated to the inclusive 15:00 Asia/Shanghai
event-time cutoff. Append-only acquisition lineage remains necessary only for
later operational-observability claims.

The evidence makes no claim about spreads, slippage, executable fills, market
impact, execution readiness, or contemporaneous availability. It performs no
contract selection, premium-path evaluation, candidate screening, strategy
performance evaluation, M7, M8, or execution work. A faithful frozen DD-line
remains absent, so this lane is not faithful Feitian replication.

## Frozen ex-ante gate

A contract-local-date unit is eligible only when all of these pass using rows
at or before 15:00:

- the filename supplies deterministic AU/AG month, call/put, and strike identity;
- the eight K-line columns are present, finite, non-negative, OHLC-coherent,
  timestamp-ordered, and unique;
- an exact 15:00 bar exists;
- the 14:00-15:00 expected grid has at least 80% coverage (at least 11 points
  for min5 or 4 for min15) and no adjacent gap longer than two cadence units;
- same-local-date cumulative volume is at least 100, turnover is positive,
  and latest open interest is at least 500.

The volume/OI floors are the predeclared Xiao bare-K floors. Turnover and
continuity are deterministic integrity gates derived from the committed data
access and instrument-quality context. Zero-activity rows remain in the
denominator and no later row can change a unit's decision.

## Public-safe aggregate results

| Product | Cadence | Source files | Contract-date units | Eligible | Ineligible | Eligible rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| AU | min5 | 1,768 | 196,996 | 10,779 | 186,217 | 5.47% |
| AG | min5 | 3,167 | 301,220 | 14,975 | 286,245 | 4.97% |
| AU | min15 | 1,768 | 196,996 | 8,804 | 188,192 | 4.47% |
| AG | min15 | 3,167 | 301,220 | 12,521 | 288,699 | 4.16% |

Combined, min5 has 25,754 eligible units out of 498,216 (5.17%); min15 has
21,325 out of 498,216 (4.28%). Failure counts in the JSON are non-exclusive:
a unit may fail continuity, activity, and OI simultaneously. Low activity and
OI are descriptive eligibility failures, not evidence about subsequent
premium performance.

The committed artifact contains only four product/cadence aggregates,
public-safe source aliases, and aggregate inventory digests. It contains no
absolute paths, local usernames, credentials, raw rows, or per-contract
results.

## Verify

Quick committed-boundary verification:

```bash
node doc/repro/pa-feitian-m6-liquid-premium-2026-07-12/verify.mjs
```

Optional full byte-identical regeneration (read-only, approximately one hour
on the current mounted store):

```bash
PA_FEITIAN_REGENERATE=1 \
QUANT_DATA_ROOT=/path/to/quant-data \
QUANT_REPO=/path/to/quant-repository \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-liquid-premium-2026-07-12/verify.mjs
```

The focused tests separately prove that appending a post-cutoff extreme-price
row cannot alter eligibility and that weakening the frozen activity floor is
rejected.

## Next gate

If premium-path research is desired, freeze a separate protocol before using
only these eligible bare-K units. That protocol must preserve contract/date
population membership and thresholds without outcome reselection. A faithful
Feitian claim still requires a separately frozen faithful DD-line; it does not
require introducing bid/ask, delta, or DTE into this bare-K model boundary.
