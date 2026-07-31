# M6R blind historical bare-K episode pack

This packet is the Issue #64 Data handoff for M6R hypothesis recovery. It is
an observation material pack, not a strategy artifact. It does not define a
bare-K rule, produce signals, calculate PnL/EV/win rate, rank families, approve
a hypothesis, authorize M7, or authorize execution.

## First-pass procedure

1. Open only `blind_episode_pack_v1.json` and
   `blind_annotation_template_v1.json`.
2. For every anonymous `episode_id`, make a first-pass structural observation
   using only relative bars `-39` through `0` and normalized OHLC.
3. Save the now-complete annotation document outside this repository.
4. Only then run the explicit reveal command below with the acknowledgement
   flag. It validates that every episode was annotated before it writes the
   decoded reveal payload.

Do not open the coverage report, manifest, sealed reveal, repository history,
or source inventory while performing first-pass annotation. The blind packet
has a strict structural surface: each episode exposes only anonymous
`episode_id`, relative bar indices, and normalized pre-anchor OHLC. It contains
no family, exchange, product, source commitment, calendar date, era, sampling
label, future path, or reveal metric. The annotation template likewise contains
only an episode id and a blank annotation.

The sealed reveal is base64-encoded canonical JSON, **not encryption**. Its
separate file and annotation-gated command provide a deliberate review-order
boundary; they are not access control against a repository reader.

## Materialization method

The builder reads the explicit `QUANT_DATA_ROOT/daily` underlying daily OHLC,
volume, and open-interest interface in read-only mode. It selected nine liquid
families from the verified local inventory: three SHFE non-precious industrial
or ferrous families, three DCE industrial/agricultural families, and three
CZCE industrial/agricultural families. No precious-metal family is required or
used.

Each candidate stays inside one native underlying contract series. It has 40
completed blind daily bars, an anchor bar at relative index zero, and 20 later
daily bars placed only in the sealed reveal. There is no contract stitching,
resampling, forward fill, repair, synthetic row, or jump across a missing or
invalid row. Native timestamps and source values remain unchanged at the input;
the public display is a deterministic normalized rendering committed to
SHA-256 native-slice hashes in the reveal provenance.

The pack uses four fixed historical eras. In each family/era, it chooses one
`candidate_activity` window with the highest **causal**, trailing-20-bar median
normalized range, and one `ordinary_control` nearest that family/era causal
median. Both require positive median daily volume and open interest on the
trailing score window. A complete, valid 20-bar reveal window is an
eligibility/materialization gate only: it checks row availability and quality,
not future direction, magnitude, strategy outcomes, or profitability. Ranking,
candidate-activity/control choice, anonymous IDs, and tie-breaking use only
blind-window data. Within an instrument family, selected full blind-plus-reveal native
calendar intervals cannot overlap even when the candidate rows came from
different expiries; cross-family windows remain independent.

## Coverage and exclusions

The frozen real-data build found 485 readable daily source series and 12,828
eligible causal anchors. It publishes 72 episodes: 8 per family, 36
candidate-activity, and 36 ordinary-control. All nine families and all three
exchanges have 8 selected episodes.

| Family | Eligible anchors | Selected | Material exclusions |
| --- | ---: | ---: | --- |
| SHFE.cu | 2,180 | 8 | outside frozen strata; short source series |
| SHFE.al | 1,993 | 8 | outside strata; activity gate; short source series |
| SHFE.rb | 2,157 | 8 | outside strata; short source series |
| DCE.p | 1,052 | 8 | outside strata; short source series |
| DCE.m | 975 | 8 | outside strata; activity gate; invalid blind/reveal window; short source series |
| DCE.pp | 1,476 | 8 | outside strata; invalid blind/reveal window; short source series |
| CZCE.TA | 977 | 8 | outside strata; invalid blind/reveal window; short source series |
| CZCE.MA | 1,020 | 8 | outside strata; invalid blind/reveal window; short source series |
| CZCE.CF | 998 | 8 | outside strata; activity gate; invalid blind/reveal window; short source series |

The machine-readable coverage report contains exact reason counts by family,
exchange, date range, and source status. If a file disappears after discovery,
becomes unreadable, changes during capture, lacks a required field, or has no
pre-audit row, the builder records an explicit exclusion and never falls back
to a substitute interface. A missing or invalid row invalidates every blind or
reveal window that would span it.

## Artifacts

- `blind_episode_pack_v1.json` — first-pass anonymous normalized candles.
- `blind_annotation_template_v1.json` — one blank annotation slot per blind ID.
- `sealed_reveal_pack_v1.json` — sealed mapping, future normalized path, and
  descriptive reveal metrics.
- `coverage_and_exclusions_v1.json` — public aggregate source, family,
  exchange, date-range, and exclusion accounting; no episode mapping.
- `episode_manifest_v1.json` — byte bindings and required review order; no
  episode mapping.

## Reproduce and reveal

From the repository root, with the data root supplied explicitly at runtime:

```sh
PYTHONPATH=src "$PA_FEITIAN_PYTHON" \
  src/scripts/build_pa_feitian_m6r_historical_bare_k_episode_pack.py \
  --contract \
    docs/research/pa-feitian-m6r-historical-bare-k-episode-pack-contract-v1.json \
  --data-root "$QUANT_DATA_ROOT" \
  --output-directory \
    doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31

PYTHONPATH=src "$PA_FEITIAN_PYTHON" -m pytest \
  src/tests/test_pa_feitian_m6r_historical_bare_k_episode_pack.py -q

node doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31/verify.mjs
```

After all annotations are nonempty, decode the reveal to an external working
location. The reveal CLI rejects every output target inside this repository,
including the blind pack, manifest, contract, and sealed artifact directory:

```sh
PYTHONPATH=src "$PA_FEITIAN_PYTHON" \
  src/scripts/reveal_pa_feitian_m6r_historical_bare_k_episode_pack.py \
  --sealed-reveal \
    doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31/sealed_reveal_pack_v1.json \
  --blind-annotations "$BLIND_ANNOTATIONS_FILE" \
  --output "$REVEAL_OUTPUT_FILE" \
  --acknowledge-first-pass-complete
```

Set `PA_FEITIAN_PYTHON` to the project interpreter path when needed. The
builder replaces each output atomically and rejects an output directory inside
the read-only data root. To demand a byte-identical real-data rebuild, use
`node verify.mjs --data-root "$QUANT_DATA_ROOT"`.

## Strategy handoff

Strategy should annotate the blind shapes first, then compare the completed
annotations with the sealed provenance and descriptive future paths. The valid
output of that review is a research question or a separately reviewed
hypothesis. It must not be treated as a recovered Feitian rule, a trading
recommendation, a performance result, or an approval gate.
