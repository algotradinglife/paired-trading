---
name: project-scope-expanded-to-candle-geometry
description: "2026-05-25 用户显式放开 \"只用宋 MACD 体系\" 的 scope 约束，纳入 K 线几何 / Brooks 价格行为 / 肖老师飞天期权框架"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**事实**（2026-05-25 用户显式确认）：项目 scope 从"只接受 MACD 动能理论体系内输入"扩展到包含**K 线几何 + 价格行为**。原话：

> "我恐怕要选择 Z。宋的体系并不是完美的。最终盈利是在价格层面。"
> "MACD动能判断的是势，K线的变化才是盈利的所在。"

第一个落地 commit：`zovnpkuk 556ddd98` — `feat(detector): Z1 candle-geometry context — candidate_rejection_wick_ratio`。

**修订之前的 scope 表述**（[[project-scope-analysis-only]] 现需对照本条理解）：
- 原表述："置信度合成只接受 MACD 动能理论体系内的输入"
- 新表述：**confidence 字段**仍然只用 MACD 体系内输入（保持 backward-compat）；新增字段 `signal.context_features` 是**开放的数字字典**，可以装 K 线几何 / 价格行为 / 量能等任意 OHLCV 衍生特征。下游 consumer 自己选用，不影响 confidence。

**已纳入的外部框架（用户明示）**：
- **Al Brooks 价格行为**：trend bar / reversal bar / signal bar / H1-H2 pullback count / spike+channel pattern / measured move 等
- **肖老师飞天期权体系**：tight-tip 止损 / 推动计数 / 飞天 expiry+strike 选择 / 分仓止盈 / 破去实现止盈 / measured move 止盈

**Why**：之前讨论 "前期阻力"时承认 MACD cycle 只是动能 lifecycle，不是"卖盘压力位"。MACD divergence 只命中 5 个组件中的 1 个（动能衰竭），剩下 4 个（价格聚集 / 拒绝形态 / 量能 / 多 TF 共振）都需要走 K 线 / volume / multi-TF。用户明确选择把"价格层面"拉进 scope，不再坚持纯净。

**How to apply**：
- 引擎输出的 `confidence` 字段仍只反映宋体系内的判定（不要把外部特征 fold 进去）
- 新外部特征一律走 `signal.context_features[key] = float`，**numeric only**（避免 schema 噪音）
- 每个新 context_feature 上线前：① codex review --uncommitted；② 走 OOS 3-split 验证（参考 [[project-cn-policy-oos-validated]] 的 harness 模式）
- 跨出宋体系的字段在 contract doc 必须明确标注，consumer 想保持宋纯净可以忽略整个 dict
- Brooks / Xiao 框架的细节**属于 context_features 字段的语义来源**，但本项目不实现具体 Brooks / Xiao 操作（仍是 [[project-scope-analysis-only]] 的 "下游交易系统的事"）
- session goal "持续寻找高胜率甜区 + tip止损 + 动态止损 + 分仓止盈 + MM 止盈" 是所有新 feature 的取舍标尺：能让下游执行这些操作更容易的 feature 优先

**Z roadmap reframe**（goal 重排序后）：
- Z1 ✅ candidate_rejection_wick_ratio（已 ship）
- **下一步候选**（按 "对 tip止损 / MM止盈 / Brooks/Xiao 操作的赋能"排序）：
  - **invalidation_level**：顶 = price extreme bar 的 high + 1 tick；底反之 → 直接给下游 tip 止损位
  - **measured_move_target**：基于前一同向 swing 距离投影，给下游 MM 止盈位
  - **prior_swing_distance**：候选 bar 距前一同向 swing extreme 的距离（绝对值 + 百分比），Brooks measured move 的基础数据
  - volume_relative：candidate bar volume / 前 N 根 mean，Brooks signal-bar 量价确认
  - bar_narrative：trend bar / reversal bar / signal bar 三态分类（Brooks 风格）
- 顺序由用户 + codex 共审决定，不是固定的
