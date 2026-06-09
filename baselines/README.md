# Baselines — Auditable artifacts for policy_weight evidence

每个 `<lane>_<pool>.json` 文件是一个 lane × pool 的 walk-forward 验证基线契约。
docstring 里的 PASS/STRONG PASS 数字只能引用此目录的 JSON——单一可信源。

## Schema

```jsonc
{
  "schema_version": 2,        // v1 original; v2 adds full_stack_lane, production_binding, fold_date_ranges
  "lane": "pa_h2_climax",
  "full_stack_lane": "pa_h2_climax",  // v2: full_stack's internal lane label for the PRIMARY anchor
  "pool": "cn_agri_pos",
  "instrument_class": "cn_futures",
  "symbols_included": ["kq_m_dce_m", "kq_m_dce_p", ...],  // symbol filter for anchor aggregation — do NOT modify
  "symbols_excluded": ["kq_m_dce_y", "kq_m_dce_i", "kq_m_dce_j"],
  "detector_params": {
    "min_h_legs": 2,
    "min_quality": 0.3,
    "ema_threshold": 0.0,
    "min_gap": 10,
    "require_climax": true,
    "climax_threshold": 0.4,
    "h_filter": "opposing"
  },
  "walk_forward": {
    "method": "K=3 OOS folds",
    "cutoff1": "2023-12-31",
    "cutoff2": "2024-06-30",
    "cutoff3": "2024-12-31",
    "stop_framework": "ATR x 1.5"
  },
  "samples": {
    "is":  { "n": 28, "ev_r":  0.082, "win_pct": null },
    "f1":  { "n": 18, "ev_r":  0.622, "win_pct": null },
    "f2":  { "n":  9, "ev_r": -0.444, "win_pct": null },
    "f3":  { "n": 17, "ev_r": -0.316, "win_pct": null }
  },
  "samples_full_stack_5y": {  // PRIMARY drift anchor — compare via full_stack_lane
    "n": 64, "ev_r": -0.040, "win_pct": 46.9
  },
  "production_binding": [     // v2: "file:func" or "file:line" strings showing where policy_weight is consumed
    "src/engine/divergence/pa_detector.py:275"
  ],
  "fold_date_ranges": {       // v2: documentation of K-fold cutoffs (open ends use "start"/"end")
    "is": ["start", "2022-12-31"],
    "f1": ["2023-01-01", "2024-06-30"],
    "f2": ["2024-07-01", "2024-12-31"],
    "f3": ["2025-01-01", "end"]
  },
  "tolerance_policy": {},     // v2 optional: per-baseline override of global drift thresholds (see below)
  "verdict": "STALE",
  "verdict_reason": "Prior K=3 STRONG PASS NOT REPRODUCIBLE; F2/F3 negative.",
  "policy_weight_assigned": 0.0,
  "valid_until": "2026-09-08",
  "commit_hash": "2fab5c1f",
  "data_snapshot": "2026-06-08",
  "last_verified": "2026-06-08",
  "repro_command": "cd src && .venv/bin/python scripts/backtest_pa_standalone.py --pool CN_AGRI_POS --stop-mult 1.5 --cutoff3 2024-12-31",
  "related_docs": [
    "doc/repro/pa_h2_climax_anomaly_2026-06-08.md",
    "doc/repro/full_stack_backtest_2026-06-08.md"
  ],
  "notes": "Free text..."
}
```

## v2 Schema Fields

| Field | Required | Description |
|---|---|---|
| `schema_version` | yes (v1+) | Integer. Currently `2`. |
| `full_stack_lane` | yes (v2+) | full_stack's internal lane label for the PRIMARY anchor. Maps the baseline to `full_stack[full_stack_lane]`, filtered to `symbols_included`, n-weighted aggregated, and diffed against `samples_full_stack_5y`. Must be one of: `pa_h2_climax`, `pa_h2`, `pa_cn_bond`, `pa_us_dif_pos`, `pa_us_60min`, `bpull`, `vflush`, `context_a`. Absent only on meta-gates (e.g. `us_regime_gate.json`). |
| `tolerance_policy` | no | JSON object — per-baseline override of global drift defaults. Any key present overrides the matching global. Absent = use global defaults. |
| `production_binding` | no | Array of `"file:func"` or `"file:line"` strings. Documents where this baseline's `policy_weight` is consumed in production code. Only add when the binding is unambiguous from the file's own `related_docs`/`notes`; skip rather than guess. |
| `fold_date_ranges` | no (doc) | Documentation of K-fold date boundaries. Keys `is`, `f1`, `f2`, `f3`; values are `["start_date_or_start", "end_date_or_end"]`. Open ends use the literal strings `"start"` / `"end"`. Only added where explicit cutoffs are known. |
| `data_snapshot_hash` | reserved | Optional; reserved for future data-vs-code attribution. Do not set manually; will be populated by the backtest harness when it emits reproducible hashes. |

## Global Drift Tolerances

Drift detection uses the `samples_full_stack_5y` PRIMARY anchor only (folds-secondary mechanism was evaluated and dropped).

| Metric | DRIFT threshold | WARN threshold | Notes |
|---|---|---|---|
| `ev_r` | `|delta| > 0.10R` **or** sign flip (strict opposite signs) | — | sign flip always DRIFT regardless of magnitude |
| `n` | `|delta| / baseline_n > 25%` | — | if baseline `n < 10`, downgrades DRIFT to WARN (tiny-n) |
| `win_pct` | — | `|delta| > 10pp` | warn-only, not a hard drift |

`tolerance_policy` can override any of: `ev_r_abs`, `sign_flip`, `n_pct`, `win_pct_pp`, `min_n`.

## 验证流程

1. **基线更新**：跑 `scripts/validate_baselines.py`；任何 `samples.*.ev_r` 当前重跑后偏移 > 0.10R 或 fold 符号翻转 → 标 `DRIFT`/`BROKEN`
2. **过期触发**：`valid_until` 超过当前日期 → 强制重新验证
3. **加权前置**：detector 的 `policy_weight()` 文档必须 BASELINE_REF 引用 JSON 路径

## Verdict 语义

| Verdict | 含义 | 默认行为 |
|---------|------|---------|
| STRONG PASS | K=3 ≥3 folds 正、monotone 或近 monotone | weight ≥0.65 可用 |
| PASS | K=2 正向或 K=3 2 折正 | weight 0.40-0.60 |
| marginal | 边缘正、F-fold 不稳 | weight ≤0.40 watch only |
| CONDITIONAL PASS | 某 fold 弱、其他强 | weight 0.50-0.65 with caveat |
| REJECT | OOS 负或 F-folds 多负 | weight 0.0 |
| STALE | 原 PASS 现已不可复现 | weight 0.0 + monitor |

## 命名约定

`<lane>_<pool>[_<scope>].json`

例：
- `pa_h2_climax_cn_agri_pos.json`
- `bpull_cn_metal_futures.json`
- `vflush_cn_metal_cu_sc.json` (sub-pool 用 _scope)
- `pa_cn_bond.json`
