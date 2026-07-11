# PA / Feitian M6 historical as-of source audit

Original Hermes task: `t_efc47205` (`M6-HIST-002`)

Correction task: `t_f4920060` (`M6-HIST-002A`)

## Corrected result

The original packet's “provision eight missing D/W/60/15 files” conclusion was
wrong. Six exact candidate files already exist under the external
`quant_data/continuous` root:

- `SHFE.{au0,ag0}.5min.parquet`
- `SHFE.{au0,ag0}.option_ivskew.parquet`
- `SHFE.{au0,ag0}.regime.parquet`

This correction audits only those six paths. All six byte streams are SHA-256
pinned, all cover their applicable frozen decision dates, and no directory
discovery, contract selection, proxy, or performance evaluation is used.
Presence does not establish causal validity: every candidate remains
`data_present_but_unverified` or blocked from score input consumption.

The M4 `00:00Z` timestamps remain daily date markers. The frozen decision
cutoffs are the SHFE day-session close (`15:00 Asia/Shanghai`, `07:00Z`). The
lookback is 180 calendar days, with minimum rows `D=60`, `W=20`, `60min=120`,
and `15min=120`.

## Exact source audit

| Candidate | Schema summary | Rows | Coverage | Finding |
| --- | --- | ---: | --- | --- |
| `au0.5min` | naive `datetime`, OHLCV/turnover/OI, `main_month`, `is_roll` | 142,162 | 2021-01-04 09:00 → 2026-06-06 02:30 | Sorted, unique, coherent OHLC; 26 roll flags. |
| `ag0.5min` | same | 51,065 | 2024-07-01 09:05 → 2026-06-06 02:30 | Sorted, unique, coherent OHLC; 10 roll flags. |
| `au0.option_ivskew` | date, main month, F, ATM/25Δ IV, RR, chain counts | 468 | 2024-07-01 → 2026-06-08 | All frozen au dates present; availability/lineage unverified. |
| `ag0.option_ivskew` | same | 466 | 2024-07-01 → 2026-06-08 | All frozen ag dates present; availability/lineage unverified. |
| `au0.regime` | date, close, IV rank, ATR/RVOL/trend/flow fields, regime | 1,313 | 2021-01-04 → 2026-06-08 | Dates present; causal regime capability blocked. |
| `ag0.regime` | same | 1,313 | 2021-01-04 → 2026-06-08 | Dates present; causal regime capability blocked. |

The Parquet metadata contains only Arrow/Pandas schema metadata. It does not
bind generator code, raw input identities, source query cutoff, roll schedule,
timezone/availability contract, or parameters. Hashes pin source identity, but
not lineage.

### Roll provenance

`main_month` and `is_roll` are internally consistent: every flag equals a
month change. They are not proven trading-day provenance. For au, 23 of 26
changes are annotated at `00:00`; for ag, 9 of 10 are at `00:00`. Midnight is
inside the CN night trading session, so these calendar-date annotations cannot
be treated as a proven causal trading-day roll ledger.

The located, hash-recorded generator candidate claims prior-session OI/volume
selection plus three-session confirmation. Candidate Parquet metadata does not
prove that this code and its raw input panel generated the pinned bytes.

### Strict-as-of aggregation

The tested audit implementation localizes the claimed naive Shanghai 5-minute
period-end timestamps, filters `timestamp <= decision_ts` before deriving any
calendar or aggregate, assigns CN night/day trading-minute offsets, and then
deterministically derives candidate D/W/60/15 bars. Appending extreme
post-decision rows leaves every output byte-identical in focused tests.

All 16 decision/level cells exceed their frozen minimum row count. Observed
ranges are D `111–118`, W `25–26`, 60min `1,084–1,155`, and 15min
`3,998–4,260`. This promotes only `strict_asof_aggregation_mechanics`; the
aggregated candidates remain quarantined because roll and session provenance
are not proven.

### IV and regime causality

The IV/skew files are date-only. They do not state when same-day option closes,
maturity data, chain membership, main-month schedule, rates, or raw option
inputs became available. Causal IV is therefore
`data_present_but_unverified`, not supported.

The regime files are also date-only and lack lineage. Moreover, the located
unbound generator computes the stress threshold using the full-series ATR 80th
percentile. That implementation is not prefix-causal, so the regime capability
remains blocked. No upstream IV/regime metric is imported as evidence.

## Capability boundary

| Capability | Status |
| --- | --- |
| Exact six-file byte identity pinning | `supported` |
| Filter-first deterministic D/W/60/15 aggregation mechanics | `supported` |
| Underlying OHLCV as causal score input | `data_present_but_unverified` |
| Continuous roll provenance | `data_present_but_unverified` |
| Causal IV | `data_present_but_unverified` |
| Causal regime | `blocked` |
| Decision-time delta / exact DTE | `blocked` |
| Option premium intraday cadence | `blocked` |
| DD-line | `blocked` |
| Historical bid/ask | `blocked` |

The trade-philosopher references remain independent, non-transferable context;
trade-philosopher was not modified and no upstream performance metric was used.

## Immutable artifacts

| Artifact | SHA-256 |
| --- | --- |
| Amended frozen protocol | `sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d` |
| Quarantined historical as-of candidates | `sha256:0622d75ec43347c1143dfc5ea7088167acac397785a0504fd024398e907cadd6` |
| Coverage/feasibility/source audit | `sha256:3639f224e41e5fe205184088a0a0724529b2a6fc005d8e2d5410dbb5d20c07f8` |

## Verify

```bash
QUANT_DATA_ROOT=/path/to/quant_data \
PA_FEITIAN_PYTHON=/tmp/paired-trading-m6-venv/bin/python \
  node doc/repro/pa-feitian-m6-historical-asof-2026-07-11/verify.mjs
```

The verifier reads only `${QUANT_DATA_ROOT}/continuous/<six pinned names>`,
checks their hashes and schemas, rebuilds both artifacts byte-for-byte, enforces
the capability quarantine and no-M7 gates, and validates source-code guards.

## Exact next gate

Produce a generator manifest binding each of the six pinned candidate hashes to
immutable generator/source commits, exact raw-input hashes, query/build cutoff,
timezone and period-end contract, and the causal prior-session roll schedule.
Repair `main_month/is_roll` to trading-date semantics and prove prefix
invariance.

Then replace the regime full-sample ATR threshold with a declared expanding or
trailing causal threshold, attach explicit availability timestamps to IV and
regime rows, and prove prefix invariance before promotion. D/W/60/15 mechanics
need no new files, but cannot enter `score_today` until source provenance passes.
Faithful Feitian remains separately blocked on decision-time delta/exact DTE,
option `<=15min` premiums, a formal DD-line definition, and historical bid/ask.
