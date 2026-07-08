# PA Feitian Structured Decision Trace v1 Design Note

Status: design only
Date: 2026-07-08
Owner scope: CONTRACT-FOLLOWUP-001

## Scope

This note defines a proposed structured `decision_trace` v1 shape for future
PA / Feitian snapshots. It does not change current runtime behavior, producer
output, fixtures, dashboard parsing, or `pa_feitian_snapshot_v0`.

The current v0 contract must remain stable:

- `src/engine/pa_feitian/contract.py` defines
  `PaFeitianSignal.decision_trace` as `str | None`.
- `doc/schemas/pa_feitian_snapshot_v0.schema.json` defines
  `signals[].decision_trace` as `string | null`.
- v0 models and schema both reject extra fields.

Because of that, a structured object must not be added to
`pa_feitian_snapshot_v0` and the type of `decision_trace` must not be changed in
v0. Any implementation should ship as a new snapshot contract version or as a
shadow sidecar that does not claim to be v0.

## Contract decision

Use a future `pa_feitian_snapshot_v1` contract for structured traces:

- Keep `signals[].decision` as the compact action label:
  `take`, `skip`, `watch`, or `null`.
- Keep `signals[].decision_trace` as a short human-readable summary string for
  dashboards, diffs, and backward-friendly display.
- Add `signals[].decision_trace_v1` as a machine-readable object.
- Keep all existing v0 outcome separation fields unchanged:
  `underlying_r_outcome`, `premium_r_outcome`, `option_runner_outcome`, and
  `proxy_outcome`.

Recommended field placement in v1:

```json
{
  "schema_version": "pa_feitian_snapshot_v1",
  "signals": [
    {
      "decision": "watch",
      "decision_trace": "score_today:breakout score=0.64 policy=PA-top selected=none status=data_blocked",
      "decision_trace_v1": {
        "trace_version": "decision_trace_v1",
        "action": "watch",
        "status": "data_blocked",
        "summary": {
          "headline": "underlying signal accepted; premium entry blocked",
          "primary_blocker": "premium_entry_missing",
          "selected_option_contract": null,
          "confidence": null
        },
        "input_refs": [
          {
            "id": "scorecard_record:17",
            "kind": "scorecard_record",
            "source": "score_today_json",
            "record_index": 17,
            "asof_ts_utc": "2026-06-30T02:00:00Z",
            "digest": "sha256:<optional-record-digest>"
          }
        ],
        "nodes": [
          {
            "id": "underlying_signal",
            "kind": "signal",
            "label": "Score Today underlying signal",
            "status": "pass",
            "decision_effect": "promote",
            "reason": "source scorecard emitted an option candidate",
            "evidence": [
              {
                "key": "score",
                "value": 0.64,
                "source_ref": "scorecard_record:17"
              }
            ]
          },
          {
            "id": "premium_entry",
            "kind": "gate",
            "label": "Premium entry availability",
            "status": "blocked",
            "decision_effect": "block",
            "reason": "selected option leg lacks option_price",
            "evidence": [
              {
                "key": "option_price",
                "value": null,
                "source_ref": "scorecard_record:17"
              }
            ]
          }
        ]
      }
    }
  ]
}
```

## Schema draft

The implementation card should materialize this as
`doc/schemas/pa_feitian_decision_trace_v1.schema.json` and reference it from a
new `doc/schemas/pa_feitian_snapshot_v1.schema.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/algotradinglife/paired-trading/doc/schemas/pa_feitian_decision_trace_v1.schema.json",
  "title": "PA / Feitian Decision Trace v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "trace_version",
    "action",
    "status",
    "summary",
    "input_refs",
    "nodes"
  ],
  "properties": {
    "trace_version": {
      "const": "decision_trace_v1"
    },
    "action": {
      "type": [
        "string",
        "null"
      ],
      "enum": [
        "take",
        "skip",
        "watch",
        null
      ]
    },
    "status": {
      "$ref": "#/$defs/signal_status"
    },
    "summary": {
      "$ref": "#/$defs/summary"
    },
    "input_refs": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/input_ref"
      }
    },
    "nodes": {
      "type": "array",
      "minItems": 1,
      "items": {
        "$ref": "#/$defs/node"
      }
    }
  },
  "$defs": {
    "signal_status": {
      "enum": [
        "keep",
        "drop",
        "advisory",
        "data_blocked",
        "model_dominated"
      ]
    },
    "summary": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "headline",
        "primary_blocker",
        "selected_option_contract",
        "confidence"
      ],
      "properties": {
        "headline": {
          "type": "string"
        },
        "primary_blocker": {
          "type": [
            "string",
            "null"
          ]
        },
        "selected_option_contract": {
          "type": [
            "string",
            "null"
          ]
        },
        "confidence": {
          "type": [
            "number",
            "null"
          ],
          "minimum": 0,
          "maximum": 1
        }
      }
    },
    "input_ref": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "id",
        "kind",
        "source"
      ],
      "properties": {
        "id": {
          "type": "string"
        },
        "kind": {
          "enum": [
            "scorecard_record",
            "option_chain_row",
            "iv_history",
            "policy_rule",
            "producer_config"
          ]
        },
        "source": {
          "type": "string"
        },
        "record_index": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0
        },
        "asof_ts_utc": {
          "type": [
            "string",
            "null"
          ],
          "format": "date-time"
        },
        "digest": {
          "type": [
            "string",
            "null"
          ],
          "pattern": "^sha256:"
        }
      }
    },
    "node": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "id",
        "kind",
        "label",
        "status",
        "decision_effect",
        "reason",
        "evidence"
      ],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[a-z0-9_:-]+$"
        },
        "kind": {
          "enum": [
            "signal",
            "gate",
            "selection",
            "policy",
            "outcome_annotation"
          ]
        },
        "label": {
          "type": "string"
        },
        "status": {
          "enum": [
            "pass",
            "fail",
            "blocked",
            "advisory",
            "not_applicable"
          ]
        },
        "decision_effect": {
          "enum": [
            "promote",
            "demote",
            "block",
            "annotate",
            "none"
          ]
        },
        "reason": {
          "type": [
            "string",
            "null"
          ]
        },
        "evidence": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/evidence"
          }
        }
      }
    },
    "evidence": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "key",
        "value",
        "source_ref"
      ],
      "properties": {
        "key": {
          "type": "string"
        },
        "value": true,
        "source_ref": {
          "type": [
            "string",
            "null"
          ]
        }
      }
    }
  }
}
```

## Node ordering and minimum node set

Nodes should be emitted in causal order. A producer can omit nodes that were not
evaluated, but the following IDs should be stable when the relevant inputs
exist:

| Node ID | Kind | Purpose |
| --- | --- | --- |
| `underlying_signal` | `signal` | Source PA / Feitian signal and scorecard context. |
| `policy_rule` | `policy` | Policy rule, weight, and reason for action class. |
| `option_selection` | `selection` | Selected option contract, side, strike, DTE, rank, delta estimate. |
| `iv_regime` | `gate` | Causal IV rank and keep/drop reason. |
| `premium_entry` | `gate` | Whether premium entry price was available without lookahead. |
| `exit_policy` | `policy` | Runner, fixed take-profit, tick stop, or unavailable exit policy. |
| `outcome_annotation` | `outcome_annotation` | Explicitly non-decisional outcome annotations, if present. |

`outcome_annotation` must not affect the current decision. It is an audit node
for downstream evaluation fields that already exist in the snapshot.

## Compatibility rules

1. v0 must remain unchanged.
2. v1 must not reinterpret existing v0 field meanings.
3. `decision_trace_v1.status` must equal `signals[].status`.
4. `decision_trace_v1.action` must equal `signals[].decision`.
5. `decision_trace` remains a lossy summary; consumers needing auditability
   should use `decision_trace_v1`.
6. Producers should not inline raw bars, full option chains, or forward outcome
   data in trace nodes. Use `input_refs` and optional digests instead.
7. If a node is blocked because data is unavailable, encode that as
   `status=blocked` with a stable `summary.primary_blocker`.

## Migration plan

Recommended implementation should be split into a follow-up card, for example:

Title: `CONTRACT-FOLLOWUP-002 implement pa_feitian decision_trace_v1 shadow contract`

Acceptance criteria:

- Add pydantic models for `DecisionTraceV1`, `TraceNode`, `TraceEvidence`, and
  `TraceInputRef`.
- Add `doc/schemas/pa_feitian_decision_trace_v1.schema.json`.
- Add `doc/schemas/pa_feitian_snapshot_v1.schema.json` that references the new
  trace schema and keeps v0 fields intact.
- Add fixture coverage for one `keep`, one `data_blocked`, and one
  `model_dominated` trace.
- Add producer support behind an explicit v1 option, such as
  `--contract-version pa_feitian_snapshot_v1`; keep v0 as the default until the
  dashboard and consumers opt in.
- Add frontend fallback behavior: render `decision_trace_v1.nodes` when present
  and keep rendering the legacy string otherwise.

## Open questions for implementation

- Whether `input_refs[].digest` should be required once source scorecard records
  are stable enough to hash deterministically.
- Whether `summary.confidence` should mirror an existing scorecard confidence
  field or stay nullable until a calibrated trace-level confidence exists.
- Whether a sidecar file is useful during shadow validation before promoting
  `pa_feitian_snapshot_v1`.
