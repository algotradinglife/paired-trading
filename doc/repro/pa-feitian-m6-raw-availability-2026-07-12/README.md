# PA / Feitian M6 raw historical-availability audit

Hermes task: `t_550fa726`

This packet reads the merged M6-HIST/M6-PROV evidence and audits the exact 210
raw inputs behind the two underlying candidates. It makes no IV/regime,
scoring, performance, execution, or M7 change.

## Result

The required acquisition evidence is absent for every input, so quarantine is
retained. Zero of 210 raw files can be proved available at any frozen
historical `as_of`.

| Raw group | Files | Complete acquisition evidence | Result |
| --- | ---: | ---: | --- |
| au daily schedule inputs | 40 | 0 | quarantined |
| au constituent 5-minute inputs | 40 | 0 | quarantined |
| ag daily schedule inputs | 65 | 0 | quarantined |
| ag constituent 5-minute inputs | 65 | 0 | quarantined |
| **Total** | **210** | **0** | **quarantined** |

Each record in `raw_availability_blocker_v1.json` pins the existing raw SHA-256,
observation bounds, metadata keys, and the same six exact blocker codes:

- `missing_source_identity`: no per-file provider/source identity is bound.
- `missing_vendor_response_identity`: no immutable response/request ID or raw
  response hash is bound.
- `missing_query_parameters`: no per-file symbol, interval, start/end, fields,
  adjustment, pagination, or equivalent request contract is bound.
- `missing_acquired_at`: no trustworthy acquisition timestamp is bound.
- `missing_query_cutoff`: no source query/build cutoff is bound. The maximum
  timestamp inside a file is an observation bound, not query-time evidence.
- `missing_raw_timestamp_timezone_contract`: raw naive timestamps carry no
  per-file vendor timezone/session/stamp contract. The downstream generator's
  declared `Asia/Shanghai` interpretation does not establish raw-source
  lineage.

All 210 Parquets contain only `ARROW:schema` file metadata. No acquisition
sidecar or per-file lineage manifest was found in the external data root. The
external quant source contains possible fetcher/provider implementations, but
none binds a particular provider call or response to any of these pinned byte
streams. That code therefore cannot fill a per-file evidence field.

Filesystem modification times were inspected only as a diagnostic and are not
accepted as provenance: the current files' mtimes span 2026-06-08 through
2026-06-18 UTC, after all four frozen decisions (2026-03-13, 2026-03-18,
2026-05-15, and 2026-06-02). A copied or rewritten file can change mtime, so
this observation cannot prove original acquisition time; it only reinforces
that the present filesystem offers no historical-availability proof. Mtimes
are deliberately excluded from the deterministic JSON packet.

## Roll validation

The pinned prior-session schedule itself is mathematically causal:

- choose prior-session settlement OI only when every active contract has
  positive OI, otherwise choose prior-session volume;
- require three consecutive prior-session wins by the same challenger;
- make the roll effective on the next exchange trading session;
- key the schedule by exchange trading date, including the night session.

An independent online reference matched the pinned full schedule at every
session prefix: 1,313/1,313 for au and 1,313/1,313 for ag (2,626 total, zero
failures). The canonical trading-date schedule hashes remain
`64ae4fc5…c69379` (au) and `d9fedf5f…7b561` (ag).

This does not prove the raw OI/volume observations were historically available.
It also does not repair the frozen candidates: their embedded `main_month` and
`is_roll` were joined by calendar date and remain quarantined. Thus the result
is `supported_conditional_on_raw_bytes` for the separate causal schedule, not
promotion of the underlying candidates.

## Immutable evidence

| Artifact | SHA-256 |
| --- | --- |
| M6-HIST protocol | `sha256:1ee6e334ada94fa928d311f3d7992d1708e4334c5b16e8e39b51ffedafcd7a1d` |
| M6-PROV manifest | `sha256:a239a15d7f11bfacac0565a32e6f6bb5895ff8c5815cf5138926722590ffd3a3` |
| Raw availability blocker | `sha256:a0f9b91b86b33bfdf97d9fc325435a8b8f6cdf8925eb5464edbea9c3494939ee` |

## Verify

```bash
QUANT_DATA_ROOT=/path/to/quant_data \
PAIRED_REPO=/path/to/paired-trading \
PA_FEITIAN_PYTHON=/path/to/python \
  node doc/repro/pa-feitian-m6-raw-availability-2026-07-12/verify.mjs
```

The verifier reads only the 210 manifest-listed raw paths and the pinned
committed continuous-source blob. It rejects raw hash/metadata drift, packet
drift, any prefix mismatch, incomplete enumeration, an evidence upgrade, score
eligibility, performance evaluation, IV/regime promotion, execution change, or
M7 advance. External repositories and data are never written.

## Exact next gate

For every one of the 210 pinned inputs, provide an immutable acquisition record
binding source/provider identity, vendor response identity, complete query
parameters, trustworthy acquisition time, query cutoff, and raw timestamp
timezone/session semantics. That record must prove the observation existed no
later than each applicable historical decision cutoff. Then generate corrected
continuous candidates whose embedded roll fields use exchange trading dates
and re-run prefix verification before considering underlying promotion.
