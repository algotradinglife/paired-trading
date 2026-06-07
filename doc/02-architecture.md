# 02 — 整体架构

## 1. 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ Layer E: 输出层                                          │
│   - 状态快照、合成结论、事件清单                          │
│   - schema 详见 11-output-schema.md                       │
└──────────────────────────────────────────────────────────┘
                              ▲
┌──────────────────────────────────────────────────────────┐
│ Layer D: 多周期信息融合层                                 │
│   - 直系第一代扫描、嵌套链遍历                            │
│   - 双向置信度传播                                        │
│   - 级联失效检测                                          │
│   - 复合事件判定（底部变盘、V 字反转、级别升级）          │
└──────────────────────────────────────────────────────────┘
                              ▲
┌──────────────────────────────────────────────────────────┐
│ Layer C: 单级别判定层                                     │
│   - 形态识别（高位空、隐形、黏合、倒挂）                   │
│   - 矢量单元状态机（堆、周期、线段）                       │
│   - 穿零轴判定                                            │
│   - 背离判定（周期内、周期间、线段间）                     │
│   - K 线走势结构分类                                      │
└──────────────────────────────────────────────────────────┘
                              ▲
┌──────────────────────────────────────────────────────────┐
│ Layer B: 特征提取层                                       │
│   - DIF / DEA / Histogram 计算                            │
│   - EMA24 / EMA52 计算                                    │
│   - 5 个基础观测流（详见 04-feature-extraction.md）       │
└──────────────────────────────────────────────────────────┘
                              ▲
┌──────────────────────────────────────────────────────────┐
│ Layer A: 数据输入层                                       │
│   - 多时间级别 K 线 OHLC 流                               │
│   - 每个级别独立维护                                       │
│   - completed K 线 + live K 线双轨                        │
└──────────────────────────────────────────────────────────┘
```

## 2. 模块划分

按层级展开，每层包含若干模块。建议下游项目按此粒度组织代码。

### Layer A — 数据输入

| 模块 | 职责 |
|------|------|
| `level_registry` | 维护本品种支持的时间级别清单（与品种类型相关） |
| `bar_aggregator` | 从基础级别 K 线聚合到各更大级别 |
| `bar_stream` | 提供每级别的 K 线流（completed 与 live） |
| `alignment_detector` | 识别多级别同时收盘的"对齐时刻" |

### Layer B — 特征提取

| 模块 | 职责 |
|------|------|
| `macd_calculator` | 计算 DIF / DEA / Histogram（每级别独立） |
| `ema_calculator` | 计算 EMA24 / EMA52（每级别独立） |
| `feature_stream` | 输出 5 个基础观测流（详见 04） |

### Layer C — 单级别判定

| 模块 | 职责 |
|------|------|
| `form_detector` | 识别 6 种基础形态，输出预置信度 |
| `heap_machine` | 量能堆状态机（边界、峰值、当前候选） |
| `cycle_machine` | 单位调整周期状态机 |
| `segment_machine` | 线段状态机（含 1 号参考点动态管理） |
| `zero_axis_detector` | 穿零轴三阶段判定（预警/候选/确认） |
| `divergence_detector` | 三类背离（周期内/周期间/线段间）统一比较器 |
| `k_structure_classifier` | K 线走势结构分类（强势/超强势/弱势） |

### Layer D — 多周期融合

| 模块 | 职责 |
|------|------|
| `level_topology` | 维护级别之间的直系/嵌套关系 |
| `confidence_propagator` | 双向置信度传播（top-down + bottom-up） |
| `validity_tracker` | 第一代级别"当值有效性"维护 |
| `cascade_failure_monitor` | 级联失效检测 |
| `bottom_phase_machine` | 底部变盘四阶段状态机 |
| `v_reversal_detector` | V 字反转复合条件检测 |
| `level_upgrade_detector` | 时间级别升级判定 |
| `chain_walker` | 沿嵌套链遍历（用于顶部判定） |
| `directs_scanner` | 扫描直系第一代集合（用于启动判定） |

### Layer E — 输出

| 模块 | 职责 |
|------|------|
| `state_snapshot_builder` | 构建各级别状态快照 |
| `synthesis_engine` | 跨级别状态汇总成主/辅助标签 |
| `event_ranker` | 关注事件按重要性排序 |
| `output_serializer` | 序列化为 API schema 格式 |

## 3. 数据流

### 3.1 实时数据流（live mode）

```
新 tick / K 线更新
    ↓
Layer A: 更新各级别的 live K 线状态
    ↓
Layer B: 对受影响的级别重算 MACD / EMA（live 值）
    ↓
Layer C: 单级别预置信度更新
    ↓
Layer D: 跨级别融合更新
    ↓
Layer E: 输出当前快照
```

### 3.2 K 线收盘流（completed mode）

```
某级别 K 线收盘
    ↓
Layer A: 标记该级别的当前 K 线为 completed
    ↓
Layer B: 锁定该 K 线的 MACD / EMA 值
    ↓
Layer C: 触发严格事件判定（穿零轴次根确认、单元边界事件等）
    ↓
Layer D: 触发可能的状态转移（线段切换、级别升级、阶段推进）
    ↓
Layer E: 输出严格事件快照（带可追溯性）
```

### 3.3 对齐时刻特殊处理

多个级别同时收盘的时刻（详见 [`13-edge-cases.md`](./13-edge-cases.md)）：

```
检测到对齐时刻
    ↓
所有对齐级别的 completed 流同时触发
    ↓
跨级别一致性检查（detect cross-level conflicts）
    ↓
融合结论的高置信度时机（标记为"对齐确认"）
```

## 4. 关键设计原则

### 4.1 每个时间级别独立

- 独立的 OHLC 序列
- 独立的 MACD / EMA 计算
- 独立的状态机（堆/周期/线段）
- 独立的形态置信度

跨级别交互**只发生在 Layer D**（融合层），其他层级保持级别隔离。

### 4.2 completed 与 live 双轨

每个级别同时维护：
- `completed_state` — 已收盘 K 线计算的状态（严格、滞后）
- `live_state` — 含未收盘 K 线的当前状态（漂移、实时）

不同的判定模块按需消费。

### 4.3 置信度全程连续

所有事件输出**连续置信度** $\in [0, 1]$，**不输出布尔状态**。下游消费者按自己的阈值决策。

详见 [`10-confidence-model.md`](./10-confidence-model.md)。

### 4.4 状态机的原子转移

线段切换、级别升级等"重大转移"必须**原子化**——不允许出现"半切换"中间态。

详见 [`06-vector-units.md`](./06-vector-units.md), [`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md)。

### 4.5 可追溯性

每个输出标签携带"为何这么判定"的简要原因（用了哪些规则、哪些级别协同），便于下游审计。

## 5. 模块间接口（高层）

下面是模块间消息流的概念视图。具体接口设计由实现者决定。

| 上游模块 | 下游模块 | 消息 |
|---------|---------|------|
| `bar_stream` | `macd_calculator` | 新 K 线 + 完成状态 |
| `macd_calculator` | `feature_stream` | MACD 当前值 |
| `feature_stream` | `form_detector` | 5 个观测量当前值 |
| `feature_stream` | `heap_machine` | Hist 序列变化 |
| `heap_machine` | `cycle_machine` | 堆边界事件 |
| `cycle_machine` | `segment_machine` | 周期边界事件 |
| `segment_machine` | `zero_axis_detector` | 候选穿零事件 |
| `form_detector` | `divergence_detector` | 形态置信度 |
| `*_machine` | `confidence_propagator` | 状态变化 |
| `confidence_propagator` | `synthesis_engine` | 跨级别合成置信度 |
| `synthesis_engine` | `output_serializer` | 主/辅助标签 |
| `*` | `event_ranker` | 待排序事件 |

## 6. 并发与时序

- 单品种内：建议**串行处理 K 线流**，避免状态机并发问题
- 多品种间：可以**并行处理**，每个品种一个独立的系统实例
- 时间戳：所有事件携带 `data_ts`（K 线时间）与 `system_ts`（处理时间）

详见 [`13-edge-cases.md`](./13-edge-cases.md) 的时序章节。

## 7. 与下游项目的边界

本系统输出到下游的接口只走 Layer E。下游：

- 消费输出 schema（见 [`11-output-schema.md`](./11-output-schema.md)）
- 不直接访问 Layer A-D 的内部状态
- 不耦合到本系统的实现细节

→ 这保证未来本系统可以独立升级，下游受影响最小。
