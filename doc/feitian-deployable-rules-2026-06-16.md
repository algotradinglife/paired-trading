# 飞天期权链 — 2 条可落地规则（researcher 落地，2026-06-16，t_044a6019）

承接 philosopher 权利金空间归因（`trade-philosopher/doc/pa-replication/feitian-h1-premium-space-2026-06-16.md`，
**真实期权 K 线、非 Black-76**，避开 MODEL_DOMINATED）。philosopher 产出 2 条可落地规则，researcher 侧：
独立核验最易出错的因果性 + 把规则落到本仓可部署/可测的形态。配套 `doc/xiao-feitian-options-timing-system-2026-06-16.md`。

## 规则 1：凸性期权用 runner，别用固定 TP1/TP2 ✅
- **证据**（au n=573 PA 突破做多）：文档 TP1(+1R 半)/TP2(+2R) 把 ≥2R 占比压到 **0%**，EV +0.31R；
  **凸性 runner（无固定 TP，trail/持满 T=17）→ ≥2R 占 22%，EV +0.65R**。ag 同向（runner 优于 TP，但绝对偏弱）。
- **机制**：naked OTM call 的 EV 在**右尾**，固定 TP 把右尾切掉=把 edge 切掉。与飞天 §1 凸性哲学一致，反驳 legacy TP1/TP2。
- **落地口径**：naked OTM 期权腿默认 **runner 出场**（持到 T 或结构 trail），**不挂 +1R/+2R 固定止盈**。
  - 代码现状：`engine/options/option_exit.py` 当前是 2x/4x/tick + max_hold 一刀切；集成时应让 naked OTM 默认走 runner（无 TP），把固定 TP 模式降为非默认。**（本卡未改 option_exit，列为集成项。）**

## 规则 2：IV-水平闸门（因果 IV-rank，强，且救 ag）✅✅ — 已落地为模块
- **证据（因果 expanding-window IV-rank，无 look-ahead，warmup=40）**：
  | (因果) | 低 rank<0.33 | 高 rank>0.66 | 闸门（弃 rank>0.66） |
  |---|---|---|---|
  | au (n=515) | **+1.57R 胜57%** | +0.41R 胜42% | 全体 +0.77R → **+1.47R**（留 34%） |
  | ag (n=352) | **+0.52R 胜46%** | −0.53R 胜16% | 全体 +0.04R → **+0.25R**（留 73%） |
  低 IV-rank → 高 premium EV，两品种单调；**闸门把 ag 从边际（+0.04R）救成可部署（+0.25R）**。
- **机制**：信号日 IV 已高 = 买贵凸性，且高 IV 多伴 topping/stress 区制，突破更易失败。
- **researcher 独立核验**：审 `feitian_h5_causal.py`——`prior_iv` 只累计**此前**信号、rank 在 append 之前算、warmup=40
  → **确认 look-ahead-free，非样本内 artifact**。
- **落地（本卡已交付）**：`src/engine/options/iv_regime.py`（纯逻辑、6 hermetic tests）：
  - `causal_iv_rank(current_iv, prior_ivs, warmup=40)` — 此前同品种信号日 IV 中严格更低的占比；history<warmup → None。
  - `iv_regime_keep(rank, max_rank=0.66, allow_during_warmup=False)` — rank≤0.66 留单；warmup 期默认弃（保守，无 IV 历史不能断定便宜）。
  - `iv_regime_decision(...)` — 返回 `{iv_rank, keep, reason}` 供 record 标注。
  - **口径**：弃 IV-rank>0.66（au 可再紧到 <0.33 @ +1.57R）。

## 集成路径（给后续/score_today，本卡未改生产）
1. **IV 取数**：信号日 OTM call 收盘 → Black-76 反解 IV（`engine/options/black76.py` / `cn_*_selector.estimate_iv`），
   维护**每品种信号日 IV 历史**（按时间序），喂 `causal_iv_rank`。
2. **闸门**：`iv_regime_decision` 标注到期权记录；`keep=False` 不出期权腿（或降级 advisory，比照 shadow gate 先影子）。
3. **出场**：期权腿默认 runner（规则 1），`option_exit` 加 runner 模式为默认。
4. 建议**先 shadow/advisory**（比照 [[project_shadow_gate_degenerate]] 教训：先影子累积前向证据再入生产/sizing）。

## Caveat / 红线（务必随规则带走）
- **日线分辨率、无 bid/ask**（期权 OHLC only）；阈值 0.66 是 philosopher 三分位/因果分位口径，需更多区制再确认。
- **规则不救负 EV 信号**：philosopher ★命门行——标的亏损子集权利金 runner **更惨**（au −0.54R/ag −0.82R）；
  naked call ≈ 标的方向 × 杠杆 − theta，方向错 theta 再加一刀。**权利金腿是放大器不是救生员**。
- **§1 命门（几-tick 结构止损 → 救负 EV）DATA-BLOCKED**：现有 min5 期权仅近月、无 bid/ask、单一 2026 topping 区制，
  测不了；且盲目 %止损必被日内 whipsaw，真机制是 **DD 线结构止损（黑盒，待提取）**。已建 data-engineer 卡（20–60DTE 日内 + bid/ask）。
- **选品**：au 主场再次复现（au≫ag，与 Q2 入场过滤、[[project_pairing_convexity_q2phase1]] 一致）。

相关：[[project_ddline_options_findings]]、[[project_pairing_convexity_q2phase1]]、[[project_shadow_gate_degenerate]]、飞天体系文档。
