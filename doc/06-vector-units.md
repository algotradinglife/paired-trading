# 06 — 时间矢量单元

> 量能堆 / 单位调整周期 / 线段是宋理论的核心容器。本文档定义这三个容器的状态机、边界事件、嵌套关系，以及 K 线走势结构的分类。

---

## 1. 三层嵌套

```
线段 (Segment)
  └── 单位调整周期 (Cycle) × 多个
        └── 量能堆 (Heap) × 多个
```

**关键约束**：
- 一个 segment 至少含一个 cycle
- 一个 cycle 至少含一个 heap
- 跨容器不可比较（背离判定的硬约束）

## 2. 量能堆（Heap）状态机

### 2.1 定义

**量能堆**：连续同号 Hist 的集合。中间可以有短暂归零，但不能有反向柱持续若干根。

### 2.2 状态

| 状态 | 含义 |
|------|------|
| `nascent` | 刚刚启动（首根同号柱） |
| `growing` | 柱体在增长 |
| `peaked` | 已达到峰值，开始衰减 |
| `decaying` | 持续衰减中 |
| `near_zero` | 当前柱接近零，但堆未结束 |
| `completed` | 堆已结束（反向柱持续若干根） |

### 2.3 边界事件

| 事件 | 触发条件 |
|------|---------|
| 堆启动 | 反向状态后首根同号柱出现 |
| 堆峰更新 | 当前 \|Hist\| > 已记录峰值 |
| 中间归零 | 连续 ≤ $g_{max}$ 根 \|Hist\| < $\epsilon$（不算反向） |
| 堆结束 | 反向 Hist 持续 $g_{max} + 1$ 根 |

**关键参数** $g_{max}$：堆"中间归零"的最大容忍根数。
- 默认建议：$g_{max} = 1$（即一根反向不切堆，两根才切）
- 详见 [`12-thresholds-and-params.md`](./12-thresholds-and-params.md)

### 2.4 连续跳空形态

**连续跳空** = 堆内出现 `near_zero` 状态但**未触发堆结束**。判定标志：

- `zero_streak ≥ 1` 且未反向 → 标记 `is_continuous_gap = true`

→ 这是周期内"连续跳空背离"的形态基础。

### 2.5 状态转移图

```
              新同号柱
              ↓
   ┌─→  nascent  → 同号柱 →  growing  → 同号柱 →  peaked  →  decaying
   │       ↑                                          │           │
   │       │                                          │           ↓ |hist|<ε
   │       │                                          │       near_zero
   │       │                                          │           │
   │       │                              恢复同向    │           │
   │       │   ←─────────────────────────────────────┴───────────┘
   │       │                                                       │
   │       │              反向持续 > g_max                          │
   └───────┴────  completed  ←───────────────────────────────────────
```

## 3. 单位调整周期（Cycle）状态机

### 3.1 定义

**单位调整周期**：黄白线从零轴**出发**到**回归**零轴的一段区间。

形式化：$\text{DIF}$ 从 $|\text{DIF}| > \tau_{exit}$（远离零轴）到 $|\text{DIF}| < \tau_{return}$（回到零轴）的连续段。

### 3.2 状态

| 状态 | 含义 |
|------|------|
| `at_zero` | 黄白线在零轴附近，等待出发 |
| `departing` | 正在远离零轴 |
| `at_high` | 已远离至高位（具体由形态层判定） |
| `returning` | 正在回归零轴 |
| `near_return` | 接近归零轴位置 |
| `completed` | 归零完成（确认事件） |

### 3.3 边界事件

| 事件 | 触发条件 |
|------|---------|
| 周期启动 | 上一周期 `completed` 后 DIF 突破 $\tau_{exit}$ |
| 远离峰值更新 | $|\text{DIF}_t| > $ 已记录峰值 |
| 接近归零 | $|\text{DIF}_t| < \tau_{return}$ |
| 归零确认 | 接近归零持续 $n_{return}$ 根 |
| 周期结束 | 归零确认（也是下一周期的潜在起点） |

**关键参数**：
- $\tau_{exit}$：判定"已离开零轴"的阈值
- $\tau_{return}$：判定"接近归零"的阈值
- $n_{return}$：归零确认所需持续根数

### 3.4 1 号参考点（动态机制）

**1 号参考点** = 当前周期内**已知最高**的量能堆的代表。用于周期内背离比较的基线。

**动态规则**：
1. 周期启动时，第一个量能堆 = 临时 1 号参考点
2. 新堆出现时：
   - 新堆峰值 > 1 号参考点 → **1 号参考点失效**，新堆成为新的 1 号参考点（这就是"跳空非背离"）
   - 新堆峰值 ≤ 1 号参考点 → 新堆成为背离候选
3. 周期结束时：1 号参考点封档归档

→ 算法上 1 号参考点是个**可变状态**，每个新堆形成时都要检查是否重置。

### 3.5 周期内"穿零轴起点"

宋的特殊处理：单位调整周期的**起点**可以是黄线穿零轴的位置（不只是"远离-回归"的远离起点）。

实现上：
- 监控黄线穿零轴事件
- 穿零轴后启动新周期，1 号参考点 = 穿零轴后**首个更高量能堆**（如无则周期为"无效周期"）

详见 [`07-zero-axis-crossing.md`](./07-zero-axis-crossing.md)。

## 4. 线段（Segment）状态机

### 4.1 定义

**线段**：黄线（DEA）第一次穿零轴到下一次反向穿零轴的整段。

- 上涨线段：DEA 上穿零轴 → DEA 下穿零轴
- 下跌线段：DEA 下穿零轴 → DEA 上穿零轴

### 4.2 状态

| 状态 | 含义 |
|------|------|
| `pending_start` | 等待 DEA 穿零轴启动 |
| `early` | 启动初期 |
| `active` | 主体运行期，可能含多个 cycle |
| `late` | 已出现衰退迹象（周期间背离/动能不足） |
| `pending_end` | 接近终结（DEA 接近反向零轴） |
| `completed` | 已结束（DEA 反向穿零轴确认） |

### 4.3 边界事件

| 事件 | 触发条件 |
|------|---------|
| 线段启动 | DEA 穿零轴确认（见 07） |
| 周期完成 | 内部 cycle 进入 `completed` |
| 衰退苗头 | 周期间背离 / 动能不足出现 |
| 线段结束 | DEA 反向穿零轴确认（见 07） |

### 4.4 线段内的"最高单位周期"

线段间背离比较所需的**线段代表值**：

$$
\text{segment\_peak\_dif} = \max_{c \in \text{segment.cycles}} \text{peak\_dif}(c)
$$

只在线段内更新。线段封档时锁定。

### 4.5 线段终结后的状态切换（原子）

线段终结 = 状态机大转移。必须**原子完成**：

```
确认线段终结
  ↓ (原子区域)
锁定旧线段所有 cycles 和 heaps
锁定旧线段 segment_peak_dif
归档 1 号参考点
启动新线段：
  - direction 翻转
  - 重置 cycles 列表
  - 重置 segment 内的所有计数
  ↓
新线段进入 early 状态
```

不允许"半切换"中间态。

## 5. K 线走势结构（K-Structure）

宋的"强势/超强势/弱势调整结构"分类。**与矢量单元并列**——它是 K 线本身的几何形态分类，不是矢量单元的子结构。

### 5.1 三种结构

| 结构 | K 线特征 | 与 EMA 关系 | MACD 表现 |
|------|---------|-----------|---------|
| 强势调整 | 高位横盘震荡 | 维持在 EMA52 之上 | DIF 缓慢趋向归零 |
| 超强势调整 | 倾斜向上缓慢上行 | 维持在 EMA24 之上 | DIF 缓慢趋向归零，破前高 |
| 弱势调整 | 快速下跌 | 快速跌至 EMA52 | DIF 快速归零 |

### 5.2 分类输入

| 输入 | 用途 |
|------|------|
| K 线相对 EMA24 的位置 | 区分超强势 vs 其他 |
| K 线 close 序列的方向性 | 区分上行 vs 下行 |
| K 线 close 的方差 | 区分横盘 vs 趋势 |
| 调整速度（K 线根数） | 区分快速 vs 慢速 |

### 5.3 分类规则草案

```
if 价格快速下跌到 EMA52 (< 5 根):
    -> 弱势调整
elif 价格保持在 EMA24 之上 + DIF 趋向归零:
    -> 超强势调整
elif 价格横盘 + DIF 趋向归零:
    -> 强势调整
else:
    -> 不确定（不输出标签）
```

### 5.4 对背离类型的修饰

K 线结构与易出现的背离类型相关（详见 [`09-divergence-detection.md`](./09-divergence-detection.md)）：

| 结构 | 易出现的背离类型 |
|------|--------------|
| 强势调整 | 标准背离 |
| 超强势调整 | 跳空非背离（破前高）、线段间背离 |
| 弱势调整 | 动能不足（不破前高） |

K 线结构作为**预置信度修饰因子**：识别到对应结构会**抬升**该结构上常见的背离类型的置信度。

## 6. 跨级别的矢量单元包含

不同时间级别的矢量单元**独立**。但概念上存在包含关系：

| 大级别单元 | 内含小级别 |
|---------|-----------|
| 1 个大级别 heap | 多个小级别 cycles |
| 1 个大级别 cycle | 多个小级别 segments |
| 1 个大级别 segment | 多个小级别完整 segments |

这种包含关系是 Layer D（[`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md)）的"底部变盘四阶段"和"嵌套链"的物理基础。

## 7. 输出接口

每个 level 的状态机模块输出当前状态摘要：

```yaml
UnitSnapshot:
  level_id: str
  timestamp: timestamp

  heap:
    heap_id: str
    state: HeapState
    peak_value: float
    current_value: float
    bars_in_heap: int
    is_continuous_gap: bool

  cycle:
    cycle_id: str
    state: CycleState
    peak_dif: float
    current_dif: float
    heaps_in_cycle: int
    reference_heap_id: str

  segment:
    segment_id: str
    state: SegmentState
    direction: up | down
    cycles_in_segment: int
    segment_peak_dif: float
    reference_cycle_id: str

  k_structure:
    type: strong | ultra_strong | weak | none
```

## 8. 数学/逻辑不变量

实现可作为测试：

1. 同级别任一时刻最多一个 live heap、一个 live cycle、一个 live segment
2. heap.parent_cycle_id 必须指向一个 active cycle
3. cycle.parent_segment_id 必须指向一个 active segment
4. segment_peak_dif ≥ 所有 cycles 的 peak_dif（取 max）
5. cycle 的 1 号参考点不可"跨越当前周期"
6. 线段切换时必须严格原子（旧线段 completed 与新线段 active 不可同时为 live）
7. 周期内的 heap 数 ≥ 1
8. 线段内的 cycle 数 ≥ 1

## 9. 实现陷阱

详见 [`13-edge-cases.md`](./13-edge-cases.md)。这里列几条关键：

| 陷阱 | 解决 |
|------|------|
| 用严格符号变化切堆 | 容忍中间归零 $g_{max}$ 根 |
| 1 号参考点未及时失效 | 每个新堆形成时都检查 |
| 跨线段做了背离比较 | 比较前检查 segment_id 一致 |
| 线段切换的非原子 | 设计原子状态转移 |
| K 线结构分类的频繁抖动 | 添加滞后/平滑 |
