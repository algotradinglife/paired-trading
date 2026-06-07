# 07 — 穿零轴的严格判定

> 穿零轴 = 线段终结 = 系统最严格的事件判定。三重约束 + 多周期协同。

---

## 1. 严格判定的三重约束

宋给出穿零轴需同时满足：

| 条件 | 表述 |
|------|------|
| ① **黄线（DEA）击穿零轴** | $\text{DEA}_t$ 与 $\text{DEA}_{t-1}$ 异号 |
| ② **K 线击穿 EMA52** | $\text{close}_t$ 与 $\text{close}_{t-1}$ 相对 EMA52 异侧 |
| ③ **次根 K 线确认** | $t+1$ 根 close 仍保持在 $t$ 的新一侧 |

三条件 **"且"** 关系：任一不满足都不算穿越确认。

→ 穿零轴事件**始终延迟一根 K 线**才能确认。

## 2. 三阶段判定（连续置信度）

把穿零轴拆成三个阶段，对应不同置信度档位：

| 阶段 | 触发 | 置信度建议 |
|------|------|----------|
| **稳态** | DEA 远离零轴 | ~0 |
| **预警** | DEA 接近零 + 次级别同向先动 | 0.30~0.50 |
| **候选** | 本根满足 ① + ② | 0.65~0.80 |
| **确认** | 次根 close 确认 | 0.90~1.0 |
| **失败** | 次根 close 回到原侧 | 0~0.10 |

下游消费者按自己策略选择阈值进场。

## 3. "有效击穿"的代码语义

### 3.1 DEA 击穿（条件 ①）

判定式：

$$
\mathrm{sign}(\text{DEA}_t) \neq \mathrm{sign}(\text{DEA}_{t-1}) \quad \text{且} \quad |\text{DEA}_t| > \epsilon
$$

$\epsilon$ 是数值噪声阈值（极小），用于过滤数值精度问题。

### 3.2 K 线击穿 EMA52（条件 ②）

判定式：

$$
\mathrm{sign}(\text{close}_t - \text{EMA52}_t) \neq \mathrm{sign}(\text{close}_{t-1} - \text{EMA52}_{t-1})
$$

**重要**：用 **close** 判定，不用 high/low。影线刺穿不算。

### 3.3 次根确认（条件 ③）

判定式：

$$
\mathrm{sign}(\text{close}_{t+1} - \text{EMA52}_{t+1}) = \mathrm{sign}(\text{close}_t - \text{EMA52}_t)
$$

即：次根的 close 与本根 close **同侧**（相对 EMA52）。

**注意**：EMA52 在 t+1 时刻已经更新，要用 t+1 时刻的 EMA52 比较。

## 4. 候选事件的生命周期

```
DEA 接近零轴
    ↓
预警事件生成 (confidence ~0.4)
    ↓
本根满足 ① + ②
    ↓
候选事件生成 (confidence ~0.7)
    ↓ 等待 t+1 K 线收盘
    ↓
分支：
    ├─ 次根确认 → 确认事件 (confidence ~0.95)
    │            ↓
    │           触发线段切换（见 06）
    │
    ├─ 次根回拉 → 候选失效 (confidence 归零)
    │            ↓
    │           线段不切换，标记为"假穿"
```

## 5. DIF 穿零 vs DEA 穿零的关系

**重要区分**：

| 概念 | 形态 |
|------|------|
| DIF 穿零 | 价格短期中枢瞬时穿越——常见、易被噪声触发 |
| DEA 穿零 | DIF 的 EMA9 穿零——结构性穿越 |
| 归零轴 | DIF 接近零但 DEA 未穿——线段未变 |

**算法上**：DIF 穿零**不触发**线段切换；只有 DEA 穿零（满足三重约束）才触发。

DIF 穿零可作为**预警信号**：往往 DIF 先穿，几根 K 线后 DEA 跟进。

## 6. 多周期协同的预判

单级别穿零轴是滞后事件，但多周期视角可以**预判**：

### 6.1 协同提升置信度

| 多周期情形 | 对当前级别穿零置信度的影响 |
|----------|---------------------|
| 次级别同向穿零先发生 | +（领先信号） |
| 长级别处于同向状态 | +（环境支持） |
| 当前级别周期间背离 + 长级别高位空 | ++（强预判） |
| 长级别处于反向加速期 | -（环境抵触） |

### 6.2 多周期合成的置信度公式

参考形式（具体权重待回测）：

$$
\text{conf}_{\text{zero\_cross}}^{\text{final}} = \alpha \cdot \text{conf}_{\text{local}} + \beta \cdot \text{conf}_{\text{sub\_level}} + \gamma \cdot \text{conf}_{\text{super\_level}}
$$

其中：
- $\text{conf}_{\text{local}}$：当前级别按三重约束算出的本级别置信度
- $\text{conf}_{\text{sub\_level}}$：次级别同向状态的贡献
- $\text{conf}_{\text{super\_level}}$：长级别状态的贡献（可能为负）

$\alpha + \beta + \gamma = 1$，默认建议 $\alpha = 0.5, \beta = 0.3, \gamma = 0.2$。

详细融合机制见 [`10-confidence-model.md`](./10-confidence-model.md)。

## 7. 穿零轴 vs 时间级别升级 — 互斥归宿

当前级别出现"周期间背离 + DEA 接近零"时，**两种归宿之一**：

| 归宿 | 触发条件 |
|------|---------|
| **穿零轴变盘** | 长级别处于高位空（有回拉零轴需求） |
| **时间级别升级** | 长级别仍在调整低位（无回拉需求） + 长级别 K 线在 EMA24 之上 |

**算法上**：判断"穿零轴候选"时必须**同时**检查长级别状态：
- 长级别支持 → 升级穿零轴置信度
- 长级别反对 → 降级穿零轴置信度，转而升级"级别升级嫌疑"

时间级别升级的判定见 [`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md)。

## 8. 触发的下游动作

穿零轴**确认**事件触发：

1. **当前线段封档**（见 06）
2. **新线段启动**（direction 翻转）
3. **新线段的 1 号参考点重置**（等待第一个量能堆形成）
4. **形态置信度重置**（高位空等形态的累积根数从 0 开始）
5. **跨级别状态更新**（长级别可能因此进入"线段切换的次级别已确认"状态）
6. **输出 EventConfirmed**（带可追溯性）

## 9. 失败回穿的处理

候选事件失效（次根回拉）时：

1. 候选事件标记为 `invalidated`
2. 线段不切换，仍是原线段
3. K 线击穿 EMA52 但被否定 → 标记为"无效击穿"（参考 wiki）
4. 输出 `EventInvalidated` 事件（让下游消费者知道）
5. 几根后如果 close 重新满足条件 → 可以重新进入候选

## 10. 时间戳与对齐

穿零轴事件的时间戳标记：

| 字段 | 含义 |
|------|------|
| `crossing_bar_ts` | 满足 ① ② 的那根 K 线时间戳 |
| `confirmation_bar_ts` | 次根 K 线时间戳 |
| `system_ts` | 系统输出时间戳 |

下游消费者用 `confirmation_bar_ts` 作为变盘"实际确认时间"。

## 11. 多级别同时穿零轴

罕见但重要的情形：**对齐时刻**多个级别同时确认穿零轴。

例：4h 与 1h 在同一时刻都满足穿零轴 + 次根确认。

**处理**：
- 大级别穿零**权重更高**——其线段切换的影响范围更大
- 小级别穿零作为大级别穿零的"协同信号"，提升大级别置信度
- 输出时**同时输出两个穿零事件**，但合成结论以大级别为主

## 12. 输出接口

```yaml
ZeroCrossingEvent:
  level_id: str
  stage: warning | candidate | confirmed | invalidated
  confidence: float
  crossing_bar_ts: timestamp
  confirmation_bar_ts: timestamp | null

  details:
    dea_crossing_value: float       # 穿越时的 DEA 值
    close_vs_ema52: float            # close - EMA52 的差
    sub_level_aligned: bool           # 次级别是否协同
    super_level_supportive: bool      # 长级别是否支持
    next_bar_confirmed: bool          # 次根确认与否

  resulting_action:                   # 触发的下游动作
    segment_closed: segment_id        # 关闭的线段
    segment_opened: segment_id        # 启动的新线段
    direction_flipped: up_to_down | down_to_up
```

## 13. 单元测试建议

| 测试 | 验证 |
|------|------|
| 影线刺穿但 close 在原侧 → 不触发候选 | close 判定 |
| 满足 ① ② 但次根回拉 → 候选失效 | 次根确认 |
| DIF 穿但 DEA 没穿 → 不触发候选 | DEA 才算 |
| DEA 穿但 K 线未击穿 EMA52 → 不触发候选 | 双通道 |
| 多次重复穿越（震荡市场）→ 多次候选+失效 | 状态机健壮性 |
| 长级别高位空 + 当前级别背离 → 预警置信度高 | 多周期协同 |
