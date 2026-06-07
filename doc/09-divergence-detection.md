# 09 — 背离判定的统一框架

> 系统的另一条主线。**三类背离共用同一比较器结构**：容器 + 幅度量 + 1 号参考点 + 同线段约束。

---

## 1. 统一比较器结构 ★

不要为每类背离写独立检测器。三类背离的本质是**同一模式**：

```
对每个容器（heap / cycle / segment）：
  - 维护参考点（1 号）：容器内首个或最高的代表
  - 当新候选出现：
      检查：与参考点是否属于同一线段（硬约束）
      检查：参考点是否需要重置（新候选幅度 > 参考点）
      若不重置：比较 价格端 + 幅度端 → 输出背离/动能不足/无
```

**参数化变量**：

| 参数 | 周期内 | 周期间 | 线段间 |
|------|------|------|------|
| 容器 | 量能堆（heap） | 单位调整周期（cycle） | 线段（segment） |
| 幅度量 | 柱高（hist amplitude） | 白线 DIF 离零的最远距离 | 线段内最高周期的 DIF |
| 价格端 | K 线影线极值 | K 线影线极值 | K 线影线极值 |
| 同线段检查 | ✓ | ✓ | 升级后相邻线段 |
| 解决需求 | 归零轴（短线） | 线段调整（中线） | 趋势终结（长线） |

→ 一个通用比较器函数 + 三组参数 = 整套背离检测。

## 2. 三类背离

### 2.1 周期内背离（Intra-Cycle）

**容器**：同一 cycle 内的多个 heap。

**比较**：当前 heap 的 peak_hist 与 cycle 的 reference_heap.peak_hist。

**类型**：
- **连续跳空背离**：heaps 之间没有反向柱分割（heap.is_continuous_gap = true）
- **分立跳空背离**：heaps 之间有反向柱分割
- **隐形跳空**：当前 heap 的 peak_hist ≈ 0（即"幅度=0"的特例，最强信号）

**解决需求**：归零轴（短线信号）

### 2.2 周期间背离（Inter-Cycle）

**容器**：同一 segment 内的多个 cycle。

**比较**：当前 cycle 的 peak_dif 与 segment 的 reference_cycle.peak_dif。

**类型**：
- **标准背离**：价格端**破前极值** + 幅度端衰减
- **动能不足**：价格端**未破**前极值 + 幅度端衰减

两者算法相同，只是价格端判定不同。

**解决需求**：线段调整（中线信号）。**但是否变盘还需看长级别**——见 08 的"穿零轴 vs 升级"分支。

### 2.3 线段间背离（Inter-Segment）

**容器**：相邻两个 segment（必须经过时间级别升级）。

**比较**：当前 segment 的 segment_peak_dif 与上一 segment 的 segment_peak_dif。

**类型**：
- **线段背离**：当前线段最高周期 DIF < 上一线段最高周期 DIF

**解决需求**：趋势终结（长线信号）。**必穿零轴**——是宋理论里最强反转信号。

## 3. 1 号参考点的动态机制

这是最容易写错的环节。1 号参考点是**可变状态**。

### 3.1 周期内（cycle.reference_heap）

```
周期启动时：第一个 heap 形成 → reference_heap = heap_1
新 heap 形成时：
  若 heap_new.peak_hist > reference_heap.peak_hist:
      重置 reference_heap = heap_new
      （这就是"跳空非背离"——参考点失效）
  否则：
      heap_new 成为背离候选，与 reference_heap 比较
```

### 3.2 周期间（segment.reference_cycle）

```
线段启动时：第一个 cycle 形成 → reference_cycle = cycle_1
新 cycle 形成时（cycle 完成归零轴）：
  若 cycle_new.peak_dif > reference_cycle.peak_dif:
      重置 reference_cycle = cycle_new
  否则：
      cycle_new 成为周期间背离候选
```

### 3.3 跨线段不行

**线段间背离**不需要 reference 的概念——直接比较两个 completed segment 的 segment_peak_dif。

## 4. 比较逻辑

### 4.1 价格端判定

价格端取 **K 线影线极值**：

| 比较方向 | 取值 |
|---------|------|
| 顶（上涨线段） | high 影线最高点 |
| 底（下跌线段） | low 影线最低点 |

### 4.2 幅度端判定

- 周期内：`heap.peak_hist`（绝对值）
- 周期间：`cycle.peak_dif`（绝对值）
- 线段间：`segment.segment_peak_dif`（绝对值）

### 4.3 背离 vs 动能不足 vs 无

```
若 价格端 创新极值（破前高/低）:
    若 幅度端 衰减:
        → 标准背离
    若 幅度端 增长:
        → 跳空非背离 / 普通延续（参考点重置）
    若 幅度端 ≈ 0:
        → 隐形背离（最强）

若 价格端 未创新极值（未破前高/低）:
    若 幅度端 衰减:
        → 动能不足
    若 幅度端 增长:
        → 异常情况（数据问题或形态特殊）
    若 幅度端 ≈ 0:
        → 隐形动能不足
```

## 5. 跨线段不可比较 — 硬约束

宋反复强调"鸡找鸡、鸭找鸭"。算法上：

```
比较 candidate(t1) vs reference(t0) 之前：
    require segment_id(t0) == segment_id(t1)
```

违反则跳过比较——不输出任何背离信号。

### 5.1 线段切换的影响

线段切换（穿零轴或升级）时：
- 旧线段所有 cycle/heap 归档
- 新线段重置所有 reference
- 跨线段比较**通道关闭**（除非进入"线段间比较"模式）

## 6. K 线走势结构对背离的影响

详见 [`06-vector-units.md`](./06-vector-units.md) 的 K 线结构分类。

| K 线结构 | 易出现的背离 | 算法权重调整 |
|---------|----------|----------|
| 强势调整 | 标准背离 | 标准背离的置信度 +0.1 |
| 超强势调整 | 跳空非背离 + 线段间背离 | 周期间背离更可能是"假"——置信度 -0.1 |
| 弱势调整 | 动能不足 | 动能不足置信度 +0.15 |

K 线结构作为**预置信度修饰因子**。

## 7. 隐形背离的特殊处理

隐形 = 幅度端 ≈ 0。

**特殊性**：
- 实时识别困难（见 wiki / 05）
- 一旦确认置信度极高
- 算法上需要独立通道，不要埋在普通背离里

### 7.1 隐形子类型

| 子类型 | 位置 | 含义 |
|--------|------|------|
| 高位隐形 | DIF 距零远 | "必回拉零轴"（下一波归零轴） |
| 归零轴隐形 | DIF 距零近 | "必穿零轴"（变盘） |

### 7.2 隐形 + 高位空 + 分型 = "送钱形态"

宋的最强反转组合：

```
单位调整周期之内
+ 分立跳空背离
+ 黄白线高位空
+ 分立跳空隐形
+ 顶/底分型
─────────────
四档置信度同向共振，标记为"送钱形态"
（在输出 schema 中作为独立标签）
```

实现上：检测到这五个条件同时满足，触发 `goldmine_form` 事件，置信度从各子条件合成（建议至少 0.85）。

## 8. 多周期信息融合对背离判定 ★

单级别背离噪声大，多级别协同的强背离才是核心信号。

### 8.1 协同提升

| 当前级别背离 | 协同条件 | 置信度变化 |
|------------|---------|---------|
| 1h 周期间顶背离 | 4h 高位空 + 30m 周期内背离 | × 1.5 |
| 5m 隐形顶背离 | 15m 周期间背离 | × 1.3 |
| D 周期间底背离 | W 在零轴上方多方 | × 0.7（多空相抵） |

### 8.2 合成公式

参考 [`10-confidence-model.md`](./10-confidence-model.md)。基本形式：

$$
\text{conf}^{\text{final}}_{\text{divergence}} = \text{conf}^{\text{local}} \cdot f_{\text{协同}} \cdot f_{\text{结构}}
$$

## 9. 决策流程

```
新 K 线收盘
    ↓
更新 heap / cycle / segment 状态
    ↓
对每个新候选（新形成的 heap / cycle / segment）：
    检查 segment_id 一致性
    若 candidate.amplitude > reference.amplitude:
        重置 reference
        输出"参考点已重置"事件
    若 candidate.amplitude ≤ reference.amplitude:
        判定价格端
        判定幅度端
        合成背离类型（背离 / 动能不足 / 隐形）
        计算单级别置信度
    ↓
多级别融合：
    应用 top-down + bottom-up + K 结构修饰
    ↓
输出 DivergenceSignal
```

## 10. 输出接口

```yaml
DivergenceSignal:
  level_id: str
  signal_type:
    - intra_cycle_continuous_gap     # 周期内连续跳空背离
    - intra_cycle_discrete_gap        # 周期内分立跳空背离
    - intra_cycle_hidden              # 周期内隐形跳空
    - inter_cycle_standard            # 周期间标准背离
    - inter_cycle_weakness            # 周期间动能不足
    - inter_cycle_hidden              # 周期间隐形背离
    - inter_segment                   # 线段间背离
    - goldmine_form                   # 送钱形态（五重共振）

  direction: top | bottom              # 顶背离 or 底背离

  confidence_local: float              # 单级别置信度
  confidence_final: float              # 多周期融合后置信度

  container:
    type: heap | cycle | segment
    container_id: str
    reference_id: str
    candidate_id: str

  price_side:
    reference_value: float
    candidate_value: float
    is_new_extreme: bool

  amplitude_side:
    reference_value: float
    candidate_value: float
    decay_ratio: float

  multi_level_support:
    sub_level_aligned: bool
    super_level_supportive: bool
    k_structure_supportive: bool

  resolves_need: "near_zero_axis" | "segment_adjustment" | "trend_termination"
```

## 11. 单元测试建议

| 测试 | 验证 |
|------|------|
| 同周期内 heap_new.peak > heap_ref.peak → 重置 reference | 1 号参考点重置 |
| 同周期内 heap_new.peak < heap_ref.peak + 价格新高 → 周期内分立背离 | 周期内判定 |
| 同线段内 cycle_new.peak_dif < cycle_ref.peak_dif + 价格新高 → 周期间标准背离 | 周期间判定 |
| 同线段内 cycle_new.peak_dif < cycle_ref.peak_dif + 价格未破 → 周期间动能不足 | 动能不足 |
| heap_new.peak ≈ 0 + 价格新高 → 周期内隐形跳空（confidence 高） | 隐形识别 |
| 跨 segment_id 比较 → 跳过不输出 | 跨线段约束 |
| 五条件齐 → goldmine_form 触发 | 送钱形态 |
| 多周期协同 → confidence_final > confidence_local | 多周期增强 |

## 12. 算法陷阱

| 陷阱 | 解决 |
|------|------|
| 1 号参考点未及时失效 | 每个新 heap/cycle 形成时检查 |
| 跨线段做了背离比较 | 显式 segment_id 检查 |
| 隐形未单独通道 | "幅度 ≈ 0" 单独判定 |
| 动能不足与背离判定耦合 | 一个比较器输出两种标签 |
| K 线结构未参与背离权重 | 前置 K 结构修饰 |
| 多周期合成简单平均 | 用乘性融合 |
| 实时背离与已确认背离混用 | 区分 candidate 与 confirmed |
