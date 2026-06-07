# 03 — 数据模型

> 本文档定义系统维护的核心数据结构。使用伪 schema（YAML 风格）表示，**不是代码**，实现者可用任何语言/库表达。

---

## 1. K 线（Bar）

每个时间级别的基本数据单位。

```yaml
Bar:
  level: 时间级别 ID（如 "1h"）
  start_ts: 区间起始时间戳
  end_ts: 区间结束时间戳（含）
  open: 开盘价
  high: 最高价
  low: 最低价
  close: 收盘价
  volume: 成交量（保留字段，本系统不消费）
  is_completed: bool  # 是否已收盘
```

**约束**：
- 同一级别 K 线时间戳必须单调递增
- 同一级别 K 线时长（end_ts - start_ts）必须恒定
- `is_completed = false` 的 K 线只能是最新一根

## 2. 时间级别（Level）

```yaml
Level:
  id: 字符串（"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "D", "3D", "W", "2W", "M", "Q", "6M", "Y"）
  rank: int  # 在级别序列中的位置
  interval_seconds: int  # 该级别 K 线的时长（秒）
  symbol_compat: 该品种是否支持此级别
```

**约束**：
- 各品种的级别清单不同（A 股跳过 6h/12h，数币完整 2 倍递进）
- 级别 ID 必须唯一稳定，用作所有跨级别数据的索引键

## 3. 级别状态（LevelState）

每个级别维护一份独立的状态对象。

```yaml
LevelState:
  level_id: str

  bars:
    completed: List[Bar]   # 已收盘的 K 线序列
    live: Bar | null       # 当前未收盘的 K 线

  indicators:
    completed:
      dif: List[float]
      dea: List[float]
      hist: List[float]
      ema12: List[float]
      ema24: List[float]
      ema52: List[float]
    live:
      dif: float | null
      dea: float | null
      hist: float | null
      ema12: float | null
      ema24: float | null
      ema52: float | null

  features:                 # 5 个基础观测流（详见 04）
    dif_proximity_zero: float
    hist_amplitude_ratio: float
    hist_dif_sign_alignment: bool
    state_persistence: int
    price_momentum: float

  form_confidences:         # 6 种基础形态的当前置信度（详见 05）
    high_position: float
    high_position_void: float
    hidden: float
    zero_stick: float       # 零轴黏合
    zero_inverted: float    # 零轴倒挂
    near_zero_axis: float

  k_structure:              # K 线走势结构（详见 06）
    type: "strong" | "ultra_strong" | "weak" | null

  current_heap: HeapState | null
  current_cycle: CycleState | null
  current_segment: SegmentState

  trend_side: "bullish" | "bearish" | "transition"

  validity:                  # 当值有效性（详见 08）
    is_active: bool
    failure_reason: str | null
```

## 4. 量能堆（HeapState）

```yaml
HeapState:
  heap_id: str  # 唯一 ID（用于跨周期追溯）
  parent_cycle_id: str
  parent_segment_id: str

  sign: "positive" | "negative"  # 多头堆 or 空头堆
  start_bar_index: int
  end_bar_index: int | null      # null = 仍在进行中

  bars_in_heap: int               # 堆内 K 线根数
  peak_hist_value: float          # 堆内最高柱
  current_hist_value: float       # 当前柱（live 或最新 completed）

  is_continuous_gap: bool         # 是否处于连续跳空形态
  zero_streak: int                # 当前已连续接近零的根数

  is_completed: bool
```

**重要状态**：
- `peak_hist_value` 在堆进行中持续更新
- `is_continuous_gap` 在堆中间出现 Hist ≈ 0（但未反向释放）时标记
- 堆边界事件触发条件：见 [`06-vector-units.md`](./06-vector-units.md)

## 5. 单位调整周期（CycleState）

```yaml
CycleState:
  cycle_id: str
  parent_segment_id: str

  start_bar_index: int            # DIF 从零轴出发的根
  end_bar_index: int | null       # 黄白线归零的根（null=未结束）

  heaps: List[HeapState]          # 周期内的量能堆序列
  reference_heap_id: str          # 1 号参考点（动态可变，详见 06）

  peak_dif_distance: float        # 周期内 DIF 离零轴的最大距离
  current_dif_distance: float

  is_completed: bool

  divergence_signals:             # 周期内背离嫌疑
    continuous_gap_divergence: float    # 连续跳空背离置信度
    discrete_gap_divergence: float      # 分立跳空背离置信度
    hidden_divergence: float            # 隐形背离置信度
```

## 6. 线段（SegmentState）

```yaml
SegmentState:
  segment_id: str
  parent_level: str

  direction: "up" | "down"        # 上涨线段 or 下跌线段
  start_bar_index: int            # 黄线穿零轴的根
  end_bar_index: int | null

  cycles: List[CycleState]
  highest_cycle_peak_dif: float   # 线段内最高单位周期的 DIF 高度

  reference_cycle_id: str         # 线段的 1 号参考点（首个或最高周期）

  is_completed: bool

  divergence_signals:
    inter_cycle_divergence: float   # 周期间背离置信度
    inter_cycle_weakness: float     # 周期间动能不足置信度
    inter_segment_divergence: float # 线段间背离置信度（升级后才能算）
```

## 7. 跨级别关系（LevelTopology）

```yaml
LevelTopology:
  direct_children:        # 每个级别的直系第一代集合
    "12h": ["6h", "3h", "2h", "1h", "30m", "15m", "10m", "5m"]
    "6h":  ["3h", "2h", "1h", "30m", "15m", "10m", "5m"]
    ...

  nesting_chain:          # 每个级别的嵌套链（取最大子级别递归）
    "12h": ["12h", "6h", "3h", "2h", "1h", "30m", "15m", "10m", "5m", "3m", "1m"]
    "1h":  ["1h", "30m", "15m", "10m", "5m", "3m", "1m"]
    ...

  parent_chain:           # 每个级别的长级别链（向上）
    "1h":  ["2h", "4h", "12h", "D", "3D", ...]
    ...
```

**约束**：
- 该拓扑由 `level_registry` 在系统启动时构建
- 不同品种的拓扑不同（与级别序列相关）
- 拓扑不可变（系统运行期间不变化）

## 8. 跨级别状态（CrossLevelState）

```yaml
CrossLevelState:
  primary_label: str       # 主标签（见 11-output-schema）
  primary_confidence: float

  secondary_labels: List[(label, confidence)]

  alignment_strength: float  # 多级别协同度

  bottom_phase: "phase_1" | "phase_2" | "phase_3" | "phase_4" | "not_applicable"
  v_reversal_confidence: float
  level_upgrade_confidence: float

  cascade_failure_warnings: List[str]   # 触发级联失效的级别

  nesting_chain_state:                  # 沿嵌套链的状态摘要
    main_level: str
    chain_progress: List[(level_id, completion_pct)]
```

## 9. 系统全局状态（SystemState）

```yaml
SystemState:
  symbol: str
  schema_version: str
  system_ts: timestamp
  data_ts: timestamp                    # 最新数据的时间戳

  levels: Dict[level_id, LevelState]    # 各级别独立状态
  topology: LevelTopology
  cross_level: CrossLevelState

  events_pending: List[EventCandidate]
  events_history: List[Event]           # 已触发的历史事件（带 TTL）
```

## 10. 事件对象（Event / EventCandidate）

```yaml
EventCandidate:
  label: str                    # 事件标签（见 11-output-schema）
  level_id: str                  # 主要发生级别
  confidence: float
  vector_unit: "heap" | "cycle" | "segment" | "none"
  data_ts: timestamp
  system_ts: timestamp
  reasoning: str                 # 简要触发原因
  related_levels: List[str]      # 协同/影响的其他级别

Event:                            # = EventCandidate + 已确认状态
  ... 同 EventCandidate
  confirmed_at: timestamp | null
  invalidated_at: timestamp | null
  invalidation_reason: str | null
```

## 11. 数据生命周期

### 11.1 K 线生命周期

```
新 tick → live Bar 更新 → 收盘时刻 → completed → 永久保留（截至缓存策略）
```

### 11.2 矢量单元生命周期

```
启动事件 → live state → 边界事件 → completed → 归档进入父容器
```

### 11.3 事件生命周期

```
预警阶段 (EventCandidate) → 候选 → 确认 (Event)
            ↓ 失效
        invalidated_at 标记
```

## 12. 缓存策略建议

- **K 线缓存**：每级别保留**至少 200 根** completed K 线（满足 EMA52 warmup + 跨多个线段的可视化需求）
- **矢量单元缓存**：当前线段及其内部所有 cycles/heaps 必须缓存；历史线段可视情况归档
- **事件缓存**：最近 N 个已确认事件 + 当前所有待确认候选

## 13. 数据完整性约束

实现时应当强制检查：

1. K 线时间戳严格递增、间隔恒定
2. 每个 cycle 至少含一个 heap
3. 每个 segment 至少含一个 cycle
4. heap → cycle → segment 的 parent_id 一致
5. 跨级别的对齐时刻一致（详见 04 与 13）
6. 任意时刻只允许一个 live K 线 / heap / cycle / segment（每级别）

违反任何一条 = 数据损坏，应触发 fail-fast。
