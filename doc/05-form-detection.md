# 05 — 形态识别

> 基于 Layer B 的 5 个观测流，识别宋理论中的 6 种基础形态。**所有形态输出连续置信度**，不输出布尔状态。

---

## 1. 形态总览

| 形态 | 含义 | 关键特征 |
|------|------|---------|
| 高位 | 黄白线远离零轴 | DIF 距零远 |
| 高位空 | 高位 + 柱体衰减 | DIF 远 + Hist 衰减 + 同向 |
| 隐形 | 柱高 ≈ 0 但价格在推进 | Hist ≈ 0 + 持续 + 价格动 |
| 零轴黏合 | 黄白线近零轴 + 柱同向 | DIF 近 + Hist 同向 + 持续 |
| 零轴倒挂 | 黄白线近零轴 + 柱异向 | DIF 近 + Hist 异向 |
| 归零轴接近 | 双通道接近归零 | DIF 近 OR 价格 ≈ EMA52 |

每个形态的置信度 $\in [0, 1]$。

## 2. 形态判定规则

每个形态由一组**输入特征 + 加权规则**生成置信度。下面给出规则草案（具体权重待回测调优，见 [`12-thresholds-and-params.md`](./12-thresholds-and-params.md)）。

### 2.1 高位（high_position）

最简单的形态——纯距离判定。

**输入**：
- `dif_proximity_zero` (流 1)

**规则**：

$$
\text{conf}_{\text{high\_position}} = 1 - \text{dif\_proximity\_zero}
$$

→ DIF 越远离零轴，"高位"置信度越高。

**注**：高位通常不作为独立决策依据，而是作为其他形态（高位空）的前置条件。

### 2.2 高位空（high_position_void）

最重要的反转预警形态。

**输入**：
- `dif_proximity_zero` (流 1)
- `hist_amplitude_ratio` (流 2)
- `hist_dif_sign_alignment` (流 3)
- `state_persistence.high_position_void` (流 4)

**判定条件**：
- DIF 远离零轴：$\text{dif\_proximity\_zero} < \theta_1$（流 1 低值）
- Hist 持续衰减：$\text{hist\_amplitude\_ratio}_t$ 已从峰值显著下降
- Hist 与 DIF 同向：流 3 = +1
- 持续根数足够：流 4 ≥ $n_1$

**合成（参考）**：

$$
\text{conf}_{\text{HPV}} = w_1 \cdot (1 - \text{流1}) + w_2 \cdot (1 - \text{流2/peak}) + w_3 \cdot \mathbb{1}[\text{流3}=+1] + w_4 \cdot \min(\text{流4}/n_1, 1)
$$

权重默认值：$w_1 = w_2 = 0.35, w_3 = 0.2, w_4 = 0.1$，可调。

### 2.3 隐形（hidden）

最强反转信号、最难实时识别。

**输入**：
- `hist_amplitude_ratio` (流 2)
- `state_persistence.hidden` (流 4)
- `price_momentum` (流 5)

**判定条件**：
- Hist 当前高度 ≈ 0：$\text{hist\_amplitude\_ratio} < \theta_2$
- 持续 ≥ $n_2$ 根
- 价格仍在推进：$|\text{price\_momentum}| > \theta_3$

**合成（参考）**：

$$
\text{conf}_{\text{hidden}} = w_1 \cdot (1 - \min(\text{流2}/\theta_2, 1)) + w_2 \cdot \min(\text{流4}/n_2, 1) + w_3 \cdot \min(|\text{流5}|/\theta_3, 1)
$$

**特殊处理**：隐形需要根据**所在位置**进一步分类：
- 高位隐形 = 隐形 + `dif_proximity_zero` 低（远离零轴）→ "必回拉零轴"
- 归零轴隐形 = 隐形 + `dif_proximity_zero` 高（接近零轴）→ "必穿零轴"

两种细分子标签由更高层（08）合成。

### 2.4 零轴黏合（zero_stick）

**输入**：
- `dif_proximity_zero` (流 1)
- `hist_amplitude_ratio` (流 2)
- `hist_dif_sign_alignment` (流 3)
- `state_persistence.zero_stick` (流 4)

**判定条件**：
- DIF 接近零：流 1 高值（接近 1）
- Hist 小：流 2 低值
- Hist 与 DIF 同向：流 3 = +1
- 持续根数足够：流 4 ≥ $n_4$

**合成**：

$$
\text{conf}_{\text{zero\_stick}} = w_1 \cdot \text{流1} + w_2 \cdot (1 - \text{流2}) + w_3 \cdot \mathbb{1}[\text{流3}=+1] + w_4 \cdot \min(\text{流4}/n_4, 1)
$$

### 2.5 零轴倒挂（zero_inverted）

与零轴黏合的关键区别：**Hist 已反向**。

**输入**：
- `dif_proximity_zero` (流 1)
- `hist_dif_sign_alignment` (流 3)
- `state_persistence.zero_inverted` (流 4)

**判定条件**：
- DIF 接近零：流 1 高值
- Hist 与 DIF **异向**：流 3 = -1
- 持续根数 ≥ $n_5$

**合成**：

$$
\text{conf}_{\text{zero\_inverted}} = w_1 \cdot \text{流1} + w_2 \cdot \mathbb{1}[\text{流3}=-1] + w_3 \cdot \min(\text{流4}/n_5, 1)
$$

### 2.6 归零轴接近（near_zero_axis）

**两个通道的 OR**——只要任一通道满足就有效。

**输入**：
- `dif_proximity_zero` (流 1) — 能量端通道
- 价格端通道：$1 - \frac{|\text{close} - \text{EMA52}|}{\text{EMA52} \cdot \theta_6}$

**判定**：

$$
\text{conf}_{\text{near\_zero}} = \max(\text{流1}, \text{价格端通道})
$$

**完美形态**：两个通道同时为高值 = 双通道协同确认。

## 3. 黏合 ↔ 倒挂的状态机

这两个形态**形态相似、属性相反**，且会**单向演变**（黏合 → 倒挂）：

```
零轴黏合 conf 高
       ↓
       Hist 开始反向释放
       ↓
零轴黏合 conf 下降, 零轴倒挂 conf 上升
       ↓
零轴倒挂 conf 高
```

实现时这两个形态的置信度应当**互补**——同时只有一个为高。

## 4. 形态置信度的更新时机

| 触发 | 更新方式 |
|------|---------|
| live K 线 tick | 重新计算所有形态的 live 置信度 |
| K 线收盘 | 锁定 completed 置信度，作为历史记录 |

**注意**：流 4（持续根数）只在 K 线收盘时 +1，因此置信度的"持续度"部分只在收盘时更新。

## 5. 跨级别独立

每个时间级别独立计算自己的 6 个形态置信度。**这一层不做跨级别交互**。

跨级别的形态合成（如"协同高位空"）在 Layer D（[`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md)）。

## 6. 输出接口

`form_detector` 模块对每级别输出：

```yaml
FormSnapshot:
  level_id: str
  timestamp: timestamp

  high_position: float
  high_position_void: float
  hidden: float
  hidden_subtype: "high" | "near_zero" | "none"  # 隐形的位置分类
  zero_stick: float
  zero_inverted: float
  near_zero_axis: float
  near_zero_perfect: bool  # 双通道同时高

  # 元数据
  hist_decay_from_peak: float    # Hist 从峰值衰减比例
  zero_streak_count: int          # Hist 接近零持续根数
```

## 7. 物理直觉对照（理论参考）

形态的物理直觉来源于宋理论，整理在 wiki：

| 形态 | 物理直觉 |
|------|--------|
| 高位空 | 桥面失支撑——结构性即将垮 |
| 隐形 | 火箭无燃料——必然回落 |
| 零轴引力 | 橡皮筋拉远——回弹更快 |
| 零轴黏合 | 多空胶着，但有支撑 |
| 零轴倒挂 | 黏合的"失败版"，能量已经反向 |

详见 wiki: [`momentum-energy-bar.md`](../../../wiki/option-timing/macd-momentum/momentum-energy-bar.md)

## 8. 单元测试建议

| 测试 | 验证 |
|------|------|
| Hist 持续 10 根 = 0 + DIF 远 + 价格涨幅 > 阈值 → 高位隐形 conf > 0.7 | 隐形识别 |
| DIF 远 + Hist 衰减 3 根 + 同向 → HPV conf 渐升 | 高位空构建 |
| 黏合状态下 Hist 突然反号 → 黏合 conf 降、倒挂 conf 升 | 状态切换 |
| 双通道（DIF≈0 + close≈EMA52）→ near_zero conf = 1.0, perfect = true | 完美归零轴 |
| Hist 极大 + DIF 极远 → 高位 conf 高，其他形态 conf 低 | 形态正交性 |

## 9. 已知限制

### 9.1 隐形的实时识别难度

如 wiki 所述，隐形是最难实时识别的形态。本层只能输出**置信度的渐进上升过程**，不能给出 "$t_0$ 时刻是隐形"的判定——这是后验性的不可避免代价。

### 9.2 形态的近似边界

各形态在特征空间中**有重叠区域**——比如"DIF 远 + Hist 小"可能同时是"高位空成熟"也可能是"刚开始的隐形苗头"。本层不强求独占——多个形态可同时有较高置信度。最终的"主标签"在 Layer D 合成。

### 9.3 参数依赖

所有 $\theta_i, n_i, w_i$ 都是可调参数。本文档给出的是**结构和默认建议**，具体值需要回测调优。详见 [`12-thresholds-and-params.md`](./12-thresholds-and-params.md)。
