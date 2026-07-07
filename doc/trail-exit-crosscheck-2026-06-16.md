# Card C：trail 出场 EV — researcher 独立交叉验证（2026-06-16，t_5af101b3）

philosopher 切片（per-contract，其 sim，n≈106）：baseline +0.502R / 机械trail(1R/1R) +0.598R /
结构trail(swing3) +0.573R / **结构trail(swing5) +0.813R**（+0.31R vs base）。本文是 researcher
EV/部署侧在**自有 harness** 的独立交叉验证（同 replica 选中突破单、同 per-contract 取数走
**sanctioned loader** `_load_cn_window`——不碰数据存储；四法同集：仅在四法下都跑满 288-bar 窗口的单子
进入对比，相对 lift 苹果对苹果）。工具 `scripts/analyze_trail_exits.py`。**机械统计，研究性，不 PASS/FAIL。**
复现：`cd src && ./.venv/bin/python scripts/analyze_trail_exits.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`

## 结果（POOLED，同集 n=73）
**各方法均值 EV（注意：这是单方法均值 CI，不是判断「谁胜谁」的统计量）：**
| 出场 | EV(R) | 胜率 | 点估计 vs base | 各方法均值 95% CI |
|---|---|---|---|---|
| baseline（自带 target OCO） | +0.805 | 68% | — | [0.49,1.14] |
| 机械 trail（1R 启动/1R 跟踪） | +0.926 | 73% | +0.12 | [0.50,1.41] |
| 结构 trail（swing3） | +1.555 | 56% | +0.75 | [0.73,2.59] |
| 结构 trail（swing5） | +1.583 | 53% | +0.78 | [0.73,2.61] |

**配对 bootstrap Δ（同集同序，才是判断「是否真胜」的统计量；reviewer t_c8092dc3 要求补）：**
| 配对差 | Δ(R) | 配对 95% CI | 判定 |
|---|---|---|---|
| 机械 − baseline | +0.121 | **[−0.26, +0.58]** | ⚠ 跨 0，**不显著** |
| 结构 swing3 − baseline | +0.750 | **[−0.004, +1.70]** | ⚠ 边缘跨 0，不显著 |
| 结构 swing5 − baseline | +0.778 | **[+0.007, +1.74]** | 勉强排除 0（边缘正） |
| 结构 swing3 − 机械 | +0.630 | **[−0.03, +1.55]** | ⚠ 跨 0，**不显著** |
| 结构 swing5 − 机械 | +0.657 | **[−0.02, +1.52]** | ⚠ 跨 0，**不显著** |

逐品种（EV）：au 0.730/0.735/0.793/**1.282**；cu 0.876/1.469/1.562/**1.685**；rb 0.791/0.675/**1.839**/1.636（**rb 机械 < baseline**）。

## 结论（已按 reviewer 降级——勿过读）
- **结构 trail vs baseline**：点估计明显更高（+0.78R），**配对 CI 仅勉强排除 0（swing5）/ swing3 边缘跨 0**——
  方向性正、但高方差、统计边缘，**不是强结论**。
- **结构 trail vs 机械 trail**：仅**样本内点估计**更高，**配对 CI 跨 0 → 统计不支持「结构 ≫ 机械 / beats mechanical」**。
- **机械 trail vs baseline**：**不显著**（CI 跨 0），且 rb 逐品种机械 < baseline。
- 一句话：**「让赢家跑」方向有证据，但本样本（n=73, in-sample, per-contract）证据强度只到「点估计更高 + 结构-vs-baseline 边缘正」**；
  「结构 ≫ 机械」**不成立为统计结论**。要立此结论需更多样本 / OOS / 主连复核 / 差值 CI 明确为正。

## 诚实 caveat（勿过读绝对值）
1. **配对 CI 边缘/跨 0**（见上表）——这是本结论强度的主约束，已纳入 headline 降级。
2. **非 philosopher 绝对值复现**：harness 约定不同（max_hold 288 vs ~400；进场/前向口径不同）；交叉验证的是方向，非绝对数。
3. **swing3≈swing5（均~+1.56），未复现其 swing3 弱/swing5 强分化**：swing 检测定义不同（其代码未提交，据文字重实现）→ swing 灵敏度依实现。
4. **高方差**：EV 由 288-bar 窗内少数大 runner 驱动；绝对 EV 对持有窗敏感；更高 EV 但更高方差/更低胜率（回撤+心理成本），非免费午餐。
5. **保守无 look-ahead 成交**：trail 抬升次 bar 才生效 → lift 不被乐观成交夸大（偏保守）。

## 未完成 & 下一步
- **仍欠『干净主力连续』绝对复核**（philosopher 点名）：单合约或含到期低流动尾部 artifact。
  `src/data/continuous.py` 主连合成需 `root` 指向数据存储——触及「不读 quant_data」边界 → 评估走
  data-engineer 主连 5min 交付，或确认 continuous root 访问是否在界内。**当前结论基于 per-contract，相对 lift 稳健但绝对值待干净复核。**
- **部署 / R002 改动属 fidelity 裁决归用户**：philosopher 论证结构 trail（跟结构非机械固定 R）契合 R002（R002 只否决机械）
  → 「R002 精化（机械✗/结构✓）」是信念调整，researcher 只量化 EV，**改 R002/出场约定需用户裁**。

工件 `data/review/trail_exits.json`（gitignore）。相关：[[exploration-plan-2026-06-15]] Card C、[[project_spec001_ev_eval]]、R002。
