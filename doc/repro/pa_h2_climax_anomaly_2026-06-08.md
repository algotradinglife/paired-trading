# pa_h2_climax 异常调查 — 2026-06-08

回应 `full_stack_backtest_2026-06-08.md` §3 的红旗：CN_AGRI_POS pool 上 pa_h2_climax 实测 -0.040R EV / n=64，与 `pa_detector.py:275` 声明的 K=3 STRONG PASS (F1+0.640/F2+0.516/F3+0.571, n=8+7+7) 严重不符。本文复现并定位异常。

## TL;DR

1. **Docstring 声明的 K=3 通过证据不可复现**。即使用原 harness（`backtest_pa_standalone.py`，ATR×1.5 stop）和 require_climax+h=opp 同口径，在多个 K=3 cutoff 下 F2/F3 均为**负**。docstring 的 0.65 weight 依据 n=22 的极小样本，且我用同一脚本任何切法都拿不到 +0.516/+0.571 的 F2/F3
2. **2025 集中亏损**：5.5 年汇总 -0.040R 几乎全由 2025 单年贡献（EV -0.904R / n=9 / 累计 -8.13R）。n=9 不足以下"regime shift"结论——这是 drawdown cluster，需要 quarantine + monitor，而非声明真实 regime
3. **Stop 框架 EV 差 ~10bp，但二阶效应未量化**：PA structural (-0.040R) vs ATR×1.5 (+0.057R) 的 EV 差小，但 structural 改变了 R 分母、bars_held 分布、max_hold 频率（13/64 触发）和 MAE/MFE shape；判断 stop 优劣需要 paired same-entry replay
4. **建议**：把 cn_agri_pos 的 `pa_h2_climax` policy_weight **从 0.65 降到 0.0（live）或 0.15（watch/annotation only）**，等收集 2026 H2 真实数据 + 完整 walk-forward 重做基线再决策

## 三方对比

| Source | Stop | Sample | F1 | F2 | F3 | OOS 总评 |
|--------|------|--------|----|----|----|----|
| docstring `pa_detector.py:275` (claimed 2026-06-04) | ATR×1.5? | n=8+7+7=22 | **+0.640R** | **+0.516R** | **+0.571R** | STRONG PASS → 0.65 |
| `backtest_pa_standalone --cutoff3 2024-12-31` | ATR×1.5 | n=18+9+17=44 | +0.622R | **-0.444R** | **-0.316R** | 边缘正 / F2-F3 反 |
| `backtest_pa_standalone --cutoff3 2025-06-30` | ATR×1.5 | n=18+15+11=44 | +0.622R | **-0.458R** | **-0.227R** | 边缘正 / F2-F3 反 |
| `backtest_full_stack`（current production） | PA structural | n=64 | — | — | — | **-0.040R EV, win 47%** |

F1 都是 +0.62~+0.64R 一致；**F2/F3 完全对不上**。

> **同口径细节**：standalone harness 在 `min_gap` 和 climax lookback 边界上与 live `PABottomDetector(require_climax=True)` 不完全一致（standalone 用 `min_gap=1` 扫描后再后过滤 `min_gap=10`；climax 后过滤用 `recent_climax_max_5` 不含信号 bar，而 detector 是 `[i-lookback, i]` 含信号 bar）。这会改变 sample 集合，所以"same params"应读作"params 名义相同，sample 因边界小有出入"。但 full_stack 用的是 live detector 形态，结果也是负的——所以这个 caveat 削弱了"严格同口径"措辞，**不能拯救 docstring**。

## 不可复现的来源（最可能）

1. **数据/快照漂移**：2026-06-04 docstring 时数据库的 daily bars 已经比现在少一段（或不同的 backfill），在那时刻的 K=3 计算碰巧落在不同的样本上
2. **不同的 cutoff 边界**：docstring 没声明 cutoff 日期。如果 cutoff 卡在了非常窄的窗口（n=7/7/7 暗示这是个极薄的切法），不同 cutoff 会得到完全不同的 F2/F3
3. **不同的 sub-pool 口径**：docstring 写 "m/p/ta/ma/sr"，但当时是否还包含其他 filter（e.g., DIF≥某阈值）未声明
4. **手工选样**：n=22 样本太小，可能是当时的 walk-forward 跑了多次后挑了好的那次（survivorship in development）

**结论**：以 2026-06-08 当前 codebase + 当前数据，docstring 的"STRONG PASS"判定**不成立**。

## 全栈历史的真实形态（按年）

由 `full_stack_backtest.csv` pa_h2_climax lane：

| Year | n | EV | sum R |
|------|---|-----|-------|
| 2021 | 9 | -0.102R | -0.92 |
| 2022 | 17 | +0.011R | +0.19 |
| 2023 | 12 | +0.315R | +3.78 |
| 2024 | 11 | -0.005R | -0.06 |
| **2025** | **9** | **-0.904R** | **-8.13** ⚠ |
| 2026 YTD | 6 | +0.424R | +2.55 |
| **Total** | **64** | **-0.040R** | **-2.58** |

去掉 2025：n=55, EV +0.094R, sum +5.55R — 与 standalone 的 +0.057R EV 直接吻合。

## 全栈历史按 symbol

| Symbol | n | EV | sum R | hit% |
|--------|---|-----|-------|------|
| kq_m_dce_p | 11 | **-0.361R** | -3.97 | 36% ⚠ |
| kq_m_czce_ma | 15 | -0.132R | -1.99 | 47% |
| kq_m_dce_m | 14 | +0.039R | +0.54 | 43% |
| kq_m_czce_sr | 11 | +0.109R | +1.20 | 55% |
| kq_m_czce_ta | 13 | +0.126R | +1.63 | 54% |

`dce_p`（棕榈油）和 `czce_ma`（甲醇）拖累。docstring 注明"y/i/j excluded — negative h=opp lift"，**但没排除 dce_p**，而 dce_p 的负 EV 比当时排除的那批更严重。

## Stop 框架对比

| Framework | EV | n | 备注 |
|-----------|-----|---|------|
| ATR×1.5（standalone） | +0.057R | 72 | h=opp + require_climax |
| PA structural（full_stack） | -0.040R | 64 | 信号 bar 附近 pivot low - 1% |

EV 差 ~10bp。但这只是一阶。Structural stop 在 CN agri 上偏松：

| Stop framework | full_stop | tp1_max | max_hold | tp1_tp2 | tp1_stop |
|----------------|-----------|---------|----------|---------|----------|
| full_stack (structural) | 27 | 13 | **13** | 9 | 2 |

13/64 (20%) 触发 max_hold——结构止损宽，TP 也够不到。

**未量化的二阶效应**（codex review 提醒）：structural vs ATR 的真实对比需要在**相同 entries** 上做 paired replay，输出：
- MAE / MFE 分布
- bars_held 分布
- outcome transition matrix（structural 下的 tp1_max → ATR 下的 tp1_tp2？）
- 资金占用时长 → 机会成本

只看 EV 不够。**待办**：写 `paired_stop_compare.py`，对每个 climax 信号同时跑两种 stop，输出对照表。

## 建议（按优先级）

1. **立刻**：把 `pa_detector.py:300` 区段里 `cn_agri_pos` 的 `pa_h2_climax` policy_weight 临时降到 0.0（或不接收，让 score_today 不 emit 该 lane 给 CN agri pool）
2. **立刻**：在 docstring 里加 "**STALE 2026-06-08**: standalone reproduction shows F2/F3 negative; full_stack 5.5y shows -0.040R EV; reduce weight pending 重新 walk-forward"
3. **下一步**：跑一次完整 K=3 walk-forward 重做基线，**这次 commit 时附 cutoff 日期 + 数据 snapshot hash 到 docstring**
4. **下一步**：跨 lane 审计——其他 docstring 引用的 STRONG PASS 是否也存在同类不可复现性？（已知 cn_metal_futures+bpull "F3+0.69R STRONG PASS" 在 full_stack 上确认 +0.179R，**那个能复现**）

## 学到

- **小样本 walk-forward 必须存 snapshot**：n=22 的 PASS 不能离开复现说明独立成立
- **policy_weight 必须有 expiry 或 re-validation cadence**：6 周前的 baseline 已经被新数据推翻
- **2025 是 drawdown cluster，不是 regime shift**（codex correction）：n=9 远不够下 regime 结论；2026 YTD 反弹 (+0.424R / n=6) 反而暗示没有持久性破坏。正确处理是 quarantine + monitor
- **未覆盖的 sample 独立性问题**（codex 提醒）：overlapping same-symbol 信号会让 walk-forward t 检验偏乐观；同 symbol 短时间内多个 climax 信号实际上不独立

## 复现命令

```bash
cd src
# 当前 backtest
.venv/bin/python scripts/backtest_pa_standalone.py --pool CN_AGRI_POS \
  --stop-mult 1.5 --cutoff3 2024-12-31

# 当前 production
DERIVED_ROOT="/Volumes/Data Drive/derived" \
  .venv/bin/python scripts/backtest_full_stack.py --pool CN_AGRI_POS
```
