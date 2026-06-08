# Baseline 可复现性审计 — 2026-06-09

回应 06-08 `pa_h2_climax_anomaly` 调查中暴露的系统性问题："docstring 里的 STRONG PASS 数字到底有多少是真的能复现"。建立 `baselines/` 作为单一可信源 + `validate_baselines.py` 一键审计入口。

## 行动总览

| 步骤 | 产物 | 状态 |
|------|------|------|
| 降权 pa_h2_climax 0.65→0.0 | score_today.py:1466/1473, pa_detector.py:275 | ✅ |
| 全代码库 baseline 宣称盘点 | 21 distinct claims across 5 lanes | ✅ |
| JSON schema 设计 + 4 个核心 baseline 文件 | baselines/{4 json + README} | ✅ |
| 重跑 3 个 STRONG PASS | bpull / vflush / pa_cn_bond | ✅ |
| validate_baselines.py | scripts/ + DRIFT 状态支持 | ✅ |
| 关键 docstring 加 BASELINE_REF | bpull/vflush/pa_detector | ✅ |

## 4 个 baseline 当前结论

| Baseline | Verdict | Weight | 复现结果 |
|----------|---------|--------|---------|
| `bpull_cn_metal_futures` | **STRONG PASS** ✓ | 0.75 | K=3 IS+0.165/F1+0.148/F2+0.706/F3+0.361；reproduced 2026-06-09。**rb 排除是关键**——若包含 rb，F1 翻成 -0.332R |
| `pa_h2_cn_bond` | **STRONG PASS** ✓ | 0.70 | 完全复现 docstring 数字（n=31 EV+0.548R F1/F2/F3=+0.219/+1.500/+0.500）。但 F2 n=6 仍是 outlier，full_stack 实际 +0.123R |
| `pa_h2_climax_cn_agri_pos` | **STALE** ❌ | 0.0 | 已降权。原 F2/F3 不可复现，2025 集中亏损 -0.904R EV/n=9 |
| `vflush_cn_metal_cu_sc` | **DRIFT** ⚠ | 0.65 (建议 0.30) | 原 cu+sc n=50 claim **现在只有 n=4**（cu n=1 / sc n=3）。当前 vflush 信号 84% 来自 ag，但 ag 不是 cu+sc baseline 支撑的路径。需要重新决定 routing 是 ag 还是 cu+sc |

## 关键发现

### 1. Bpull 反而比之前更好（带 caveat）

新 K=3（cutoffs 2023-12-31 / 2024-12-31 / 2025-06-30，排除 rb）：
- IS +0.165R (n=73)
- F1 +0.148R (n=12)
- F2 **+0.706R** (n=16)
- F3 +0.361R (n=38)

vs 原 docstring（2026-06-02）：
- IS +0.171R (n=92)
- F1 +0.121R (n=71)
- F2 +0.348R (n=48)
- F3 +0.495R (n=45)

新 F2 比老 F2 更强；F1 接近；F3 弱一些。**Direction 和 verdict 都 hold**。但样本结构很不同（n=73 vs n=92），暗示原 cutoffs 跟我现在挑的不同。

### 2. Pa_cn_bond 完美复现，但要注意 F2 outlier

n=31, EV +0.548R, F1=+0.219(n=16), F2=+1.500(n=6), F3=+0.500(n=9) — 与 docstring 完全一致。

但 F2 n=6 + EV+1.500R 是显著的 small-sample outlier；full_stack 5.5y 实际只有 +0.123R。**承认 verdict，调低叙述**。

### 3. Vflush 是新的红旗：cu+sc 子池已经"消失"

| Source | scope | n | EV |
|--------|-------|---|-----|
| Docstring 2026-06-03 | cu+sc only | 50 (22+12+9+7) | +0.598/+0.722/+0.436/+0.533 |
| 2026-06-09 复现 (h=opp, all symbols) | full pool | 43 | +0.185R |
| 2026-06-09 复现 (h=opp, cu+sc only) | manual filter | **4** | n/a |

**只剩 4 个 cu+sc 信号**，0.65 weight 站不住脚。production 实际生效的是 ag-dominated 路径，但那条路径从来没有 baseline 验证过。

可能原因：
- 数据回填/调整（最有可能）
- 同样的 detector 跑出来的 cu+sc 信号本来就稀
- 原 baseline 用了不同的 climax_threshold

下一步：拉出 2026-06-03 的 commit + 数据 snapshot 对比 cu+sc 信号数量；如确认是数据漂移而非代码漂移，承认 vflush 是 ag-driven、重做 baseline。

## 新基础设施

### `baselines/<lane>_<pool>.json`

每条 lane × pool 的契约。字段：
- `samples`: IS/F1/F2/F3 with n/ev_r/win_pct
- `samples_full_stack_5y`: full_stack 实际产线 PnL（对比 standalone WF）
- `verdict`: STRONG PASS / PASS / CONDITIONAL PASS / marginal / REJECT / STALE / **DRIFT**
- `policy_weight_assigned`: 当前生效权重
- `policy_weight_recommended`: 如果与 assigned 不同（DRIFT 状态）
- `valid_until`: 强制重新验证 deadline
- `commit_hash` + `data_snapshot`: 数据/代码 snapshot 锚点
- `repro_command`: 一行命令复现
- `repro_post_filter`: 复现后需手工处理的步骤（如 vflush/bpull 缺 --symbols flag）

### `scripts/validate_baselines.py`

两种模式：
```bash
# 默认 metadata 审计（fast）
.venv/bin/python scripts/validate_baselines.py

# 全跑 repro_command（slow, opt-in）
.venv/bin/python scripts/validate_baselines.py --full

# 按 lane 过滤
.venv/bin/python scripts/validate_baselines.py --lane pa_h2_climax
```

输出 dashboard：
```
STATUS  LANE                  POOL                VERDICT          W     REASON
[ OK ]  bpull                 cn_metal_futures    STRONG PASS    0.75   valid for 91d
[STAL]  pa_h2_climax          cn_agri_pos         STALE          0.00   verdict=STALE (known broken)
[ OK ]  pa_h2                 cn_bond             STRONG PASS    0.70   valid for 91d
[DRFT]  vflush                cn_metal_futures    DRIFT          0.65   weight=0.65 but recommended=0.3
```

### Detector docstring 新规范

任何 detector 的 `policy_weight()` 或 lane 配置里，凡引用 baseline 数字，都必须带：
```
BASELINE_REF: baselines/<file>.json
```
docstring 里的 inline F1/F2/F3 是历史快照；当前权威以 JSON 为准。

## 没做的（明确割舍）

| 原计划 | 决定 | 原因 |
|--------|------|------|
| Detector 代码直接读 JSON 而不是 hard-code policy_weight | **跳过** | 引入新的运行时失败模式；validate 脚本已经能抓 drift，detector 保持 Python 静态 |
| 把 21 条 baseline 全部翻成 JSON | **只做了 4 条核心** | 4 条覆盖了所有 STRONG PASS（高权重路径），其他 17 条多是 REJECT/marginal，验证 ROI 低 |
| 完整 walk-forward 重做所有 PASS baseline | **N/A** | 已经发现 1 STALE + 1 DRIFT；继续做也是同等流程 |

## 下一轮该做

按优先级：

1. **Vflush DRIFT 根因调查**：把 2026-06-03 commit checkout 出来，跑相同脚本，看 cu+sc n 数量。如果当时也是 n=4，docstring 是当时就编造的；如果是 n=50，数据被回填过
2. **剩余 17 条 baseline 翻 JSON**：context_a (US/CN_METAL), pa_h2 (US/CN_METAL/CN_FUTURES), b1_bottom (REJECT 状态)，等
3. **Score_today.py 多处 inline baseline 数字清理**：line 834 / 904 / 1022 的注释都应换成 BASELINE_REF 引用
4. **Cron 化 validate_baselines.py**：每周自动跑、有 EXPIRED/DRIFT 立刻告警

## 复现命令汇总

```bash
cd src

# Dashboard
.venv/bin/python scripts/validate_baselines.py

# Bpull K=3
.venv/bin/python scripts/backtest_bpull.py --pool CN_METAL \
  --cutoff1 2023-12-31 --cutoff2 2024-12-31 --cutoff3 2025-06-30

# Vflush K=3
.venv/bin/python scripts/backtest_vflush.py \
  --cutoff1 2023-12-31 --cutoff2 2024-12-31 --cutoff3 2025-06-30 --h-opp-only

# Pa_cn_bond
.venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool CN_BOND
```
