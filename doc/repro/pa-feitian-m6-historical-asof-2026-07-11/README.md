# PA / Feitian M6 historical as-of input lane

Hermes task: `t_efc47205` (`M6-HIST-002`)

## Result

This packet freezes a coverage/feasibility lane for the four immutable
`M6-HIST-001` ag/au decisions, the two-symbol SHFE universe, and four required
underlying levels (`D`, `W`, `60min`, `15min`) with a 120-calendar-day
lookback and frozen minimum row counts of 60, 20, 120, and 120 respectively.
It does not run `score_today`, detector logic, an option selector,
an outcome traversal, or any performance evaluation.

The M4 `00:00Z` signal timestamps are daily date markers rather than market
availability instants. The protocol therefore freezes the causal cutoff at the
SHFE day-session close (`15:00 Asia/Shanghai`, `07:00Z`) on each signal date.
This permits the completed daily signal bar without pretending it was known at
midnight; intraday inputs remain bounded by the same cutoff.

The reusable builder reads only the eight exact mapped underlying paths. Every
load requires the frozen UTC decision timestamp as `as_of` and `end`; continuous
contract synthesis, JSON fallback, raw-store globbing, option catalog discovery,
and contract selection/reselection are disabled. The artifact verifier rejects
any bar timestamp after its decision timestamp.

At the frozen run, the current paired-trading quant store contained zero files
in the relevant `daily`, `weekly`, `hour`, and `min15` directories. Coverage is
therefore `0 / 16` requested decision-series snapshots, with all 16 classified
`data_blocked`; nothing is imputed. Focused synthetic tests separately prove
that the supported underlying lane emits only rows at or before `as_of`.

## Capability boundary

| Capability | Status | Boundary |
| --- | --- | --- |
| Underlying OHLCV as-of snapshots | `supported` | Exact-path `BarStore` load with explicit UTC `as_of`; actual frozen coverage is zero. |
| Decision-time delta / exact DTE | `blocked` | No bounded CN delta series or exact exchange expiry contract; `% OTM` and approximate expiry are not substituted. |
| Causal IV | `blocked` | No pinned decision-time IV history and causal warmup; no Black-Scholes or upstream metric proxy. |
| Regime | `blocked` | No frozen causal CN Feitian regime-label contract; upstream labels are not imported. |
| Option price cadence | `blocked` | Current paired-trading OptionStore is daily-only and the frozen store is empty; DD/tight-stop work requires option 15-minute or finer bars. |
| DD-line | `blocked` | Neither a frozen DD-line definition nor bounded option intraday inputs exist; generic swing/percent stops are not proxies. |
| Bid/ask | `blocked` | Current schemas have no historical bid/ask; costs are not invented. |

The four hash-pinned trade-philosopher documents from `M6-HIST-001` were read
at source commit `5802d0ff5d99819ad01ba9f3550b6a2d504f1e81`. They remain
independent, non-transferable research context. No upstream performance metric
or implementation was imported, and trade-philosopher was not modified.

## Immutable artifacts

| Artifact | SHA-256 |
| --- | --- |
| Frozen protocol | `sha256:55652f37b93db653b3259fb6e1a419565ba00d6101a83a66fb99b74edc57c7dc` |
| Historical as-of inputs | `sha256:4eaa7251174a28fa1ae75bb0ca9425aaeb23725ff5f3f44e7b284bfd3f42cfe6` |
| Coverage/feasibility audit | `sha256:aeef4ad05ede7c4f988d1374cba560dc389453cdf99afbeb63782efe9acf77f1` |

## Verify

```bash
PA_FEITIAN_PYTHON=/tmp/paired-trading-m6-venv/bin/python \
  node doc/repro/pa-feitian-m6-historical-asof-2026-07-11/verify.mjs
```

The verifier checks pinned bytes and public-path hygiene, validates all causal
guards and timestamps, confirms the exact capability classification, scans the
builder source for implicit current-date calls, and rebuilds both artifacts
byte-for-byte against a fresh empty explicit root.

## Exact next gate

Provision the exact eight frozen underlying files (`au0` / `ag0` × `D` / `W` /
`60min` / `15min`) with provenance sufficient to cover all 16 requested
decision-series snapshots through their decision timestamps, then rerun this
verifier.

That gate enables bounded PA input generation only. Faithful Feitian evaluation
remains separately blocked until a new protocol pins decision-time CN delta and
exact DTE, causal IV warmup/history, causal regime labels, option `<=15min`
bars, a formal DD-line definition, and historical bid/ask.
