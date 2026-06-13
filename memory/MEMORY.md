# paired-trading memory index

## Project direction & strategic decisions

- [Signal source: DIF off, PA on](project_signal_source.md) — 不再投入 DIF 路径；未来信号走 `engine/divergence/pa_*` 体系
- [Baselines as auditable artifacts](project_baselines_infra.md) — baselines/（repo 根）单一可信源；validate_baselines.py --full 真漂移检测（schema v2 full_stack_lane）；folds-secondary 已否决
- [Broad-market/defensive H2 suppression](project_broad_market_suppress.md) — DIA/SPY/XLU 等在 H2 反转家族系统性负 EV，全面排除；新 US lane 默认套用
- [Regime gate not portable](feedback_regime_gate_not_portable.md) — SPY/SMA200 gate 不能套 bottom-reversal lane；跨市场 portable signal 极少
- [Retired & historical findings](project_retired_and_historical.md) — DIF 检测器家族 + PA TOP/put（3 机制全 REJECT，不做 PA put lane）+ 旧 policy/data/scope：已废除勿重探（含原因）
- [Put side: Xiao direction reopened](project_put_side_xiao_direction.md) — 肖偏重 put；put 须在权利金空间验证（非标的 R 空间，PA top 镜像否决仍成立）；数据补完在新服务器，代码将迁移 WSL
- [US premium lane harness ready](project_us_premium_lane.md) — OCC 精确到期选约 + broad/defensive 排除已就绪；SPY 冒烟仅管道验证；信号验证等 GLD/GDX（t_6eae7583）

## Methodology & philosophy

- [Signals are posterior inference](project_signals_are_posterior.md) — 归零轴/背离/变盘事前不可知，算法输出连续置信度而非离散事件
- [Multi-TF is fusion, not a layer](project_multitimeframe_is_fusion_not_layer.md) — 单级别形态置信度不可靠，必须多时间级别融合（对齐 DIR 模块）
- [Recall-first paradigm](project_recall_first_paradigm.md) — MACD 背离只捕到 5-11% 波段；大头在新 detector 类型，不在窄子集精修
- [Scope: analysis & probability only](project_scope_analysis_only.md) — 不实现具体交易动作，输出供下游交易系统调用
- [Scope expanded to candle geometry](project_scope_expanded_to_candle_geometry.md) — 2026-05-25 起纳入 K 线几何 + Brooks/Xiao；confidence 仍纯宋
- [Project goal: code implementation](project_goal_code_implementation.md) — 整理理论是为自动化检测背离与多周期分析，带"可编程化"视角
- [Options: left-side entry valid](project_options_left_side_entry.md) — 期权场景小级别+严止损可左侧进场，不照搬宋"等理性买点"
- [instrument_class-aware engine](project_instrument_class_aware.md) — us_equity / cn_futures 两套校准；detector + policy + envelope schema

## Collaboration preferences (feedback)

- [Strategy repo boundary](feedback_strategy_repo_boundary.md) — 数据事务全归 data-engineer（kanban 建卡是唯一路径）；不读 quant_data/ 代码、不看 .env、不探数据源 API、不跑 quant sync

- [Decisions: give your opinion, not a quiz](feedback_options_style.md) — 判断题直接给带理由的推荐+等 go-ahead，别甩 AskUserQuestion 菜单；列选项必带推荐+尽量并行；提问先用大白话+实例
- [VCS: use jj not git](project_vcs_jj.md) — 仓库统一用 jj（colocated），日常 commit/push 禁用 git 写命令
- [Signal report must lead with macro](feedback_signal_must_have_macro.md) — 信号汇报先给多周期+走势结构+上下文多空，再谈信号本身
- [Codex review by default](feedback_codex_review_default.md) — 脚本/分析/报告生成后自动跑 codex review，P1/P2 修完再报告
- [Codex review after each fix](feedback_codex_review_after_fix.md) — 每次 fix/feature 提交后跑 `codex review --base <last-reviewed-commit>`
- [Autonomous commit authorized](feedback_autonomous_commit.md) — 逻辑单元完成即自行 commit，无需等指示；conventional commit 格式
- [No pseudocode during concept walkthrough](feedback_no_pseudocode_during_concept_walkthrough.md) — 走概念分层时只澄清思路，不写代码
- [Song Jianyi: no premature fusion](feedback_song_jianyi_no_fusion.md) — 让宋的体系独立讲，重点多周期与背离，先别与肖淳心融合
- [Multi-TF sweet-spot timing pitfall](feedback_multi_tf_sweet_spot_timing_pitfall.md) — bar-timestamp session 语义没对齐前不要做 multi-TF 桶聚合（leak 风险）

## Live lanes & validated findings

- [h=opposing validated universal](project_h_opposing_validated_universal.md) — CN+US cross-pool bottom+opp 强信号；K=3 STRONG PASS
- [h=opposing temporal stability](project_h_opposing_temporal_stability.md) — 2024 失效是 CN 商品 regime 不是降息；US 全年正；2025 恢复
- [CN_BOND pool (默认池)](project_cn_bond_pool.md) — 国债期货 TF/T/TS；bottom×h=opp EV +0.958R；2026-06-01 升级默认池
- [BPullDetector (live lane)](project_bpull_detector.md) — CN_METAL DIF>0 EMA20 pullback；K=3 STRONG PASS；rb excluded；CN_BOND REJECTED
- [VFlushDetector (live lane)](project_vflush_detector.md) — V 形急跌底部 K=3 STRONG PASS；cu/sc only；90% 不与 PA H2 重叠
- [PA H2 standalone detector](project_pa_standalone_detector.md) — CN_METAL h2|h=opp PASS；CN_AGRI REJECTED；policy_weight() 按池路由
- [Swing context backtest](project_swing_context_backtest.md) — US 60min uptrend+h=opp F1+0.625/F2+0.708；CN_METAL inverted
- [Swing quality hypothesis validated](project_swing_hypothesis_validated.md) — tight/wick 双独立信号；底部 EMA↓×opp×(tight|wick) 91.7% hit
- [Validated bottom setup](project_validated_bottom_setup.md) — bottom+leading+opposing 是 Codex 严格验证的强信号（过 Bonferroni）

## Options layer

- [Options entry timing (IV)](project_options_entry_timing.md) — 信号触发时 IV 16-17% vs 旧 6-7%；select_otm_calls() 集成 score_today
- [ag options swing findings](project_ag_options_swing_findings.md) — htf=supporting+宽止损 EV 1.685x；Xiao 飞天止损实为期权 K 线几个 tick
- [DD-line options cross-instrument](project_ddline_options_findings.md) — ag/au 有效(1.29x/1.66x)，cu/rb 全负 EV；贵金属上涨偏态是关键
- [CN options intraday (TqSdk)](project_cn_options_intraday_tqsdk.md) — SHFE/DCE/CZCE symbol formats + 全合约历史覆盖
- [Position size in score_today](project_position_size_in_score_today.md) — full/half/light/watch；score 分层+PA 相位限制+15m 降级

## Reference

- [Codex CLI local](reference_codex_cli.md) — `codex review --uncommitted` 是 pre-commit pre-flight 默认手段，不用 MCP
