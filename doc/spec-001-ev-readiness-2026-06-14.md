# SPEC-001 EV/边缘评估 — readiness 评估与方法学（2026-06-14）

卡片 t_0da3b750（philosopher → researcher 交付：楔形完成二次入场突破做多）。
**结论先行：当前无法给出有意义的 EV——可评估的复刻语料只有 N=1 笔 SPEC-001 多单。**
本文件给出（1）语料现状，（2）已验证的出场仿真方法（单实例闭环 +2.0R），
（3）忠实计 EV 必须先与 philosopher 敲定的约定，（4）解锁后的 EV 口径与所需样本量。

## 1. 语料现状（阻塞点）

philosopher 复刻体（`scripts/replay_cn.py`，每节点跑一次 LLM replica）目前仅产出 1 个
replay 工件 `runs/_replica/replay_rb2607_5min.json`：23 个评测节点、**仅 2 笔下单**
（`n_order=2`），其中：

- **1 笔 SPEC-001 多单**（rb2607 2025-07-23 10:05，E/S/T=3379/3365/3407，2:1）——本卡目标。
- 1 笔做空突破单（非 SPEC-001）。

即 SPEC-001 多单语料 **N=1**。胜率/期望/盈亏分布/跨品种·周期·市场态稳健性/净 EV
**全部需要规模样本**，N=1 无法支撑任何统计结论。复刻体高度选择性（23 节点仅 2 单）是 PA
特征（philosopher 强调不应被"优化"掉），但也意味着凑足样本需要跨大量品种×长历史的复刻运行。

## 2. 已验证的出场仿真（单实例闭环）

复刻输出只记**订单**（entry/stop/target/direction），**不记实际出场结果**——故 EV 需逐K
前向仿真。已建 harness `src/scripts/eval_spec001_ev.py`（消费 replay JSON + philosopher
`tp.pa.cn_data` 5min 接口），自检复现 spec 单实例：

- rb2607 多单：买 stop 3379 于 **2025-07-24 13:35** 触发（前向首根 high≥3379），
  **14:45 触及 3407 止盈 → +2.0R**，与 spec §7 documented outcome 完全一致。✓
- `python3 scripts/eval_spec001_ev.py --validate` → PASS（+2.0R target）。8 个单测覆盖
  多/空、target/stop/timeout、同根 stop-first、未触发、成本。

时间戳口径：复刻节点 `end` 与 cn_data `ts_open` **均为 UTC epoch**（已核对，10:05 节点 ==
ts_open 10:05 UTC）。早期一版 −1R 是本地时区误用，非真实失败。

## 3. 忠实计 EV 必须先敲定的约定（→ philosopher）

逐K仿真暴露出几处**对结果决定性、但复刻输出未确定性记录**的约定：

1. **入场前失效（最关键）**：rb2607 入场前（买 stop 3379 于 07-24 13:35 触发前），价格最低
   下探到 **3334**（07-23 14:25）——**既低于止损 3365、也低于复刻 `invalidation_condition`
   的 3352**。即按**任何**入场前失效判据（3366/3365/3352）该 setup 都应作废、**不会有这笔 +2R**。
   〔更正（reviewer t_9ef7dc76）：本文件早先称"唯有按 3352 才保持有效"是**错的**——3334<3352。〕
   故本 harness 的 `--validate`/`simulate_order` 是**纯出场引擎**：**完全不建模入场前失效**
   （挂单一直挂到触发）。+2R 只证明出场引擎复现了 documented 的"入场→止盈"路径，**不**证明
   挂单在复刻失效条件下仍然有效。`invalidation_condition` 是自由文本（含"强势空头信号棒"模糊项），
   **无法机械判定**——是否建模入场前失效是**待定约定**。
2. **挂单有效期**：买 stop 触发前可挂多久？（本例隔日 13:35 才触发，需有效期约定）。
3. **同根 stop/target 优先级**：本 harness 取 stop-first（保守），需确认。
4. **超时/管理出场**：§11 管理规则随样本追加，目前仅 target/stop/timeout。

**这些不能由 researcher 主观拍板**（违反"复刻体不应比交易员更聪明"）。建议二选一：
(a) 复刻 replay 输出**每单附实际出场结果**（出场价/类型/R），researcher 仅叠加成本算净 EV；或
(b) philosopher 给出**确定性出场/失效约定**（入场前失效判据、有效期、同根优先级、管理出场），
researcher 据此跑 harness。

## 4. 解锁后的 EV 口径 + 所需样本

- **毛 EV**：逐K仿真得每单 R；报 win-rate、mean/median R、R 分布、target/stop/timeout 占比。
- **净 EV**：减成本（滑点 + 手续费 + 换月）。以 R 计：`cost_R = (滑点tick×tickval + 手续费)/风险点数`。
  rb 例风险=14 点，若滑点 2 跳 + 手续费 ≈ 1 点等值 → ~0.2R/单。harness `--cost-r` 可调。
- **稳健性**：按品种（ag/au/cu/rb/sc…）、周期、市场态（cycle: broad/normal/tight channel…）分层。
- **样本量**：单边 2:1 setup，若真实胜率 ~50–55%，要把 EV 的 95% CI 收到 ±0.3R 量级，
  约需 **N≈30–50 笔 SPEC-001 多单**（bootstrap 口径，与本仓既有 lane 验证一致）。
  按 rb2607 选择性（~1 单/2 周/品种），需跨 ~10+ 品种 × 数月 × 5min 复刻运行。

## 5. 给 philosopher 的语料请求（另建卡）

请复刻体批量产出 SPEC-001 多单语料：多品种（建议 ag/au/cu/al/rb/i/sc 等流动性品种）×
2024–2025 多段窗口 × 5min，落 `runs/_replica/replay_*.json`；目标累计 ≥30–50 笔多单。
并请明确 §3 的出场/失效约定，或在 replay 输出中附每单实际出场结果。

## 局限
harness 出场约定为**显式假设、待 philosopher 批准**（见 §3），当前仅在 rb2607 单实例上
对齐 spec。数据走 philosopher `tp.pa.cn_data`（5min，SHFE parquet）。
脚本 `src/scripts/eval_spec001_ev.py` + 8 单测；复现：
`cd src && python3 scripts/eval_spec001_ev.py --validate`（philosopher 源由 `_resolve_tp_src()` 自动解析，
HOME 异常的 Hermes worker 下亦可，无需手动指定；非标准布局可 `--philosopher-src <path>` 或设 `TP_PA_SRC`）。
