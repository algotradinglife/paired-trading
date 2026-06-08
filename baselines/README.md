# Baselines — Auditable artifacts for policy_weight evidence

每个 `<lane>_<pool>.json` 文件是一个 lane × pool 的 walk-forward 验证基线契约。
docstring 里的 PASS/STRONG PASS 数字只能引用此目录的 JSON——单一可信源。

## Schema

```jsonc
{
  "schema_version": 1,
  "lane": "pa_h2_climax",
  "pool": "cn_agri_pos",
  "instrument_class": "cn_futures",
  "symbols_included": ["kq_m_dce_m", "kq_m_dce_p", ...],
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
