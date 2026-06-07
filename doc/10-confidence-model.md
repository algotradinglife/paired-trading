# 10 — 置信度模型

> 系统所有事件以**连续置信度** $\in [0, 1]$ 表达。本文档定义置信度的来源、合成规则、阶段划分。

---

## 1. 核心原则

### 1.1 后验性

所有 MACD 动能理论的"事件"——归零轴、背离、变盘——**实时不可知**。事前只能给概率推断。

→ 算法**不输出布尔事件**，只输出连续置信度。下游消费者按自己阈值决策。

### 1.2 置信度作为标准接口

整个系统的输出语言只有一种数值：**置信度** $\in [0, 1]$。不混用"嫌疑度""可能性""概率"等同义词。

### 1.3 多通道融合

最终置信度不是单一指标，而是**多个独立观测通道的融合**：
- 单级别先验
- 多周期协同（top-down + bottom-up）
- K 线结构修饰
- 持续度加权

## 2. 置信度档位（决策友好）

虽然置信度是连续的，但下游消费时常用档位思维。建议默认档位划分：

| 档位 | 范围 | 语义 | 典型动作（仅供下游参考） |
|------|------|------|---------------------|
| `dormant` | [0, 0.30) | 无活跃信号 | 监控 |
| `watching` | [0.30, 0.50) | 预警，单一指标进入预警区 | 准备、不动 |
| `forming` | [0.50, 0.65) | 形态在构建中 | 关注 |
| `candidate` | [0.65, 0.80) | 形态嫌疑成立、多指标合流 | 视下游策略决定 |
| `confirmed` | [0.80, 0.95) | 形态确立、多重确认 | 高置信度 |
| `post_hoc` | [0.95, 1.0] | 已经发生、后验确认 | 已经过点，常已晚 |

这是**建议档位**，不是硬性规则。下游可以自定义阈值。

## 3. 置信度的三个来源

每个事件的最终置信度由三部分合成：

```
conf_final = conf_local × f_multi_level × f_modifier
```

### 3.1 conf_local — 单级别先验

由 [`05-form-detection.md`](./05-form-detection.md) 的形态识别 + [`09-divergence-detection.md`](./09-divergence-detection.md) 的背离判定计算。

来源于 5 个基础观测流的特定组合。

### 3.2 f_multi_level — 多周期协同因子

来自 Layer D（[`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md)）。

包含 top-down 与 bottom-up 两个分量：

$$
f_{\text{multi\_level}} = f_{\text{bottom\_up}} \cdot f_{\text{top\_down}}
$$

### 3.3 f_modifier — K 线结构修饰

来自 K 线走势结构分类（[`06-vector-units.md`](./06-vector-units.md) 第 5 节）。

| 形态 | 结构匹配 | 修饰因子 |
|------|--------|--------|
| 周期间标准背离 | 强势调整 | × 1.1 |
| 周期间标准背离 | 超强势调整 | × 0.9（更可能是非背离） |
| 周期间动能不足 | 弱势调整 | × 1.15 |
| 周期内隐形 | 任意 | × 1.0（结构对隐形影响小） |

具体值默认值见 [`12-thresholds-and-params.md`](./12-thresholds-and-params.md)。

## 4. 多周期协同因子的详细形式

### 4.1 Bottom-up 传播

小级别的形态对当前级别提供**领先支持**：

$$
f_{\text{bottom\_up}}(L) = 1 + w_{\text{sub}} \cdot \text{conf}_{\text{sub}}(L) \cdot \mathbb{1}[\text{方向一致}]
$$

其中：
- $\text{sub}(L)$ = $L$ 的次级别
- $\text{conf}_{\text{sub}}$ = 次级别同形态的置信度
- $w_{\text{sub}}$ = 默认 0.4

→ 次级别同向支持时，当前级别置信度最多放大 1.4 倍（当 $\text{conf}_{\text{sub}} = 1$）。

### 4.2 Top-down 约束

长级别的状态提供**环境约束**：

$$
f_{\text{top\_down}}(L) = \begin{cases}
1 + w_{\text{up}}^+ & \text{长级别同向支持} \\
1 - w_{\text{up}}^- & \text{长级别反向抵触} \\
1 & \text{长级别中性}
\end{cases}
$$

默认：$w_{\text{up}}^+ = 0.3, w_{\text{up}}^- = 0.4$

**长级别"同向支持"的定义**：

| 当前级别信号 | 长级别同向 | 长级别反向 |
|------------|--------|--------|
| 顶背离嫌疑 | 长级别高位空 / 顶背离 / 已穿零 | 长级别强势多方加速 |
| 底背离嫌疑 | 长级别低位空 / 底背离 / 已穿零 | 长级别强势空方加速 |
| 归零轴接近 | 长级别接近 EMA52 | 长级别强势单边 |

### 4.3 合成示例

```
情景：1h 出现周期间顶背离
  conf_local = 0.65
  4h 处于高位空状态（长级别同向）→ f_top_down = 1.3
  30m 出现周期内分立顶背离（次级别同向，conf 0.7）→ f_bottom_up = 1 + 0.4 × 0.7 = 1.28
  K 线结构 = 强势调整 → f_modifier = 1.1

  conf_final = 0.65 × 1.3 × 1.28 × 1.1 ≈ 1.19 → 截断至 1.0
```

clamp 到 $[0, 1]$ 区间。

## 5. 置信度的时间动态

### 5.1 动态升降

置信度**随时间动态变化**：

- K 线收盘 → 持续度 +1 → 置信度可能升级
- live tick 更新 → 置信度小幅波动（漂移期）
- 反向证据出现 → 置信度回落

### 5.2 阶段转换

档位间的转换由置信度跨阈值触发：

```
dormant ─→ watching：conf 跨过 0.30
watching ─→ forming：conf 跨过 0.50
forming ─→ candidate：conf 跨过 0.65
candidate ─→ confirmed：conf 跨过 0.80
confirmed ─→ post_hoc：严格事件确认（如次根 K 线确认穿零轴）

任一阶段 ─→ dormant：置信度跌破 0.10 + 持续根数清零
```

### 5.3 反向证据的处理

若出现反向证据（如形态被否定）：
- 置信度立即衰减（不平滑）
- 形态相关持续度清零
- 标记 `invalidation_reason`

## 6. 不同事件类型的合成差异

不同事件的合成略有差异。下表是默认建议：

| 事件 | 合成公式 |
|------|--------|
| 形态识别（高位空、隐形、黏合、倒挂） | conf_local × f_multi_level × f_modifier |
| 周期内背离 | conf_local × f_multi_level × 1.0 |
| 周期间背离 | conf_local × f_multi_level × f_modifier(k_structure) |
| 线段间背离 | conf_local × 1.5（线段间本身权重就高） |
| 穿零轴 | conf_local × f_top_down（次级别贡献已内化在 conf_local 里） |
| 时间级别升级 | 四条件**乘性**合成（任一为 0 即触发不成立） |
| 底部变盘第 i 阶段 | 各子信号的**加权和**（详见 08） |
| 级联失效 | 触发即跳到 0.7+，不需要平滑过渡 |

## 7. 多事件并发时的优先级

某时刻可能多个事件同时活跃。优先级建议：

```
线段间背离  >  时间级别升级  >  穿零轴确认  >  底部变盘第 ③④ 阶段
  >  周期间背离  >  送钱形态  >  周期内背离  >  形态嫌疑
```

输出层（11）按这个优先级排列事件清单。

## 8. 与下游决策的接口

本系统**不做决策**——只输出置信度。下游消费者根据：

- 自己的风险偏好选择阈值
- 自己的策略选择动作
- 自己的特征工程（品种、时段、波动率等，**out of scope**）进一步加工

## 9. 一致性约束

实现时应当保证：

1. $\text{conf} \in [0, 1]$ 始终成立（clamp 边界）
2. 反向证据出现时 conf 单调不增
3. 同向证据累加时 conf 单调不减
4. conf 跨档位是离散事件（应触发 EventStageChanged）
5. K 线收盘时所有 conf 重新计算并锁定 completed 值
6. live tick 只更新 conf 不锁定（避免假阶段切换）

## 10. 输出接口（每个事件携带）

```yaml
ConfidenceDetail:
  conf_final: float                # ∈ [0, 1]
  stage: dormant | watching | forming | candidate | confirmed | post_hoc

  components:
    conf_local: float
    f_multi_level: float
    f_modifier: float

  contributions:                    # 各 contributor 的贡献度
    feature_flows: Dict[stream_id, contribution]
    sub_levels: List[(level_id, contribution)]
    super_levels: List[(level_id, contribution)]
    k_structure: contribution

  trajectory:                       # 最近 N 根 K 线的 conf 变化
    history: List[(ts, conf)]

  invalidation_reason: str | null   # 若被否定，原因
```

## 11. 单元测试建议

| 测试 | 验证 |
|------|------|
| 全部输入归 0 → conf_final = 0 | 边界 |
| 全部输入归 1 → conf_final ≤ 1.0（clamp） | clamp |
| 单级别 0.6 + 长级别支持 → conf_final > 0.6 | top-down + |
| 单级别 0.6 + 长级别反对 → conf_final < 0.6 | top-down − |
| 反向证据出现 → conf 立即降到下一档以下 | 反向处理 |
| 同档位维持时间累加 → 持续度对 conf 有贡献 | 时间动态 |
| 跨档位跳变 → 输出 StageChanged 事件 | 阶段事件 |

## 12. 调优指南

权重 $w_{\text{sub}}, w_{\text{up}}^\pm$ 等需要回测调优。建议步骤：

1. 用历史数据回放，观察各事件的实际触发频率
2. 比较高置信度事件的"事后正确率"
3. 调整权重以平衡精确率 / 召回率
4. 不同时间级别可能需要不同权重（小级别噪声大，权重收紧）
5. 不同品种可能需要不同权重（高波动品种权重收紧）

注：这些**回测调优**属于本系统的范围内（参数化设计），但**用什么策略消费置信度**属于下游项目。
