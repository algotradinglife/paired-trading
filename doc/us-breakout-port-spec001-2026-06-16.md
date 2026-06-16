# CardB：spec001_proxy 突破移植 US 指数 ETF — researcher 独立定论（2026-06-16，t_b918daa8）

承接 philosopher US 突破 port（其用自有 coarse `breakout_candidate` + R013 门，结论：突破 edge 不跨市场到 US，
raw 全负、R013 门的正是 tiny-sample 假象）。原 CardB 明确要 **researcher 的 spec001_proxy** 定论（philosopher proxy 太粗）。
本文用**已验证的 `scripts.backtest_spec001_proxy.detect_signals`**（CN 同一无 look-ahead 突破检测器：强实体 + 收上 1/3 +
处下边界 + 前置下跌腿 + 二次入场 + payoff 门）跑 US SPY/QQQ/IWM 5min RTH，规范突破止损出场（`eval_spec001_ev.simulate_order`）。
工具 `scripts/us_breakout_port_spec001.py`，数据经 sanctioned loader（`data.bar_loader`，与 backtest_full_stack 同；data/raw，已 RTH）。**机械统计，研究性。**
复现：`cd src && ./.venv/bin/python scripts/us_breakout_port_spec001.py`

## 结果（max_wait=78 / max_hold=234 bar，≈1/3 RTH 段）
| 标的 | n(resolved) | EV(R) | 胜率 | 95% CI |
|---|---|---|---|---|
| SPY | 422 | +0.081 | 18.7% | [−0.154, +0.330] |
| QQQ | 1243 | +0.092 | 19.6% | [−0.046, +0.235] |
| IWM | 1324 | −0.045 | 17.3% | [−0.162, +0.084] |
| **POOLED** | **2989** | **+0.030** | **18.4%** | **[−0.059, +0.117]** |

## 结论：突破 edge 不跨市场到 US 指数 ETF（独立确认 philosopher）
- **池 EV ≈ 0（+0.03R），CI 跨 0，胜率仅 ~18%** → **不可部署**。三只 ETF 单独看也都 CI 跨 0（含 IWM 负）。
- **比 philosopher 的 coarse proxy 略好**（其 raw −0.08/−0.25/−0.31）：严格的 spec001_proxy 把 US 突破从"负"提到"~0"，
  但**仍无正 edge** → 印证 philosopher 的"太粗"批评（严检测器更干净），但**结论方向一致：US 指数突破不可部署**。
- **结构观察**：US 突破是**极低胜率（18%）+ 极高 payoff**（max R 15–19）的右尾分布——少数大赢家恰好抵消大量 −1R 止损 → 净 ~0。
  CN 同结构是正 EV（已验证 lane）；US 上 win 率不够把 EV 推正。
- **机制**：US 指数日内**强均值回归** → 突破被 fade → 突破止损系统性挨打。与"US 经典是回踩 pullback 不是突破"先验吻合。

## 建议
- **不投入把突破 port 到 US 指数 ETF**（edge 不在 US 突破里，非检测器/门的问题——严检测器也救不出正 edge）。
- 若要做 US 方向：**转 pullback setup**（趋势中回踩），而非突破止损。这是独立的新 setup 探索，另起卡。
- caveat：单一持有窗口（敏感性非重点，EV 符号是）；US 5min 已 RTH、period-end 标注；overnight gap 在连续 bar 序里被折叠（与 philosopher 同口径）。

相关：philosopher `doc/pa-replication/us-breakout-port-2026-06-16.md`；[[project_spec001_ev_eval]]、[[project_broad_market_suppress]]。
