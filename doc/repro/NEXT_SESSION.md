# NEXT_SESSION — handoff from 2026-06-10

读这一篇就能接管。下一 session 开头：`读 doc/repro/NEXT_SESSION.md 继续`。

## 当前状态快照（origin/main 同步至 `8a69ea6f`，三个 cleanup commit 已 push；本 handoff 更新为其后续 doc commit）

- **Baselines dashboard**: **10 OK / 1 STALE**（仅 `pa_h2_climax` STALE/weight-0；其 anchor 已随 harness fix re-baseline，repro 现在 within tolerance）。无 PENDING。
- **Drift gate**: `src/scripts/validate_baselines.py --full` 现在做**真漂移检测**（full_stack per-(lane,symbol) primary anchor）。每周 cron（Mon 08:53）跑 `src/scripts/drift_gate.sh`，只在真 `[DRFT]` / `FULL_STACK_UNAVAILABLE` 时报警（`logs/drift-gate/ALERTS.log`）。**新**：full_stack 现在吐真 `data_hash`（不再 None），drift 的"数据 vs 代码"归因机制已解锁——待某 baseline 在有意 re-baseline 时把 emitted hash 写进 `data_snapshot_hash` 才端到端亮起。
- **Tests**: 490 passed（+4 `tests/test_full_stack_data_hash.py`）。
- **Memory**: 37 entries 自动加载（含 jj、broad-market suppress、regime-gate 不可移植、baselines-as-auditable、retired-and-historical 等）。

完整快照在 `STATUS.md` 顶部 sync 块 + "baselines/ infrastructure" 段。

## 两个 bounded cleanup —— 都已完成 ✅

- **data_hash 接线** ✅（commit `52db5c6d`）：`backtest_full_stack.replay_pool` 累积 daily+60min bars（key `"{symbol}@{level}"`），`main` 跨 pool 合并经 `compute_data_hash` 吐确定性 sha256。Codex：no actionable issues。**剩余 opt-in**：要端到端亮起归因，需在一次有意 re-baseline 时把 emitted hash 写入 baseline 的 `data_snapshot_hash`（README 标 reserved，验证器只加注解、不改 verdict）。
- **pa_us_dif_pos TR-0.30 子 cell K=3** ✅（commit `f1b29ae1`）：**KEEP 0.30**。daily лане 按 PAStructure phase 加权（BULL=0.65 / TR,TR_FORMING=0.30）。扩 `backtest_pa_us_k3.py` 加 phase tag + 生产 gate 切片：子集**全是 TR_FORMING**（纯 TR n=0），且 gate-drop 后占 daily 生产信号 86%。生产 1.5×ATR 框架下 n=36 EV+0.069R、F1<0 —— 不过 3/3-OOS 关（不 promote），但 4 个变体全正 EV（不 suppress）。状态从 placeholder→validated-marginal，**无生产权重变更**。证据：`doc/repro/pa_us_dif_pos_tr_k3_2026-06-10.md`、baseline `samples_k3_phase_tr_forming_2026-06-10`。Backlog 线索：TR_FORMING 在 2.0×ATR 跳到 +0.410R/4-of-4（stop-width-by-phase，未做）。

## 自上次 handoff 起已完成

- **共享 harness 边界 bug** ✅（commit `86c91584`）：TP1-at-boundary 计分 bug 在全部 12 个 simulator 修复——9 个 long `simulate_trade`（pa_standalone / pa_swing / pa_us_k3 / pa_incycle / bpull / vflush / b1_bottom / context_a_ev / dif_crossing）+ `rr_pool`/`dif_crossing` 的 tuple 返回（顺带改正 `max_hold`→`tp1_max` 标签）+ `pa_top_grid` short + `full_stack._simulate_forward`。新增 `tests/test_simulate_trade_boundary.py`（每 simulator 一条回归，TDD 先 RED 后 GREEN）。`validate_baselines.py --full`：10 个 live anchor 全在容差内（verdict 全不变）；唯一越界的 weight-0 STALE `pa_h2_climax`（ev_r −0.040→+0.056 符号翻转）已 re-baseline 到 live 4-symbol replay（n=53），旧 5-symbol/pre-dce_p-exclusion 快照冻结为历史证据。Codex review：no actionable issues。

## 本 session 完成了什么（大弧线）

1. **Memory 整合**：项目重命名后从两个旧路径迁移/精简到 `-paired-trading/memory/`（37 entries，旧目录已删）。
2. **Baseline validation v2**（旧 handoff 的 Item 1 + Item 2，**已 SHIP**）：`--full` 真解析 + schema v2（`full_stack_lane` / `tolerance_policy` / `production_binding` / `fold_date_ranges`）。Codex 审过两轮，P1/P2 全修。
3. **Drift gate**：每周 cron 自动跑 `--full`，catch 漂移 + 零成交崩溃（`FULL_STACK_UNAVAILABLE`）。
4. **pa_us_60min K=3 → PASS**：清掉最后一个 PENDING（uptrend+h=opp，8/8 OOS folds 正，weight 维持 0.65）。
5. **PA TOP path B → REJECT，DECIDED 不做 PA put lane**（详见下）。

设计/计划文档：`docs/superpowers/specs|plans/2026-06-09-baseline-validation-schema*.md`、`...2026-06-10-pa-top-path-b*.md`。

## 推荐的下一个主线：期权层（需要 brainstorm）

**Why now**：刚决定"下行用期权/对冲层表达"（不做 PA put detector）。但期权层目前 `score_today` 只 *emit* `options_calls`，**没有系统化 P&L attribution / backtest**——它现在是系统表达上行+下行的承重墙，却未验证。

**建议**：开新 session，走 brainstorm → spec → plan → implement（和本 session 的 baseline-validation / PA TOP 一样的流程）。需要 clean context，别在长 session 末尾硬上。

**Caveat**：option pricer（Black-model）当年 migration 没活下来（`options_simulation` repro 卡在这）；做期权层 P&L 可能要先重建 pricer。

## 也可以做的 bounded cleanups（小、确定性高）

两个原列项（pa_us_dif_pos TR-0.30 K=3、data_hash 接线）均已完成，见上方"两个 bounded cleanup"段。

| 项目 | 说明 | 起点 |
|------|------|------|
| **data_snapshot_hash 端到端启用** | data_hash producer 已通；要让 drift 的"数据 vs 代码"注解真正触发，需在一次有意 re-baseline 时把 full_stack emitted hash 写进某 baseline 的 `data_snapshot_hash`（仅当认可当前数据快照为可信源时）。 | `baselines/*.json` 的 `data_snapshot_hash`；emitted hash 来自 `backtest_full_stack.py --out-json` |
| **TR_FORMING stop-width-by-phase** | TR_FORMING 在 2.0×ATR 跳到 +0.410R/4-of-4 折正。phase-conditional stop（TR_FORMING 用更宽止损）是真优化线索，但改生产止损模型（现为 structural stop），daily lane 仍 monitoring 时低优先。 | `doc/repro/pa_us_dif_pos_tr_k3_2026-06-10.md` Backlog 段 |

## 已废除的方向（不要重试）

| 方向 | 为何 REJECT | 文档 |
|------|------------|------|
| **PA TOP / put detector（3 机制全 REJECT）** | H2-mirror ×2 + A_top sell-the-rally 全 0 promotable cell。结构性原因：顶是 diffuse fatigue 不是 panic event；confirmed-downtrend regime 太稀疏（A_top 几乎只在 TR_FORMING fire，BEAR n≈15）。**不做 PA put lane**，下行走期权/对冲。**别再造 PA top detector 除非有全新 mechanism class + 新证据。** | `doc/repro/pa_atop_wf_2026-06-10.md`；STATUS "PA TOP" 段；memory `retired-and-historical` |
| TP1 1R → 0.75R | 价格不动，非 TP1 远 | `doc/repro/p2_followups_2026-06-09.md` §A |
| pa_us_dif_pos / CN_METAL 套 regime gate | bottom-reversal lane 与 trend filter 互斥 | `cn_regime_gate_reject_2026-06-09.md`；memory `regime-gate-not-portable` |
| baseline-validation 的 "folds-secondary" 二级对比 | baseline 的 fold 是 config+符号筛过的子集，K=3 脚本不暴露；用 full_stack primary anchor 足够 | memory `baselines-as-auditable-artifacts` |

## 其他低优先 backlog

| 项目 | Why low priority |
|------|-----------------|
| DIR audit followups（3/5 open：minute15 polarity、daily_structure bias、resonance skew）| DIR 仍 annotation-only；等 POC 对齐数据累积 |
| pa_us_60min 10-source POC 阈值调参 | 等 ~50+ live samples |
| pa_h2_climax 重激活 | 太边缘，ROI 低；现 STALE/weight-0 |
| 2022 pa_h2 CN_METAL -1.77R | 4 种 gate 全失败，接受为结构性代价 |
| DIF detector 源文件物理删除 | 确认零 live consumer 后再清 |
| `_position_size()` 重做 | 用户已 defer 到 DIR + Xiao 定型后 |

## 快速 ref

| 想看 | 路径 |
|------|------|
| 整体状态 | `STATUS.md` 顶部 sync 块 + "baselines/ infrastructure" 段 |
| commit 时间线 | `jj log --no-graph` 或 `git log --oneline -25` |
| Drift gate 脚本 + 日志 | `src/scripts/drift_gate.sh`；`logs/drift-gate/` |
| Validator | `src/scripts/validate_baselines.py`（`--full` 真检；`--strict` CI gate）|
| Baselines schema | `baselines/README.md` |
| PA TOP REJECT 证据 | `doc/repro/pa_atop_wf_2026-06-10.md` |
| baseline-validation 设计/计划 | `docs/superpowers/specs|plans/2026-06-09-baseline-validation-schema*.md` |
