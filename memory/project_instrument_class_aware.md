---
name: project-instrument-class-aware
description: Engine 全链路 instrument_class 支持 (us_equity / cn_futures)，2026-05-24 落地
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**事实**（2026-05-24 完成）：engine 全链路接受 `instrument_class: Literal["us_equity", "cn_futures"]` 参数。

涉及组件：
- `engine/divergence/direction_gate.py`：multiplier 表按 class 分离。`us_equity` 用 5y SPY 校准的 hidden=0 / weakness=0.7 / inter_segment=0.5 / gap=1.2 等；`cn_futures` 全 1.0 pass-through（CN tops 实际 +0.65% mean，US 校准过度惩罚）。
- `engine/divergence/detector.py`：`detect_all_divergences(..., instrument_class="us_equity")` 透传给 `gate_signals`。
- `engine/divergence/downstream_policies.py`：`apply_policy(sig, instrument_class)` 分派到 `_apply_us_equity` (F1/F2/F3/F4/B1/F8) 或 `_apply_cn_futures` (F8'/CN1/baseline)。
- `engine/output/build.py`：`build_analysis_output(..., instrument_class="us_equity")` 串到 detect + policy。
- `engine/output/envelope.py`：v1.2 加 `instrument_class: str = "us_equity"` 字段。默认值保持向后兼容。

**Why**: 2026-05-24 国内期货 backtest 发现 CN tops 是正向 (+0.65%, 55.8% hit, n=400)，而 direction_gate 之前 hard-baked 美股 top de-weight，对 CN 信号 over-conservative。之前 `CN1-top-passthrough` policy rule 只能在 policy 层 weight=1.0 但不能撤销已 baked 进 confidence 的 gate 惩罚。这个修复让 CN 调用者从 detect 层就跳过 gate，confidence 完整保留。

**How to apply**:
- US 股票/期权（默认）: `build_analysis_output("SPY", bars)` 即可，行为不变
- 国内期货: `build_analysis_output("IF0", bars, instrument_class="cn_futures")` — gate pass-through + CN policy
- Schema v1.2 输出含 `instrument_class` 字段告诉下游用了哪套校准
- 添加新 instrument_class 步骤：① 在 `direction_gate._TABLES_BY_CLASS` 加表 ② 在 `downstream_policies.apply_policy` 加分派 ③ Literal type 更新

**测试覆盖**：8 个新 test (test_divergence::TestDirectionGateInstrumentClass) + 4 个 policy test (TestInstrumentClassCnFutures) + 2 个 envelope test。总测试 131 通过。

**未来候选** instrument classes:
- `us_options` — 期权 premium 时间序列上 detection（已知不适配，但接口预留）
- `cn_etf` — 国内 ETF (510050/510300 等)
- `crypto` — 数字货币 24h 市场
