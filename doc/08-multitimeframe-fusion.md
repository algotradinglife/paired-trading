# 08 — 多周期信息融合机制

> 本系统的两条主线之一。把单级别的形态预置信度合成为最终判定，并处理跨级别的级联依赖、底部变盘、级别升级等复合事件。

---

## 1. 两种级别关系

宋的"嵌套关系"实际包含两个不同的结构。区分它们是这一层的第一件事。

### 1.1 直系第一代（Direct Children）

**当前级别直接包含的所有较小级别**——一个集合（无序）。

例：12h 的直系第一代 = {6h, 3h, 2h, 1h, 30m, 15m, 10m, 5m, 3m, 1m}

数据结构：`Set[level_id]`。

### 1.2 嵌套链（Nesting Chain）

**沿"每层取最大直系子级别"递归向下展开**的线性序列。

例：12h 的嵌套链 = [12h, 6h, 3h, 2h, 1h, 30m, 15m, 10m, 5m, 3m, 1m]

数据结构：`List[level_id]`（有序）。

### 1.3 用法对比

| 用途 | 用哪个 |
|------|------|
| 判断主级别**何时启动反弹** | 直系第一代集合 — "所有要走完底部" |
| 判断主级别**反弹何时见顶** | 嵌套链 — "沿最大子级别一直往下找到底" |

**记忆口诀**：进入靠**集合**（直系），退出靠**链**（嵌套）。

## 2. 双向置信度传播

跨级别的置信度有**两个方向**同时存在：

### 2.1 自下而上（领先信号 / bottom-up）

小级别先于大级别变化，是**领先指标**。

**示例**：
- 5m 出现底背离 → 提升 15m 同方向背离置信度
- 30m 完成下跌线段调整 → 提升 1h 底部变盘第④阶段置信度

**传播规则**：

$$
\text{conf}^{\text{up}}_{L} += w_{\text{up}} \cdot \text{conf}_{L'}, \quad L' = \text{次级别}(L)
$$

### 2.2 自上而下（环境约束 / top-down）

大级别状态约束小级别的有效性。**大级别是先验**。

**示例**：
- D 仍在强势多方 → 1h 的顶背离信号置信度打折
- 4h 高位空 → 1h 周期间顶背离置信度抬升

**传播规则**：

$$
\text{conf}^{\text{down}}_{L} \cdot= w_{\text{down}}(\text{state of } L^{+}), \quad L^{+} = \text{长级别}(L)
$$

其中 $w_{\text{down}} \in [0, 2]$，可以放大也可以收缩。

### 2.3 合成公式

最终置信度 = 单级别先验 × 协同因子 × 环境因子：

$$
\text{conf}_L^{\text{final}} = \text{conf}_L^{\text{prior}} \cdot f_{\text{bottom-up}}(L) \cdot f_{\text{top-down}}(L)
$$

详细函数形式见 [`10-confidence-model.md`](./10-confidence-model.md)。

## 3. 第一代级别"当值有效性"

宋第六章第六节的关键约束。

### 3.1 当值有效的两个条件

| 条件 | 表述 |
|------|------|
| ① 不击穿零轴 | 该级别如果击穿零轴，当值即失效 |
| ② 推升长级别到高位 | 该级别的反弹必须把长级别推到单位调整周期的高位（不可使长级别变成"零轴黏合 / 倒挂"） |

### 3.2 失效检测

| 失效类型 | 检测 |
|---------|------|
| **类型 A — 击穿零轴** | DEA 在该级别**反向穿越**零轴 |
| **类型 B — 推升乏力** | 长级别在该级别完成反弹后变成 `zero_stick` 或 `zero_inverted` 形态 |

### 3.3 级联失效

某级别失效 → 长级别失去当值能力 → **可能**触发主级别趋势终结：

```
小级别失效
    ↓
长级别变成 zero_stick / zero_inverted
    ↓
长级别失效（不能再当值）
    ↓
... 沿链上溯
    ↓
主级别趋势终结候选
```

**算法上**：维护 `validity[level]` 状态。一旦某级别变为 `inactive`，自动**触发对其长级别的状态再评估**。

### 3.4 输出

```yaml
CascadeFailureWarning:
  failed_level: str
  failure_type: zero_axis_breach | weak_push_up
  affected_levels: List[str]   # 受影响的长级别清单
  main_trend_termination_confidence: float  # 主级别趋势终结的合成置信度
```

## 4. 底部变盘四阶段状态机

宋第五章的核心机制。基于主级别在**归零轴形态**下的子级别运行逻辑。

### 4.1 四阶段

```
①单边下跌 → ②超跌反弹 → ③反抽 + 背离/动能不足 → ④零轴黏合 → 主级别启动反弹
```

### 4.2 每阶段的判定（基于子级别状态）

| 阶段 | 主级别状态 | 子级别状态 |
|------|----------|----------|
| ① | 接近零轴上方 | 在下跌线段中、仍在单边下跌 |
| ② | 第一次触 EMA52 | 归零轴反弹（但可能反抽） |
| ③ | 仍在 EMA52 附近 | 反抽 + 周期间底背离（**理性买点候选**） |
| ④ | 等待时机 | 完成下跌线段调整、零轴黏合 |

### 4.3 状态机的进入/退出

```
监控 (no phase) ─→ ① ─→ ② ─→ ③ ─→ ④ ─→ 反弹启动
                  ↑    ↑    ↑    ↑
                  └────┴────┴────┘  失败回退（任何阶段都可回退）
```

阶段可以**前进**也可以**回退**（如③出现假买点，回退到②）。

### 4.4 置信度

每个阶段都有"已进入此阶段"的置信度，由多个观察量合成：

```yaml
BottomPhaseSnapshot:
  current_phase: phase_1 | phase_2 | phase_3 | phase_4 | none
  phase_confidence: float
  phase_entry_ts: timestamp

  sub_signals:
    main_level_near_ema52: float
    sub_level_in_decline: float
    sub_level_recoiled: float
    sub_level_inter_cycle_divergence: float
    sub_level_zero_stick: float
```

### 4.5 主级别 ↔ 关键子级别对应

| 主级别归零轴 | 完成底部变盘的子级别 |
|------------|-------------------|
| 1h | 30m |
| 2h | 1h |
| 4h | 2h |
| 12h | 6h |
| D | 12h（数字货币）/ 2h（A 股） |
| 3D | D |
| W | 3D |
| M | 2W |
| Q | M |
| 6M / Y | Q / M |

→ 这些组合是**默认建议**，具体取决于品种的级别拓扑。

## 5. V 字反转检测

底部变盘的**特殊情形**——不是最大子级别走完，而是**更小级别突破横盘区间**。

### 5.1 三个必要条件

| 条件 | 测量 |
|------|------|
| 主级别保持归零轴形态 + MACD 收敛 | 主级别 |
| 零轴之下大多数小级别完成线段调整 + 底部形成横盘 | 多个子级别 |
| 下一长级别 EMA52 高于底部横盘区间上沿 + 实际突破 | 跨级别 |

### 5.2 算法步骤

```
1. 主级别处于归零轴附近 + DIF 拐头
2. 识别"底部横盘区间"= 最近 N 根 K 线的 [low_min, high_max]
3. 监控下一长级别的 EMA52 是否高于 high_max
4. 触发突破时刻：close 上穿 high_max
5. 标记 V 字反转候选（confidence ~ 0.7）
6. 持续观察反弹力度，更新置信度
```

### 5.3 V 字反转后的特征

- 反弹**力度强、速度快**
- 剩下未调整的小级别**易直接击穿零轴**（不再反抽）
- 弱势调整结构特征明显

## 6. 时间级别升级检测

宋第四章第九节。**周期间背离不变盘**的特殊归宿。

### 6.1 四个触发条件

| 条件 | 测量级别 |
|------|--------|
| ① 多次周期间背离不破零轴 | 当前级别 |
| ② 完成线段调整，DIF 黏合零轴 | 当前级别 |
| ③ MACD 黄白线无限接近零轴 | 长级别 |
| ④ K 线保持在 EMA24 之上 | 长级别 |

四条同时满足 → 升级触发。

### 6.2 升级 vs 穿零轴的判别

```
当前级别周期间背离 + 长级别有归零轴需求：
    ├─ 长级别处于高位空 → 穿零轴（线段终结）
    │
    └─ 长级别仍在低位 + K 线在 EMA24 之上 → 时间级别升级
```

**注意**：穿零轴与升级**互斥**。必须显式分支判定。

### 6.3 升级的下游动作

```
升级触发
    ↓
当前级别产生新线段（不切换线段方向，是新线段的早期阶段）
    ↓
后续形态对比从"周期间"升级为"线段间"
    ↓
当值任务递进给长级别
```

### 6.4 升级 vs 普通新线段的区别

| 维度 | 普通新线段（穿零轴后） | 升级新线段 |
|------|------------------|----------|
| direction | 翻转 | 保持 |
| 触发 | DEA 穿零确认 | 四条件合成 |
| 长级别状态 | 高位空 | 低位 / 黏合 |

## 7. 嵌套链遍历（顶部判定）

主级别反弹的**终结**判定。

### 7.1 倒推流程

要找主级别（如 12h）反弹的最高点：

```
1m / 3m 反弹结束（最末端最小级别）
    ↓
5m 反弹结束
    ↓
15m 反弹结束
    ↓
... 沿嵌套链向上 ...
    ↓
6h 反弹结束
    ↓
12h 反弹结束 = 主级别顶部出现
```

### 7.2 算法

```
对主级别 L 的嵌套链 chain = [L, L1, L2, ..., L_n]:
    for level in reverse(chain):
        if level.current_segment.has_ended():
            mark level as "completed at top"
        else:
            return "still ascending"
    return "main level top confirmed"
```

### 7.3 输出

```yaml
NestingChainState:
  main_level: str
  chain: List[str]
  chain_progress: List[(level_id, completion_pct)]
  topping_confidence: float
  expected_top_levels_remaining: int
```

## 8. 直系第一代扫描（启动判定）

主级别**反弹启动**的判定。

### 8.1 算法

```
对主级别 L 的直系第一代 directs = {D1, D2, ..., D_m}:
    completed_count = 0
    for direct in directs:
        if direct.has_completed_decline_segment():
            completed_count += 1

    completion_ratio = completed_count / len(directs)

    if completion_ratio >= θ_directs:
        mark as "directs completed, awaiting main level start"
    else:
        mark as "directs still settling"
```

$\theta_{\text{directs}}$ 默认 0.9（90% 的直系完成才算启动条件就绪）。

### 8.2 与四阶段的关系

直系第一代扫描**整合**到底部变盘四阶段的第④阶段判定中：第④阶段成立的实质就是"直系第一代基本走完"。

## 9. 跨级别协同度

衡量"多个级别同向程度"的标量。

### 9.1 定义

$$
\text{alignment\_strength} = \frac{1}{|\text{levels}|} \sum_{L} \mathbb{1}[\text{trend\_side}(L) = \text{dominant\_side}]
$$

即：投票一致的级别比例。

### 9.2 用途

- 协同度高 → 提升合成主标签的置信度
- 协同度低（多空各半）→ 主标签为"过渡 / 不确定"
- 配合**主导级别**（最大有效级别）判定整体方向

## 10. 输出接口

```yaml
MultiTimeframeFusion:
  alignment_strength: float
  dominant_trend: bullish | bearish | mixed

  bottom_phase:
    current_phase: phase_1 | phase_2 | phase_3 | phase_4 | none
    phase_confidence: float
    expected_start_level: str        # 哪个子级别是关键变盘级别

  v_reversal:
    confidence: float
    detected_breakout: bool

  level_upgrade:
    confidence: float
    current_level: str               # 哪个级别在升级
    target_level: str

  nesting_chain:
    main_level: str
    progress: List[(level_id, completion_pct)]
    topping_confidence: float

  direct_scan:
    main_level: str
    completion_ratio: float
    starting_confidence: float

  cascade_warnings: List[CascadeFailureWarning]

  validity_states:
    Dict[level_id, "active" | "inactive"]
```

## 11. 与单级别判定的接口

Layer D 从 Layer C 接收：

- 每级别的 `FormSnapshot`
- 每级别的 `UnitSnapshot`
- 每级别的 `ZeroCrossingEvent`（如果有）
- 每级别的 `DivergenceSignal`（如果有，见 09）

Layer D 输出 `MultiTimeframeFusion`，供 Layer E 序列化。

## 12. 单元测试建议

| 测试 | 验证 |
|------|------|
| 5m 底背离 + 15m 周期间背离 → 1h 底部第③阶段 conf 跳升 | bottom-up 传播 |
| D 强势多方 + 1h 顶背离 → 1h 顶背离 conf 衰减 | top-down 约束 |
| 30m 击穿零轴 → 1h 当值有效性变 inactive | 级联失效 |
| 主级别 W + 所有直系完成调整 → starting_confidence 高 | 直系扫描 |
| 主级别 1h + 1m 至 30m 沿嵌套链依次走完 → topping_confidence 高 | 嵌套链遍历 |
| 长级别低位 + 当前级别背离 → upgrade conf > zero_cross conf | 升级判定分支 |
