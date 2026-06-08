# Codex 第二意见 — baselines/ 基础设施 (2026-06-09)

来源：`codex exec --sandbox read-only` 对 commit `f0ff0bc5` (baselines infrastructure) 的独立审查。

---

**Verdict: directionally sound, but currently advisory, not preventative.** It will make stale claims more visible, but it will not stop a bad weight or silent baseline disappearance from reaching production.

Highest-risk hole: `validate_baselines.py --full` does not validate the baseline. The README says reruns should flag `samples.*.ev_r` drift `> 0.10R` or fold sign flips ([baselines/README.md:56](baselines/README.md)), but the script only checks JSON types ([validate_baselines.py:64](src/scripts/validate_baselines.py)) and whether `repro_command` exits 0 ([validate_baselines.py:132](src/scripts/validate_baselines.py)). That would miss exactly the original failure mode: a backtest can succeed while output changes materially. It should parse structured output, or better require repro scripts to emit JSON with fold `n`, `ev_r`, win rate, symbol breakdown, and compare against saved tolerances.

The `DRIFT` design is too permissive. `vflush` records `verdict: DRIFT`, assigned `0.65`, recommended `0.30` ([vflush baseline:48](baselines/vflush_cn_metal_cu_sc.json)), while production still returns `0.65` ([vflush_detector.py:254](src/engine/divergence/vflush_detector.py)) and `score_today.py` documents that same live weight ([score_today.py:1089](src/scripts/score_today.py)). I would not have the validator mutate detector code, but CI should fail on `DRIFT` when `policy_weight_assigned != policy_weight_recommended`, or require an explicit waiver field with owner, expiry, and rationale. Current metadata mode exits 0 with one `DRIFT` and one `STALE`, so this is a dashboard, not a gate.

Schema is a decent v1, but insufficient for accountability and future cases. It lacks owner/reviewer, tolerance policy, expected parser/output contract, dependency versions, data source identity/hash, fold date ranges as a list, execution environment, slippage/fee assumptions, risk metric definitions, and production binding: which function/rule actually consumes the weight. It also cannot naturally model ensemble lanes or cross-lane interactions; `lane × pool` is fine for atomic detectors, but ensembles need component baselines, interaction terms, aggregation method, and attribution.

The "one-stop audit entrypoint" claim is overstated ([audit doc:3](doc/repro/baselines_audit_2026-06-09.md)). It will not catch untracked lanes, changed detector defaults, manual `repro_post_filter` mistakes, stale docstring inline numbers, data backfill without output diffing, production routing drift, or deleted baseline files. The deletion edge case is real: the script just globs current JSON files ([validate_baselines.py:177](src/scripts/validate_baselines.py)); there is no registry of expected lanes.

`BASELINE_REF` is useful but fragile. Some production comments still contain inline obsolete numbers, e.g. bpull `F1=+1.000R F3=+1.008R` ([score_today.py:834](src/scripts/score_today.py)), and the actual weights remain hardcoded. Add a linter that scans detector/score files for `policy_weight`, policy rules, and baseline numeric claims, verifies referenced JSON exists, and optionally checks assigned weight equals code-returned weight for covered rules.

Missing next steps: tests for schema validation, exit-code semantics, missing references, unknown verdicts, `DRIFT` gating, deleted-baseline registry, and CI/cron integration. I ran metadata validation; it exits 0 despite `DRIFT`, which confirms the main enforcement gap.

---

## Action items (按优先级)

### 立刻执行（本 batch）
1. **降 vflush production weight 0.65 → 0.30**：`vflush_detector.py:258` + `score_today.py:1089`。DRIFT verdict + 0.65 是矛盾的
2. **`--strict` 模式**：DRIFT / STALE 都让 validate_baselines.py 退 1，CI 可以 gate
3. **EXPECTED_LANES 注册表**：`baselines/EXPECTED_LANES.json` 列产线必须有 baseline 的所有 (lane, pool) 对；缺失就 BROKEN
4. **清理 score_today.py:834 stale bpull 注释**（"F1=+1.000R F3=+1.008R"）
5. **保存本次 codex review** 到 codex-review.md（这个文件）

### 下一轮
6. **Schema v2**：加 owner, tolerance_policy, data_snapshot_hash, fold_date_ranges (list), slippage_bp, production_binding (file:line + function) 字段
7. **结构化 backtest 输出**：让 backtest_*.py 写 JSON metric 文件，validate_baselines.py --full 真正解析比对
8. **Linter**：扫描 src/ 找未引用的 inline F1/F2/F3 数字 + 验证 BASELINE_REF 路径存在
9. **17 条剩余 baseline 翻 JSON**：context_a/pa_h2/b1_bottom 等
10. **CI / cron**：每日 validate_baselines.py --strict，DRIFT 立刻报警
