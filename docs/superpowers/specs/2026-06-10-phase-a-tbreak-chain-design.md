# Phase A — 趋势线破位检测器 + 背离 Alert 链 设计

**日期**: 2026-06-10
**上游文档**: `doc/design/paired_options_direction_2026-06-10.md`（§3 肖机制链、§6 Phase A）
**状态**: 设计已确认（用户授权按推荐默认执行）

## 1. 目标与非目标

**目标**：在迁移/期权数据到位之前，把肖体系的"右侧确认"链路建好：

> 标的 MACD 背离（alert）→ 趋势线破位（右侧确认）→ put/call 候选事件

交付物是**候选事件清单**（按池分组的 JSON + 汇总），供迁移后的权利金空间
harness 直接消费。

**非目标**（明确不做）：
- ❌ 不做 EV 判定 / PROMOTE 结论——R 空间回测对 put 链是方法错误
  （见上游文档 §2.1），权利金空间验证等数据到位。
- ❌ 不进 8 条生产 emit lane，不动任何 baseline，`policy_weight` 恒为 0.0。
- ❌ 不实现 1B/2B/3B 结构层（黑盒，等材料提取）。
- ❌ 不做工程杂务（BaseOTMSelector / Black-76）——独立小改动另行处理。

## 2. 方案选择（已决策）

趋势线算法三选一：

| 方案 | 描述 | 决策 |
|---|---|---|
| **A. 枢轴两点连线** | 最近两个抬高 swing low（支撑线）/ 降低 swing high（压力线）连线延长 | ✅ **选定**——和肖手画趋势线同构，拿到她的标注图后可直接对照校准；简单可解释 |
| B. 回归通道 | lookback 窗口线性回归 ± band | ❌ 不是 discretionary trader 画的东西，无法对图校准 |
| C. 多触点拟合 | 枢轴集合上找触点最多的线 | ❌ 无标注数据时是过度工程；触点数降级为质量特征保留 |

## 3. 架构

三个新组件 + 一个扫描脚本，全部因果（无 lookahead）：

```
engine/features/trendline.py          纯几何层
    fit_trendline(bars, up_to_idx, kind, pivot_n, ...) -> Trendline | None
    Trendline: anchor 枢轴 (idx, price) ×2、slope、value_at(idx)、touches

engine/divergence/tbreak_detector.py  检测器层（仿 bpull/vflush 约定）
    @dataclass TBreakSignal: bar_idx, timestamp, direction, features, line meta
    TBreakDetector(pivot_n=5, buffer_atr=0.1, confirm_bars=1, min_gap=10)
        .scan(bars, h_bars=None) -> list[TBreakSignal]
        .policy_weight(...) -> 0.0   # alert-only，永不进生产权重
    direction: "breakdown"（跌破上升支撑线）| "breakout"（突破下降压力线）

engine/divergence/alert_chain.py      链路组合层
    divergence_alerts(bars, ...) -> list[DivAlert]
        # 取 pre-gate 原始背离（绕开 direction_gate 的 top 降权/丢弃），
        # 双向输出，alert_min_confidence=0.3
    combine(alerts, tbreaks, lookback=20) -> list[ChainEvent]
        # top 背离 alert + breakdown（lookback 内）→ put_candidate
        # bottom 背离 alert + breakout（lookback 内）→ call_candidate
        # ChainEvent 携带两端信号的完整引用 + 间隔 bar 数

scripts/scan_tbreak_chain.py          全池扫描
    所有 CN 池 + US，日线；输出按池分组 JSON + stdout 汇总
    （events/year per pool/symbol；put 候选重点池=工业品，call=贵金属）
```

**复用**：枢轴检测复用 `pa_structure.py` 的 5-bar fractal 约定
（`confirmed_at = bar + n`，只用 `confirmed_at <= up_to_idx` 的枢轴）；
ATR 复用现有 features；背离复用 `detect_intra_cycle/inter_cycle/inter_segment`
（pre-gate 调用，或给 `detect_all_divergences` 加 `gate=True` 默认参数）。

## 4. 默认参数（全部构造参数，等肖材料校准）

| 参数 | 默认 | 说明 |
|---|---|---|
| pivot_n | 5 | fractal 半宽，与 PAStructure 一致 |
| 锚点 | 最近 2 个同向枢轴 | 支撑线要求抬高 low、压力线要求降低 high |
| buffer | 0.1 × ATR(14) | 收盘穿线超过缓冲才算破，防贴线假破 |
| confirm_bars | 1 | 1=当根收盘即破；2=次根不收回才确认 |
| min_gap | 10 bars | 同向破位信号最小间隔 |
| alert_min_confidence | 0.3 | 背离 alert 最低置信度 |
| chain lookback | 20 bars | 破位向前回看背离 alert 的窗口 |
| 级别 | daily | 60min 留参数不开 |

## 5. 测试与验收

**测试**（仿 `test_b1_bottom_detector.py` 模式，合成 K 线 fixture）：
1. 几何正确性：构造已知枢轴的合成上升段，验证线方程与 value_at。
2. 破位判定：贴线不破（缓冲内）不发信号；穿越缓冲发 breakdown。
3. **因果性**：对 bars[:i] 扫描的结果，在追加未来 bars 后逐 bar 不变。
4. min_gap 去重；confirm_bars=2 的次根收回撤销路径。
5. 链路：窗口内/外配对、方向映射（top+breakdown→put / bottom+breakout→call）。
6. policy_weight 恒 0。

**验收标准**（Phase A 完成的定义）：
- 全部测试通过，`uv run pytest` 全绿（现有 504 不回归）。
- `scan_tbreak_chain.py` 在本机数据上跑通，产出按池 JSON 事件清单 +
  年度事件数汇总（数量级 sanity：每品种每年破位事件应在个位数到几十，
  不是 0 也不是数百——超出即参数或 bug 嫌疑）。
- 不产生任何 EV 声明；STATUS.md 不加 lane；baselines/ 不动。

## 6. 校准路径（材料到手后）

肖的标注图 → 逐图核对：枢轴选取是否一致、线画法是否一致、破位点是否一致。
偏差通过 §4 参数调整吸收；吸收不了的（如她用第三点修线、用影线而非收盘）
再改几何层。标注图本身转化为回归测试 fixture（"算法在该图必须标出与她一致的点"）。
