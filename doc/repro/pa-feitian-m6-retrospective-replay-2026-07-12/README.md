# PA / Feitian M6 retrospective-finalized replay gate

Hermes task: `t_23c01908`

## Correction

The prior raw-availability audit correctly found that none of the 210 pinned
raw inputs has acquisition metadata. Its gate was too broad: absence of an
append-only acquisition manifest blocks a claim that an operator could have
observed that exact dataset vintage at a historical decision, but it does not
block research on finalized historical data when every input is strictly
truncated at the decision timestamp.

This packet separates two claim modes:

| Mode | Missing acquisition metadata | Causal reconstruction / roll reuse | Result |
| --- | --- | --- | --- |
| `retrospective_finalized` | attached limitation, not a blocker | allowed | `enabled_with_explicit_limitations` |
| `operational_observability` | hard blocker | forbidden as proof | `blocked` |

Append-only acquisition manifests belong to M8. M6 neither creates nor
requires them for the limited retrospective claim.

## No-lookahead contract

The replay contract freezes the same four decisions and only the two already
validated underlying candidates. For each decision it requires:

- exact source, raw-input-set, and causal trading-date roll-schedule hashes;
- `timestamp <= decision_ts_utc` filtering before calendar assignment,
  resampling, or any other derivation;
- the declared prior-session OI/volume rule, three-session confirmation, and
  next-session roll effectiveness;
- no discovery, contract selection, contract reselection, proxy, or
  imputation;
- no consumption of the candidates' quarantined calendar-date
  `main_month/is_roll` annotations.

The four evidence rows explicitly attach the remaining revision and
observability limitations: finalized bytes may include later corrections;
historical vendor visibility, deletions, restatements, and survivorship are
unproven.

## Narrowest capability enabled

Finalized-vintage, decision-time-truncated descriptive D/W/60/15 underlying
replay for the four frozen au/ag decisions, using only the hash-pinned
continuous reconstruction and declared causal roll schedule.

This is a reconstruction and coverage capability, not a performance or
strategy-screening result. It does not promote date-only IV/regime, options or
option premiums, delta/DTE, DD-line, bid/ask, `score_today`, M7, or execution.

## Immutable evidence

| Artifact | SHA-256 |
| --- | --- |
| Epistemic replay contract | `sha256:f6f3daa7a1dae99bc2e69a5a3471802173fad1f1333c814ec1152802592a0290` |
| Retrospective replay evidence | `sha256:eaeb6c3fffa93115c4fc7a0f8b86abbabed5e776bdd8f3c139826150f51a12fb` |
| Historical as-of protocol | `sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d` |
| Strict-as-of source audit | `sha256:3639f224e41e5fe205184088a0a0724529b2a6fc005d8e2d5410dbb5d20c07f8` |
| Continuous provenance | `sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3` |
| Raw availability audit | `sha256:a0f9b91b86b33bfdf97d9fc325435a8b8f6cdf8925eb5464edbea9c3494939ee` |

## Verify

```bash
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-retrospective-replay-2026-07-12/verify.mjs
```

The verifier uses committed JSON only; it reads no external raw data. It
rebuilds the evidence, verifies every predecessor hash, enforces both claim
modes, and rejects future-row, reselection, capability-promotion, M7, and
execution drift.
