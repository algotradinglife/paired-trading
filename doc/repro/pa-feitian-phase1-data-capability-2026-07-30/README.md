# Phase 1 candidate data capability and freshness inventory

This packet answers Issue #43 from an explicit, read-only audit of the
caller-provided `QUANT_DATA_ROOT` interface. It inventories the six predeclared
families across daily, hourly, 15-minute, and 5-minute data without refreshing
or mutating the source.

The committed candidate-interface artifact contains only family/cadence
aggregates. It omits local paths, usernames, source filenames, raw contract
identifiers, raw rows, credentials, and strategy outcomes. Filesystem timestamps
are not accepted as observation freshness.

The fixed audit date is `2026-07-30` in `Asia/Shanghai`. Evidence no more than
seven calendar days old is `fresh`; evidence eight or more days old is `stale`;
and evidence without a bound latest observation is `unknown`.

## Decision

The result remains **data blocked**. Zero families are usable for frozen
`P1-EXP-001`, so Issue #45 must not start outcome work.

Unlike the earlier packet, no family is classified as unavailable merely because
an older repository aggregate omitted it. The explicit audit matched 31,141
candidate-interface files, read all of them successfully, and found underlying
and option-premium bars for every family at every declared cadence.

| Family | Underlying files per cadence | Option files per cadence | Latest option evidence | 5m option nonzero-activity rows / rows | Daily option OHLC violations | Frozen P1 usable |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| SHFE.au | 40 | 1,768 | 2026-06-16, stale | 19,106,461 / 23,587,772 (81.0016%) | 106,232 | no |
| SHFE.ag | 65 | 3,170 | 2026-06-17, stale | 26,239,408 / 32,480,047 (80.7862%) | 174,034 | no |
| CZCE.TA | 36 | 379 | 2026-06-22, stale | 1,579,285 / 1,759,109 (89.7776%) | 0 | no; outside frozen experiment |
| CZCE.MA | 36 | 438 | 2026-06-22, stale | 1,741,588 / 2,026,260 (85.9509%) | 0 | no; outside frozen experiment |
| SHFE.cu | 72 | 1,490 | 2026-06-16, stale | 13,175,995 / 16,904,905 (77.9418%) | 91,378 | no; outside frozen experiment |
| DCE.i | 77 | 214 | 2026-06-22, stale | 259,492 / 1,306,685 (19.8588%) | 10,140 | no; outside frozen experiment |

The file counts above are stable across the four declared cadences, except that
the audit also identifies one separate daily continuous-underlying interface for
SHFE.cu. DCE.i hourly and 15-minute option evidence ends on 2026-06-10 even
though its daily and 5-minute interfaces reach 2026-06-22; the machine artifact
retains each cadence separately.

All audited files expose observation timestamps and all family/cadence
interfaces report zero duplicate timestamp rows. The artifact reports schema
variants, timestamp nulls, OHLC rows checked and violations, and availability,
non-null rows, and nonzero rows for volume, turnover, and open interest.

The activity rate is descriptive only:

```text
option rows with any nonzero observed volume, turnover, or open interest
-----------------------------------------------------------------------
                           all option rows
```

It is not a minimum threshold, ranking, selection, or performance result.

## Why the experiment still fails closed

The explicit interface audit establishes broad historical data presence, not
permission to run the frozen causal experiment. All six families are stale at
the fixed audit date. AU/AG additionally remain blocked by missing exact exchange
expiry, unproven decision-time availability, unavailable causal signal-day
same-product IV history, no selected option leg bound to enrollment artifacts,
and no immutable daily enrollment ledger. Their daily option OHLC coherence
findings must also be resolved before prospective use.

TA/MA/CU/i now have limited historical research usability rather than
`unavailable` status. They still cannot replace AU/AG in `P1-EXP-001`: the
merged registry freezes that experiment to SHFE.ag and SHFE.au, and changing the
universe requires a new registry version and experiment ID.

## Artifact and M6 relationship

`candidate_interface_audit_v1.json` is the primary six-family evidence. It is
generated from the frozen candidate-interface audit contract and records a
deterministic source-inventory digest.

`candidate_capability_inventory_v1.json` binds that artifact by schema and
SHA-256, then relates it to the merged Phase 1 registry and prior M6 AU/AG option,
liquidity, continuous-provenance, underlying-corpus, retrospective-replay, and
raw-availability aggregates. Those M6 artifacts remain continuity and causal
boundary evidence; they are no longer used as a substitute for auditing the
other four families.

## Reproduce

From the repository root, with the explicit data interface supplied at runtime:

```sh
PYTHONPATH=src python3 src/scripts/build_pa_feitian_candidate_interface_audit.py \
  --contract docs/research/pa-feitian-phase1-candidate-interface-audit-contract-v1.json \
  --data-root "$QUANT_DATA_ROOT" \
  --output doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json

PYTHONPATH=src python3 -m pytest \
  src/tests/test_pa_feitian_candidate_interface_audit.py \
  src/tests/test_pa_feitian_data_capability_inventory.py -q

node doc/repro/pa-feitian-phase1-data-capability-2026-07-30/verify.mjs
```

Set `PA_FEITIAN_PYTHON` when the project interpreter is not named `python3`.
When `QUANT_DATA_ROOT` is present, the verifier rebuilds the interface aggregate
and requires byte identity; otherwise it verifies the committed aggregate and
always rebuilds the derived capability inventory.
