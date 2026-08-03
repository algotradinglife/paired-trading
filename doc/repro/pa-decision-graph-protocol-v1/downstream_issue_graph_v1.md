# PA M6P downstream issue graph v1

This is a routing contract, not a request to open child issues in Issue #85.
Each future issue has exactly one owner and communicates cross-owner ordering
through `blockedBy` / `blocking`.

```text
M6P-STRATEGY-PROTOCOL (Strategy, this issue)
        |
        +--> M7-DATA-EPISODE-CONTRACT (Data)
        |
        +--> M7-ENGINEER-WORKBENCH (Engineer)
                       |
                       +--> M7-STRATEGY-REHEARSAL-10 (Strategy)
                                      |
                                      +--> M8-DATA-LEARNING-30-CONFIRM-20 (Data)
                                                     |
                                                     +--> M8-STRATEGY-WEIGHT-DISPOSITION (Strategy)
```

## Owner and dependency table

| Work key | Project owner | Deliverable boundary | `blockedBy` | `blocking` | Minimum gate |
|---|---|---|---|---|---|
| `M6P-STRATEGY-PROTOCOL` | Strategy | Frozen source graph, lifecycle, episode, and feedback contracts | M6F accepted terminal | M7 Data; M7 Engineer | `protocol_ready_for_m7` only |
| `M7-DATA-EPISODE-CONTRACT` | Data | Append-only causal episode/event/outcome schema and custody | `M6P-STRATEGY-PROTOCOL` | M7 Strategy | no outcome leakage; immutable event IDs |
| `M7-ENGINEER-WORKBENCH` | Engineer | Blind plan, bar-management, and review workbench | `M6P-STRATEGY-PROTOCOL` | M7 Strategy | no automatic routing; trace version bound |
| `M7-STRATEGY-REHEARSAL-10` | Strategy | Ten forward protocol/interface rehearsal episodes | `M7-DATA-EPISODE-CONTRACT`, `M7-ENGINEER-WORKBENCH` | M8 Data | exactly 10; zero weight updates |
| `M8-DATA-LEARNING-30-CONFIRM-20` | Data | Seal 30 eligible learning and next 20 unseen confirmation episodes | `M7-STRATEGY-REHEARSAL-10` | M8 Strategy | 30 eligible; 20 unseen; custody and split sealed |
| `M8-STRATEGY-WEIGHT-DISPOSITION` | Strategy | Batch weight review, promotion or rollback | `M8-DATA-LEARNING-30-CONFIRM-20` | none | multi-metric review; no topology drift |

## Ordering and authorization

- The M7 rehearsal tests protocol and interface usability only. It cannot update
  node, edge, or terminal weights.
- M8 candidate fitting requires at least 30 eligible forward policy episodes;
  evaluation uses only the next 20 sealed unseen confirmation episodes.
- A failed integrity gate blocks the dependent owner and does not get bypassed by
  a profitable outcome.
- No downstream key is authorized until this packet's terminal is
  `protocol_ready_for_m7`. That terminal authorizes creation of the M7 child issue
  graph only; it does not authorize M8 observation, execution, routing, capital,
  or reserve release.
