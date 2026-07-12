# PA / Feitian M6 liquid-premium unit membership

Hermes task: `t_02ba3dea`

The versioned membership contract was committed as
`e81d283fac967db06932cd2bc3bdf5eeab8e8ef4` before any external option file
was inspected. It binds the merged M6 eligibility contract and aggregate
evidence by SHA-256 and applies their rules without changing the finalized
vintage, inclusive 15:00 Asia/Shanghai cutoff, or no-bid/ask, no-delta and
no-DTE bare-K boundary.

## Result

The artifact contains 47,079 eligible contract-local-date-cadence identities:

| Product | Cadence | Source files | Contract-date units | Eligible members | Ineligible omitted |
| --- | --- | ---: | ---: | ---: | ---: |
| AU | min5 | 1,768 | 196,996 | 10,779 | 186,217 |
| AG | min5 | 3,167 | 301,220 | 14,975 | 286,245 |
| AU | min15 | 1,768 | 196,996 | 8,804 | 188,192 |
| AG | min15 | 3,167 | 301,220 | 12,521 | 288,699 |

Every member carries exactly `product`, `local_date`, `underlying_month`,
`option_type`, `strike`, `cadence`, and a public-safe `source_alias`. This is
enough to join an explicit PA alert by product/date and then retain every
eligible alert-consistent unit in the already-frozen observation order. It
does not rank or select a month, strike, contract, side, or cadence.

The four source inventories reconcile byte-for-byte to the frozen filename
inventory digests. The evidence additionally pins each partition with a
content-manifest digest over sorted relative filenames and source-file hashes;
neither local paths nor raw bytes are published.

## Missing-data and access semantics

The builder accepts one explicit data root and reads only direct, non-symlink
files under its `min5` and `min15` children that match the frozen AU/AG
identity regex. It never searches a parent, sibling, recursive directory, or
implicit current-time location.

A missing or extra inventory file, digest mismatch, unreadable file, or
missing required schema aborts before an artifact is written. A readable file
with no rows in the frozen window contributes zero units. An ineligible unit
is omitted, never imputed. There is no partial output, cadence resampling,
cadence substitution, contract substitution, or post-cutoff admission.

## Exact boundary and limitations

This packet contains membership evidence only. It contains no OHLC values,
raw market rows, premium paths, option outcomes, rankings, chosen contract,
PA alert changes, bare-K/DD-line confirmation, Greeks, delta, DTE, bid/ask,
model price, PnL, win rate, tuning, M7/M8, or execution result.

Finalized historical rows may include later revisions and do not prove
contemporaneous operational availability. K-line eligibility does not prove
an executable quote. Membership does not establish a faithful Feitian result;
an authentic machine-testable bare-K or DD-line rule remains unrecovered.

## Verify

Verify committed hashes, counts, exact fields, uniqueness, ordering, and
public safety without external data:

```bash
node doc/repro/pa-feitian-m6-unit-membership-2026-07-12/verify.mjs
```

Optional byte-identical read-only regeneration:

```bash
PA_FEITIAN_REGENERATE=1 \
QUANT_DATA_ROOT=/path/to/quant_data \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-unit-membership-2026-07-12/verify.mjs
```

## Next gate

The explicit PA alert corpus may now be joined to this hash-pinned membership
artifact. Do not inspect any premium path until an authentic machine-testable
bare-K or DD-line definition is recovered and a successor observation
contract is frozen first.
