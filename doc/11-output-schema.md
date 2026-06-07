# 11 — 输出 API Schema

> 系统对下游的稳定接口。三层结构：各级别快照 + 跨级别合成 + 关注事件清单。

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **稳定** | schema 版本化，向后兼容；新字段只增不删 |
| **结构化** | 嵌套 + 明确字段名，下游可选择性消费 |
| **可追溯** | 每个结论附带"为何这么判定"的简要原因 |
| **置信度优先** | 所有判定字段都带置信度数值 |
| **时间戳齐全** | 区分 `data_ts`（K 线时间）与 `system_ts`（系统输出时间） |
| **品种无关** | 同一 schema 适用所有品种和级别 |

## 2. 顶层结构

```yaml
OutputObject:
  meta: MetaInfo
  per_level: Dict[level_id, LevelSnapshot]
  cross_level: CrossLevelSummary
  events: List[Event]
```

三层从下到上的语义：

- `per_level` — **原始状态**，下游可基于此自己合成
- `cross_level` — **已合成的核心判定**，下游直接消费
- `events` — **按优先级排序的关注事项**，下游按阈值过滤

## 3. MetaInfo

```yaml
MetaInfo:
  symbol: str                    # 品种标识（"SHFE.cu2509" / "BTC-USDT" / "000001.SZ"）
  schema_version: str             # "1.0.0"（语义化版本）
  system_ts: timestamp_iso8601    # 系统输出时间（含时区）
  data_ts: timestamp_iso8601      # 最新数据的时间戳（含时区）
  supported_levels: List[str]     # 本品种支持的级别清单
  output_mode: per_tick | per_bar # 输出模式
  trigger_reason: str             # 触发本次输出的原因（如 "1h bar closed"）
```

## 4. LevelSnapshot（每级别一份）

```yaml
LevelSnapshot:
  level_id: str
  is_completed: bool              # 当前 K 线是否已收盘

  bar:                            # 最新 K 线（live 或 completed）
    start_ts: timestamp
    end_ts: timestamp
    open: float
    high: float
    low: float
    close: float

  indicators_live:                # 含未收盘 K 线的当前指标
    dif: float
    dea: float
    hist: float
    ema12: float
    ema24: float
    ema52: float

  indicators_completed:           # 仅已收盘 K 线的指标（稳定值）
    dif: float
    dea: float
    hist: float
    ema12: float
    ema24: float
    ema52: float

  features:                       # 5 个基础观测流（详见 04）
    dif_proximity_zero: float     # [0, 1]
    hist_amplitude_ratio: float   # [0, 1+)
    hist_dif_sign_alignment: int  # {-1, 0, +1}
    state_persistence: int        # 当前形态持续根数
    price_momentum: float         # 价格短期增量

  form_confidences:               # 6 种形态的置信度
    high_position: float
    high_position_void: float
    hidden: float
    hidden_subtype: high | near_zero | none
    zero_stick: float
    zero_inverted: float
    near_zero_axis: float
    near_zero_perfect: bool

  k_structure:                    # K 线走势结构
    type: strong | ultra_strong | weak | none
    confidence: float

  vector_units:
    heap:
      heap_id: str
      state: HeapState
      peak_value: float
      bars_in_heap: int
      is_continuous_gap: bool
    cycle:
      cycle_id: str
      state: CycleState
      peak_dif: float
      heaps_count: int
      reference_heap_id: str
    segment:
      segment_id: str
      direction: up | down
      cycles_count: int
      segment_peak_dif: float
      reference_cycle_id: str

  trend_side: bullish | bearish | transition

  validity:                       # 当值有效性
    is_active: bool
    failure_type: zero_axis_breach | weak_push_up | null
    failure_ts: timestamp | null
```

## 5. CrossLevelSummary

```yaml
CrossLevelSummary:
  primary_label: str              # 主标签（见下表）
  primary_confidence: float

  secondary_labels:                # 次要标签清单
    - label: str
      confidence: float

  alignment_strength: float        # 多级别协同度 [0, 1]
  dominant_trend: bullish | bearish | mixed

  bottom_phase:                    # 底部变盘四阶段
    current_phase: phase_1 | phase_2 | phase_3 | phase_4 | none
    phase_confidence: float
    expected_pivot_level: str      # 哪个子级别是关键变盘级别

  v_reversal:
    confidence: float
    breakout_detected: bool

  level_upgrade:
    confidence: float
    upgrading_level: str
    target_level: str

  segment_termination:
    confidence: float
    affected_level: str

  nesting_chain:                   # 顶部判定的嵌套链状态
    main_level: str
    chain: List[str]
    chain_progress: List[(level_id, completion_pct)]
    topping_confidence: float

  cascade_failures: List[CascadeFailureWarning]
```

### 5.1 主标签的可能取值

| 主标签 | 含义 |
|--------|------|
| `stable_bullish` | 稳态多方上升 |
| `stable_bearish` | 稳态空方下跌 |
| `consolidation` | 震荡整理 |
| `near_zero_pending` | 归零轴接近中 |
| `bottom_phase_<n>` | 底部变盘第 n 阶段 |
| `segment_termination_warning` | 线段终结预警 |
| `zero_cross_candidate` | 穿零轴候选 |
| `zero_cross_confirmed` | 穿零轴确认 |
| `level_upgrade_candidate` | 级别升级候选 |
| `v_reversal_active` | V 字反转进行中 |
| `goldmine_form_detected` | 送钱形态出现 |
| `cascade_failure_warning` | 级联失效预警 |

## 6. Event

```yaml
Event:
  event_id: str                    # 唯一 ID
  label: str                        # 事件标签（见下表）

  level_id: str                     # 主要发生级别
  related_levels: List[str]          # 协同/关联级别

  stage: dormant | watching | forming | candidate | confirmed | post_hoc
  confidence: float                  # [0, 1]

  vector_unit:
    type: heap | cycle | segment | none
    unit_id: str

  timestamps:
    detected_at: timestamp           # 首次检测到的时间
    last_updated_at: timestamp        # 最近更新置信度的时间
    confirmed_at: timestamp | null   # 确认时间（如有）
    invalidated_at: timestamp | null # 失效时间（如有）

  details:                          # 事件类型相关的额外字段
    # 因事件类型而异，参考下文 6.2

  reasoning: str                    # 简要触发原因（一句话）

  trajectory:                       # 最近 N 根 K 线的 confidence 变化
    history: List[(ts, confidence, stage)]
```

### 6.1 事件标签清单

| 标签 | 矢量单元 | 含义 |
|------|------|------|
| `near_zero_axis_approach` | cycle | 归零轴接近 |
| `zero_axis_crossing_warning` | segment | 穿零轴预警 |
| `zero_axis_crossing_candidate` | segment | 穿零轴候选 |
| `zero_axis_crossing_confirmed` | segment | 穿零轴确认 |
| `high_position_void` | cycle | 高位空形态 |
| `hidden_form_high` | cycle | 高位隐形 |
| `hidden_form_near_zero` | cycle | 归零轴隐形 |
| `zero_stick_pattern` | cycle | 零轴黏合 |
| `zero_inverted_pattern` | cycle | 零轴倒挂 |
| `intra_cycle_divergence` | heap | 周期内背离（含跳空类） |
| `inter_cycle_divergence` | cycle | 周期间背离 |
| `inter_cycle_weakness` | cycle | 周期间动能不足 |
| `inter_segment_divergence` | segment | 线段间背离 |
| `goldmine_form` | cycle | 送钱形态 |
| `bottom_phase_transition` | segment | 底部变盘阶段切换 |
| `v_reversal_detected` | segment | V 字反转 |
| `level_upgrade_triggered` | segment | 时间级别升级 |
| `cascade_failure` | level | 级联失效预警 |

### 6.2 事件详情字段（按标签）

**zero_axis_crossing_***:
```yaml
details:
  crossing_bar_ts: timestamp
  confirmation_bar_ts: timestamp | null
  dea_crossing_value: float
  close_vs_ema52: float
  affected_segment_id: str
```

**intra_cycle_divergence / inter_cycle_divergence / inter_segment_divergence**:
```yaml
details:
  divergence_subtype: continuous_gap | discrete_gap | hidden | standard | weakness
  direction: top | bottom
  reference_unit_id: str
  candidate_unit_id: str
  reference_amplitude: float
  candidate_amplitude: float
  decay_ratio: float
  is_new_price_extreme: bool
```

**bottom_phase_transition**:
```yaml
details:
  from_phase: phase_n
  to_phase: phase_(n+1)
  pivot_sub_level: str
  v_reversal_likely: bool
```

**level_upgrade_triggered**:
```yaml
details:
  upgrading_level: str
  target_level: str
  cycles_with_inter_divergence: int     # 触发升级前的周期间背离次数
  super_level_at_zero: bool
  super_level_k_above_ema24: bool
```

**cascade_failure**:
```yaml
details:
  failed_level: str
  failure_type: zero_axis_breach | weak_push_up
  affected_super_levels: List[str]
  main_trend_termination_confidence: float
```

## 7. 输出节奏

### 7.1 两种输出模式

| 模式 | 触发 | 用途 |
|------|------|------|
| **per_tick** | 每个新价格 tick | 实时漂移监控 |
| **per_bar** | 某级别 K 线收盘 | 严格事件判定 |

### 7.2 推荐策略

- 多数严肃判定基于 **per_bar 模式**在对齐时刻的输出
- per_tick 仅用于漂移期监控（如左侧预警）
- 对齐时刻（多级别同时收盘）的输出**优先级最高**

## 8. 事件清单的排序规则

events 数组的排序优先级：

```
1. 按事件优先级（线段间 > 升级 > 穿零 > 底部阶段 > 周期间 > 送钱 > 周期内 > 形态嫌疑）
2. 在同优先级内，按 confidence 降序
3. 在同 confidence 内，按 detected_at 升序（早发现的在前）
```

## 9. 错误与异常字段

```yaml
OutputObject:
  ...
  warnings: List[str]              # 非阻塞警告（数据 gap、初值未收敛等）
  errors: List[str]                # 触发但未阻塞的错误（应在下次输出修复）
```

## 10. 版本控制

### 10.1 语义化版本

`schema_version: MAJOR.MINOR.PATCH`

- MAJOR 升级：破坏性变更（字段删除、类型变化）—— 慎重
- MINOR 升级：向后兼容的新增（新字段、新标签）
- PATCH 升级：纯修复（不影响接口）

### 10.2 兼容性

- 下游消费者**必须**先读 schema_version
- MAJOR 不匹配 → 拒绝消费
- MINOR 高于已知 → 警告但消费（忽略未知字段）

## 11. 序列化建议

- **JSON** — 标准、易用、可读
- **MessagePack** — 高频场景下更紧凑
- **Protobuf** — 严格 schema 控制时

实现者按下游需求选择。schema 本身平台无关。

## 12. 示例（节选）

```yaml
meta:
  symbol: "BTC-USDT"
  schema_version: "1.0.0"
  system_ts: "2026-05-21T16:00:01Z"
  data_ts: "2026-05-21T16:00:00Z"
  supported_levels: [1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, D, 3D, W, 2W, M]
  output_mode: per_bar
  trigger_reason: "1h bar closed"

per_level:
  "1h":
    level_id: "1h"
    is_completed: true
    features:
      dif_proximity_zero: 0.21    # 离零轴远（"高位"）
      hist_amplitude_ratio: 0.42  # 柱在衰减
      hist_dif_sign_alignment: 1
      state_persistence: 4
      price_momentum: 0.0023
    form_confidences:
      high_position: 0.79
      high_position_void: 0.68
      hidden: 0.12
      zero_stick: 0.01
      ...
    vector_units:
      cycle:
        cycle_id: "cycle_1h_42"
        peak_dif: 245.3
        heaps_count: 2
        reference_heap_id: "heap_1h_98"
      segment:
        segment_id: "seg_1h_7"
        direction: up
        cycles_count: 3
        segment_peak_dif: 312.1
    trend_side: bullish
    validity:
      is_active: true

cross_level:
  primary_label: "segment_termination_warning"
  primary_confidence: 0.72
  secondary_labels:
    - label: "high_position_void"
      confidence: 0.68
  alignment_strength: 0.76
  dominant_trend: bullish
  bottom_phase:
    current_phase: none
  level_upgrade:
    confidence: 0.18
  segment_termination:
    confidence: 0.72
    affected_level: "1h"
  nesting_chain:
    main_level: "1h"
    topping_confidence: 0.56

events:
  - event_id: "evt_001"
    label: "inter_cycle_divergence"
    level_id: "1h"
    stage: candidate
    confidence: 0.74
    vector_unit:
      type: cycle
      unit_id: "cycle_1h_42"
    details:
      divergence_subtype: standard
      direction: top
      reference_amplitude: 312.1
      candidate_amplitude: 245.3
      decay_ratio: 0.21
      is_new_price_extreme: true
    reasoning: "Price made new high, but 1h cycle peak_dif decreased from 312 to 245"
  - event_id: "evt_002"
    label: "high_position_void"
    level_id: "1h"
    stage: candidate
    confidence: 0.68
    reasoning: "DIF still far from zero, Hist decaying for 4 bars while DIF same sign"
```

## 13. 不变量

实现可作为序列化层的测试：

1. `schema_version` 始终存在且合法
2. `per_level` 的 keys ⊆ `supported_levels`
3. 所有 `confidence` ∈ [0, 1]
4. `events` 按优先级 + confidence 排序
5. `system_ts >= data_ts`
6. `confirmed_at >= detected_at`（若存在）
