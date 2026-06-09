# NEXT_SESSION — handoff from 2026-06-09

读这一篇就能接管。下一 session 开头：`读 doc/repro/NEXT_SESSION.md 继续`。

## 当前状态快照（commit `1d4738e6`）

- **PnL**: 5.5y EV +0.131R → +0.247R（+89% in-sample），K=3 OOS +23.39R verified
- **Production lanes**: 8 active emit + 1 STALE + 1 meta-gate
- **Baselines**: 11 entries audit-able，dashboard 9 OK / 1 STALE / 1 PENDING；`scripts/validate_baselines.py --strict` 是 CI gate
- **Memory**: 7 entries 自动加载，含跨 session 规则（jj、broad-market suppress、regime gate 不可移植）

完整快照在 `STATUS.md` 顶部 2026-06-09 sync 块。

## 路线图剩余 — 2 项 substantial infra

### Item 1: `validate_baselines.py --full` 真解析 backtest 输出

**Why**: codex 主诉求（review 第 2 轮 finding #1）。当前 `--full` 只检 exit code，不对比 sample 数字——backtest 可以 run 成功但输出已经 drift，validator 看不见。这正是 vflush 2026-06-09 false-alarm DRIFT 的诊断盲区。

**Scope**:
- 给每个 backtest_*.py 加 JSON output contract：`--out-json` 写一行 `{lane, pool, samples: {is/f1/f2/f3: {n, ev_r, win_pct}}}`
- 每个 baseline JSON 加 `comparison_pattern` 字段：用什么 cell 对比、tolerance（e.g. ±0.10R EV / sign-flip）
- `_run_repro()` 解析 JSON，对比 saved samples，emit `DRIFT_DETECTED` / `OK`

**起点文件**:
- `src/scripts/validate_baselines.py:154-180`（`_run_repro` 函数）
- `src/scripts/backtest_pa_standalone.py`、`backtest_bpull.py`、`backtest_vflush.py`、`backtest_pa_cn_phasefilter.py` — 4 个 backtest 各加 `--out-json` flag
- `baselines/*.json` — 加 `comparison_pattern` 字段

**工作量**: 1-2 天。需要：
1. 设计 JSON output schema（半天）
2. 改 4 个 backtest script（半天）
3. 写 parser + 对比逻辑（半天）
4. 在 baselines 加 comparison_pattern + 测试 round-trip（半天）

**Caveat**: backtest 还需保持人可读 stdout（不能完全 JSON-only），所以 `--out-json` 是附加输出。

### Item 2: Schema v2 字段

**Why**: codex 第 2 轮 finding #3：当前 schema 缺 owner / tolerance_policy / data_snapshot_hash / fold_date_ranges (list) / slippage_bp / production_binding 等字段，治理不完整。

**Scope**:
- 设计 schema v2 字段集（参考 codex 列表 + 实际遇到的痛点）
- 更新 `baselines/README.md` schema 文档
- backfill v2 字段到 11 个 baseline JSONs
- `validate_baselines.py` 加 v2 字段的可选校验

**字段建议**（按优先级）:
| 字段 | 含义 | 来源 |
|------|------|------|
| `owner` | 谁负责该 baseline 的 re-validation | 治理 |
| `tolerance_policy` | drift 阈值（EV ±X、sign-flip 容忍 etc.）| Item 1 配套 |
| `data_snapshot_hash` | bars CSV/Parquet 的 hash | 可复现性 |
| `fold_date_ranges` | 显式 list 替代 cutoff1/2/3 散文 | 已有 caveat 多次提到 |
| `slippage_bp` | EV 数字假定的滑点 | codex 提的 missing |
| `production_binding` | file:func:line 显式 | EXPECTED_LANES 已部分有 |

**起点文件**:
- `baselines/README.md`
- `baselines/*.json`（11 entries）
- `src/scripts/validate_baselines.py:29-37`（VERDICTS / REQUIRED_FIELDS）

**工作量**: 半天 + propagate to 11 JSONs（1-2 小时）。

### 两项耦合度

Item 1 的 `comparison_pattern` 与 Item 2 的 `tolerance_policy` 是同一关注点的两半。**建议合并设计**：tolerance_policy 字段在 schema v2 引入，Item 1 的 parser 消费它。

## 已废除的方向（不要重试）

为防止下次再试这些已经被实证拒绝的方向：

| 方向 | 为何 REJECT | 文档 |
|------|------------|------|
| TP1 1R → 0.75R | max_hold 高发不是 TP1 远，是价格不动 (只 4/66 max_hold trades 达到 0.75R)。pa_h2 -4.66R，pa_us_dif_pos -1.71R | `doc/repro/p2_followups_2026-06-09.md` §A |
| pa_us_dif_pos 套 SPY regime gate | 自带 DIF>0 + h_opp macro filter，2022 那 5 笔已经精选；regime gate 抹掉 3 笔正贡献 +0.44R | `doc/repro/p2_followups_2026-06-09.md` §C |
| CN_METAL 套 SMA200 regime gate | bottom-reversal lane 与 trend filter 互斥。Composite gate -19.17R，per-symbol -10.16R，SPY 移植 +1.35R 但 2025 -2.60R 不稳 | `doc/repro/cn_regime_gate_reject_2026-06-09.md` |
| pa_us_dif_pos 单 lane max_hold=20（vs 全局 30）| K=3 OOS mh=30 wins +0.73R；per-lane override 不值 | commit `1d4738e6` task C |

Memory 已存：`feedback_regime_gate_not_portable.md` — "bottom-reversal 不能套 trend filter，cross-market gate 慎用"。

## 其他可推 / 不优先的 backlog

| 项目 | Why low priority |
|------|-----------------|
| `pa_h2_climax` 重激活（剔 dce_p 后估算 EV +0.026R）| 太边缘，需要 fresh K=3 + 1 年 OOS forward 才证明，ROI 低 |
| pa_us_60min 正式 K=3 baseline（当前 PENDING_VALIDATION）| 需要新 backtest harness；当前已 production 跑且 dashboard 标 PEND，不阻塞 |
| 2022 pa_h2 CN_METAL -1.77R 单年代价 | 已尝试 4 种 gate 全失败；接受为结构性代价 |
| valid_until cron / 自动 cadence | 当前已 stagger 到月度，手工足够；自动化是锦上添花 |
| Schema v2 中的 fee/commission 假定 | full_stack 未计；改起来需要 product decision |

## 快速 ref

| 想看 | 路径 |
|------|------|
| 整体状态 | `STATUS.md` 顶部 2026-06-09 sync 块 |
| 14 个 commit 时间线 | `jj log --no-graph` 或 `git log --oneline -15` |
| 最新 codex review | `codex-review.md`（root）|
| 跨市场 lane × market 分析 | `doc/repro/lane_market_evaluation_2026-06-09.md` |
| max_hold 实验 + K=3 验证 | `doc/repro/max_hold_experiment_2026-06-09.md` |
| 4 个 REJECT decisions 评估 | `doc/repro/p2_followups_2026-06-09.md` + `cn_regime_gate_reject_2026-06-09.md` |
| dce_p 根因 | `doc/repro/agri_pos_dce_p_diagnosis_2026-06-09.md` |
| Baselines schema | `baselines/README.md` |
| Validator script | `src/scripts/validate_baselines.py` |

## 完全新方向？

如果路线图剩余 2 项都不优先，可以转向：
- **Forward monitoring**：跑 weekly `score_today` smoke + 累积 dashboard，看 P0-P3 在真实新数据上是否维持
- **Lane 扩展**：当前 8 active lanes 都已优化，若有新 PA pattern 候选（e.g. PA TOP trend-follow K=3 已 ready 但未 production），可以验证 + emit
- **Options 集成深化**：当前 score_today emit options_calls 但没系统 backtest，可以建立期权层 P&L attribution
