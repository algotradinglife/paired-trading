---
name: baselines-as-auditable-artifacts
description: baselines/<lane>_<pool>.json（repo 根）是 baseline 单一可信源；validate_baselines.py --full 做真·漂移检测（schema v2）
metadata: 
  node_type: memory
  type: project
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

`baselines/`（**repo 根目录**，不是 `data/review/baselines/`——那是旧路径）自 2026-06-09 起是所有 lane × pool baseline 数字的单一可信源。审计入口 `src/scripts/validate_baselines.py`。

**Why:** 06-08 调查发现 pa_h2_climax docstring 的 K=3 STRONG PASS 不可复现，触发盘点——docstring inline 数字会随数据/代码漂移、无 expiry/commit-hash 锚点，不适合做契约。

## schema v2 + `--full` 真漂移检测（2026-06-09 本 session 新增）

`validate_baselines.py --full` 以前只检 repro 的 exit code；现在**真解析输出并对比**：

- 跑一次 `backtest_full_stack.py --out-json`（输出 per-`(lane, symbol)` cells，经 `src/scripts/_baseline_output.py` 契约）当**主基准**，全 baseline 共享。
- 每条 baseline 用 v2 字段 **`full_stack_lane`** 映射到 full_stack 的 lane label（**注意 lane 名不一定等于 baseline 的 `lane` 值**，如 cn_bond 的 full_stack_lane 是 `pa_cn_bond`，US daily H2 是 `pa_us_dif_pos`），再按 `symbols_included` 过滤（**大小写不敏感**——full_stack 输出 US ticker 大写、baseline 写小写）、n-加权聚合，和 `samples_full_stack_5y` 比。
- 容差（全局默认 + 单文件 `tolerance_policy` 覆盖）：`ev_r ±0.10R` / 严格符号翻转（仅正负相反才算，0 附近不误判）/ `n ±25%` → `DRIFT_DETECTED`；`win_pct ±10pp` → WARN；`min_n=10` 把小样本漂移降为 WARN。
- runtime drift **不覆盖**已知 broken 的 metadata verdict（STALE/EXPIRED/MISSING/BROKEN）。validator **永不回写** baseline 的 `verdict`（人工拥有）。full_stack 跑挂则主检查跳过（fail-open，不误报 DRIFT）。
- v2 字段（全可选，v1 仍校验通过）：`full_stack_lane` / `tolerance_policy` / `production_binding` / `fold_date_ranges` / 预留 `data_snapshot_hash`。

**已废弃的方向（别重试）：** "folds-secondary"（用 K=3 脚本的 fold cells 做二级对比）设计过但**被否决**——baseline 记的 fold 是 config + 符号范围筛过的子集，K=3 脚本不直接暴露这个 cell，做对就得 per-symbol fold 机制，等于把主基准逻辑复制一遍，价值低。full_stack 主基准已足够。

**未完成 follow-up：** `compute_data_hash` 已实现但**未接线**（full_stack 输出 `data_hash=None`），所以"数据变了 vs 代码变了"的归因目前空转；真要诊断漂移来源时再把 full_stack 加载的 bars 喂进去。

**How to apply:**
- 任何新 lane × pool baseline 写完 walk-forward 后立刻产出 JSON；docstring 涉及 F1/F2/F3 数字时删 inline、改用 `BASELINE_REF: baselines/<file>.json`。
- 新 baseline 想被 `--full` 检测，必须加 `full_stack_lane`（用 full_stack 的 label）；`symbols_included` 是符号过滤器。
- 部署改了产出数字（如 max_hold / 抑制规则）后，对应 baseline 的 `samples_full_stack_5y` 会被 `--full` 标 DRIFT——确认是预期改善（如抑制剔除亏损 trade 致 EV/win 升）后**re-baseline**（刷新数字 + last_verified + commit_hash），不要盲目刷新（可能掩盖真回归）。
- 每周 / 新数据进来跑 `validate_baselines.py`（`--full` 慢但真检），`--strict` 是 CI gate。verdict 语义见 `baselines/README.md`；新增 verdict 同步 validate_baselines.py 的 VERDICTS set。
- 设计 + 计划：`docs/superpowers/specs|plans/2026-06-09-baseline-validation-schema*.md`。
- 相关：[[project-signal-source]]、[[broad-market-defensive-h2-suppress]]、[[feedback-signal-must-have-macro]]
