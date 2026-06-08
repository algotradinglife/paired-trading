# Baselines 基础设施 V2 — 2026-06-09

第二轮迭代。回应 codex review 五处批评，扩展覆盖。

## 本轮改动

| 改动 | 文件 | 来源 |
|------|------|------|
| Vflush 生产权重 0.65 → 0.30 | vflush_detector.py:258, score_today.py:1089 | codex: DRIFT + assigned > recommended 是生产 gap |
| `--strict` 模式（STALE/DRIFT/PENDING/EXPIRED/BROKEN/MISSING → exit 1）| validate_baselines.py | codex: 不能只是 dashboard，必须能 CI gate |
| EXPECTED_LANES.json 注册表 | baselines/EXPECTED_LANES.json | codex: 缺 baseline 文件会沉默 |
| MISSING/ORPHAN 检测 | validate_baselines.py | codex: 删除 baseline 文件无告警 |
| `policy_weight_assigned != recommended` → BROKEN | validate_baselines.py | codex: silent production gap |
| 清理 score_today.py:834 stale bpull 注释 | score_today.py | codex 直接 cited |
| 6 个新 baseline JSON | baselines/{context_a×2, pa_h2×3, pa_us_60min} | 把 production-active 但只在 docstring 里的 lane 移到 audit 范围 |
| `PENDING_VALIDATION` verdict | validate_baselines.py | 区分"production-active 但无 K=3 baseline" |

## 当前 dashboard

```
STATUS  LANE                    POOL                  VERDICT                 W   REASON
[ OK ]  bpull                   cn_metal_futures      STRONG PASS          0.75  valid for 91d
[ OK ]  context_a               cn_metal_futures      CONDITIONAL PASS     0.60  valid for 92d
[ OK ]  context_a               us_equity             CONDITIONAL PASS     0.60  valid for 92d
[STAL]  pa_h2_climax            cn_agri_pos           STALE                0.00  verdict=STALE (known broken)
[ OK ]  pa_h2                   cn_bond               STRONG PASS          0.70  valid for 91d
[ OK ]  pa_h2                   cn_futures            marginal             0.55  valid for 92d
[ OK ]  pa_h2                   cn_metal_futures      STRONG PASS          0.75  valid for 92d
[ OK ]  pa_h2                   us_equity             PASS                 0.80  valid for 92d
[PEND]  pa_us_60min             us_equity             PENDING_VALIDATION   0.65  无 K=3 baseline
[DRFT]  vflush                  cn_metal_futures      DRIFT                0.30  weight 已降到 recommended

10 entries audited; 7 OK; 1 STALE; 1 DRIFT; 1 PENDING
默认 exit 0；--strict exit 1
```

10 个 baseline 覆盖了**所有 production-active lanes**（policy_weight > 0），加上 1 个 STALE。

## 6 个新 baseline 的状态

6 个 JSON 都标 `requires_verification: true`——数字是从 docstring 导入，不是新 K=3 跑出来的。要点：

| File | Verdict | Weight | 状态 |
|------|---------|--------|------|
| context_a_us_equity.json | CONDITIONAL PASS | 0.60 | OK 但 cutoffs=null，需要重做 K=3 |
| context_a_cn_metal_futures.json | CONDITIONAL PASS | 0.60 | OK，F2 fail 备注 2024 regime |
| pa_h2_us_equity.json | PASS | 0.80 | uptrend+h=opp；下行变体 REJECT |
| pa_h2_cn_metal_futures.json | STRONG PASS | 0.75 | full_stack +0.189R/n=102 验证方向 |
| pa_h2_cn_futures.json | marginal | 0.55 | 只有 F1+F2，无 F3/IS 信息 |
| pa_us_60min_us_equity.json | **PENDING_VALIDATION** | 0.65 | 无任何 K=3 baseline；full_stack +0.086R/win 36% |

## Agent 发现的 5 个新问题（未修，留作下一轮）

1. **`pa_detector.py:333` vs `:246`** 同一 cell 引用两组不同的 n（n=28/56 vs n=12/24）。可能是 gap-fix 前/后版本，但没标注
2. **`cn_futures` pool 缺 symbol allowlist**：routing 用 `instrument_class==cn_futures` 但没在任何地方写明具体哪些 symbol 进
3. **pa_us_60min 没有 K=3 baseline**：实际 production 用 weight 0.65/0.30 phase-based 路由，但这套权重从哪儿来未文档化
4. **K=3 cutoff 全部以散文形式存在**（"IS<=2021 / OOS2=2023H2-2024 / OOS3>2025"），从未 ISO 化
5. **score_today.py:1254 phase weight vs legs=1 bonus 语义不清**：confidence 用 phase_w，weight 用 PABottomDetector.policy_weight；两者哪个主导未明示

## 关键变化：codex 拒绝单 dashboard，要 CI gate

Codex 最强批评是"`validate_baselines.py` 现在只是 dashboard 不是 gate"。本轮的回应：

```bash
# CI / cron 用这个
.venv/bin/python scripts/validate_baselines.py --strict
# exit 1 if any: STALE / DRIFT / PENDING / EXPIRED / BROKEN / MISSING
```

任意 STALE/DRIFT/PENDING 在 CI 失败——强迫修复或显式 waive，不能再静默存在。

但 codex 另一个批评**还没解决**：`--full` 还是只检查 exit code，不解析 backtest 输出对比 samples。这需要让 backtest_*.py 全部加结构化 JSON 输出契约，是更大的 surgery，下一轮做。

## 下一轮（按优先级）

1. **结构化 backtest 输出**：让 backtest_*.py 写一行 JSON（fold/n/ev/win），validate_baselines.py --full 解析比对 tolerance ±0.10R（codex 主诉求）
2. **Vflush 根因调查**：checkout 2026-06-03 commit + 同样数据 snapshot 看 cu+sc 信号数；判断是数据回填还是 detector 漂移
3. **Pa_us_60min 真正的 K=3 baseline**：把 PENDING_VALIDATION 推成 STRONG PASS/marginal/REJECT 其一
4. **Schema v2 字段**：owner, tolerance_policy, data_snapshot_hash, fold_date_ranges 列表, slippage_bp, production_binding（codex 提的 schema 缺字段）
5. **Linter**：扫 src/ 检测未引用 BASELINE_REF 的 inline F1/F2/F3 数字 + 验证 JSON 路径存在
6. **CI 集成**：把 `--strict` 接到 pre-commit / GitHub Action

## 复现

```bash
cd src

# Dashboard（人看）
.venv/bin/python scripts/validate_baselines.py

# CI gate（机器看）
.venv/bin/python scripts/validate_baselines.py --strict

# 单 lane 调试
.venv/bin/python scripts/validate_baselines.py --lane pa_h2

# JSON output
.venv/bin/python scripts/validate_baselines.py --json
```
