# 04 — 特征提取层

> 系统的所有上层判定都建立在 5 个基础观测流之上。本文档定义这 5 个流的计算方式。

---

## 1. 基础指标（前置）

### 1.1 MACD 三件套

参数采用标准默认值：

| 参数 | 值 |
|------|---|
| 快速 EMA 周期 | 12 |
| 慢速 EMA 周期 | 26 |
| Signal 周期 | 9 |

计算式：

$$
\begin{aligned}
\mathrm{EMA}_N(x_t) &= \alpha \cdot x_t + (1-\alpha) \cdot \mathrm{EMA}_N(x_{t-1}), \quad \alpha = \frac{2}{N+1} \\
\text{DIF}_t &= \mathrm{EMA}_{12}(\text{close}_t) - \mathrm{EMA}_{26}(\text{close}_t) \\
\text{DEA}_t &= \mathrm{EMA}_9(\text{DIF}_t) \\
\text{Hist}_t &= k \cdot (\text{DIF}_t - \text{DEA}_t)
\end{aligned}
$$

其中 $k$ 是直方图缩放因子（`hist_scale`），可配置。

**Histogram 缩放系数 $k$**：

| 平台 / 来源 | $k$ |
|----------|-----|
| Aspray 1986 原始定义 | 2.0 |
| **TradingView** | **1.0** |
| MetaTrader 4/5 | 1.0 |
| 多数现代图表平台 | 1.0 |

→ **本系统默认 $k = 1.0$** 以与 TradingView 等可视化端**绝对值可比**。Aspray 的 ×2 可以作为可选参数保留，但不再是默认值（实测见 src 端 `macd()` 函数）。

**实现要点**：
- EMA 初值：第一根 K 线的 close（或前 N 根的 SMA，两种实现都可，需保持一致）
- Warmup 期：建议丢弃前 80 根（约 3×26）以避免初值偏差
- 每个时间级别独立计算（**严禁**从小级别 MACD 上采样到大级别）
- 已实测：标准 EMA 实现 + $k=1.0$ 在 SPY 的 1h / D / W 三个时间级别上与 TradingView 内置 MACD 的差异 < 0.005（详见 src/scripts/validate_macd.py）

### 1.2 EMA24 / EMA52

主图均线，与 MACD 副图无关：

$$
\mathrm{EMA24}_t = \mathrm{EMA}_{24}(\text{close}_t), \quad \mathrm{EMA52}_t = \mathrm{EMA}_{52}(\text{close}_t)
$$

**含义（来源宋的经验拟合）**：
- EMA52 ≈ 当前级别**归零轴**时 K 线触碰的位置
- EMA24 ≈ 次级别归零轴时 K 线触碰的位置

## 2. 5 个基础观测流

每根 K 线收盘（或 live tick）时，对**每个时间级别独立**计算下列 5 个观测量。这些观测量是上层所有形态识别的输入。

### 2.1 流 1：`dif_proximity_zero`（DIF 距零轴的归一化距离）

**定义**：

$$
\text{dif\_proximity\_zero}_t = 1 - \frac{|\text{DIF}_t|}{R_t}
$$

其中 $R_t$ 是归一化基准（参考摆幅），取以下三种之一（推荐采用最后一种）：

| 选项 | 计算 | 优点 | 缺点 |
|------|------|------|------|
| 当前线段内 max\|DIF\| | $\max_{s \in \text{current\_segment}} \|DIF_s\|$ | 符合宋的语义 | 依赖线段已知 |
| 历史 N 根 max\|DIF\| | rolling max | 启动期可用 | N 选择敏感 |
| DIF 滚动标准差 | $k \cdot \sigma(\text{DIF}_{t-N:t})$ | 自适应噪声 | 解释性较弱 |

**默认实现建议**：组合使用——线段已知时用线段内 max；线段未知时退化为 rolling max（N=200）。

**值域**：$[0, 1]$，越接近 1 越接近零轴。

### 2.2 流 2：`hist_amplitude_ratio`（Hist 当前高度相对历史摆幅）

**定义**：

$$
\text{hist\_amplitude\_ratio}_t = \frac{|\text{Hist}_t|}{H_t}
$$

其中 $H_t$ 是 Hist 的历史摆幅参考，建议：

$$
H_t = \max_{s \in \text{current\_segment}} |\text{Hist}_s|
$$

线段未知时退化为 rolling max（N=200）。

**值域**：$[0, 1+)$，超过 1 表示当前柱创了线段新高。

**用途**：识别隐形（接近 0）和能量峰值。

### 2.3 流 3：`hist_dif_sign_alignment`（柱与黄白线的符号关系）

**定义**：

$$
\text{hist\_dif\_sign\_alignment}_t = \mathrm{sign}(\text{Hist}_t) \cdot \mathrm{sign}(\text{DIF}_t)
$$

**值域**：$\{-1, 0, +1\}$
- $+1$ = 同向（如多方市场中放红柱）
- $-1$ = 异向（如多方市场中放绿柱，零轴倒挂特征）
- $0$ = 至少一方为零

**用途**：区分零轴黏合 vs 零轴倒挂。

### 2.4 流 4：`state_persistence`（当前状态的持续根数）

**定义**：当前形态参数保持稳定（无显著变化）的连续 K 线数。

具体度量需根据形态类型选择：

| 用于哪个形态 | 度量方式 |
|------------|---------|
| 高位空 | Hist 衰减持续根数 |
| 隐形 | Hist 持续接近零的根数 |
| 零轴黏合 | DIF 持续接近零的根数 |
| 零轴倒挂 | Hist 与 DIF 异号的根数 |

**值域**：整数 $\geq 0$。

**用途**：区分"瞬时穿越"vs"真正进入某状态"，提高置信度。

### 2.5 流 5：`price_momentum`（价格方向性增量）

**定义**：

$$
\text{price\_momentum}_t = \frac{\text{close}_t - \text{close}_{t-k}}{\text{close}_{t-k}}
$$

其中 $k$ 是 lookback 窗口（建议 $k = 5$，即过去 5 根 K 线的累计涨跌幅）。

**值域**：实数。正值 = 上涨，负值 = 下跌。

**用途**：识别隐形形态（价格在动但能量未释放）的核心特征。

## 3. 流的更新时机

| 触发时机 | 重新计算哪些流 |
|---------|-------------|
| live K 线 tick 更新 | 全部 5 个流（live 值） |
| 某级别 K 线收盘 | 全部 5 个流（completed 值固化） |

**重要约束**：
- 流 1、2 的归一化基准 $R_t, H_t$ 只在 K 线收盘时更新（不在 tick 中频繁变化）
- 流 4（持续根数）只在 K 线收盘时计数 +1

## 4. 跨级别独立性

每个时间级别独立维护自己的 5 个流。跨级别的关联**不发生在本层**——发生在 Layer D 融合层。

## 5. 各形态对流的依赖（前向引用 05）

下面是流 → 形态的依赖关系表（详细规则见 [`05-form-detection.md`](./05-form-detection.md)）：

| 形态 | 流 1 | 流 2 | 流 3 | 流 4 | 流 5 |
|------|:---:|:---:|:---:|:---:|:---:|
| 高位 | ✓ | | | | |
| 高位空 | ✓ | ✓ | ✓ | ✓ | |
| 隐形 | | ✓ | | ✓ | ✓ |
| 零轴黏合 | ✓ | ✓ | ✓ | ✓ | |
| 零轴倒挂 | ✓ | | ✓ | ✓ | |
| 归零轴接近 | ✓ | | | | |

每个形态都是 5 个流的特定组合 + 阈值规则。

## 6. 输出接口

`feature_stream` 模块对外暴露：

```yaml
FeatureSnapshot:
  level_id: str
  timestamp: timestamp
  is_completed: bool

  dif_proximity_zero: float
  hist_amplitude_ratio: float
  hist_dif_sign_alignment: int        # -1, 0, +1
  state_persistence_by_form:          # 因为对不同形态度量不同
    high_position_void: int
    hidden: int
    zero_stick: int
    zero_inverted: int
  price_momentum: float

  # 元数据（便于追溯）
  base_indicators:
    dif: float
    dea: float
    hist: float
    ema24: float
    ema52: float
    close: float
```

下游模块（form_detector / divergence_detector）按需消费。

## 7. 数学不变量

实现时可作为单元测试：

1. $\text{Hist}_t = 2 \cdot (\text{DIF}_t - \text{DEA}_t)$
2. $\text{DEA}_t$ = $\text{DIF}_{t-9:t}$ 的 EMA9，因此变化滞后于 DIF
3. $\text{dif\_proximity\_zero} \in [0, 1]$ 在所有合法输入下成立
4. 当 $\text{DIF}_t = 0$ 时，$\text{dif\_proximity\_zero}_t = 1.0$
5. 同价格输入下，不同语言/库实现的 MACD 应在合理误差范围内一致（建议相对误差 < $10^{-6}$）

## 8. 已知问题与注意

### 8.1 EMA52 在大级别上的延迟

大级别（如周线、月线）的 EMA52 收敛较慢，warmup 期可能持续数年（历史数据）。实务上需要：
- 提供足够长的历史数据
- 或在大级别上接受较高的初值偏差直至收敛

### 8.2 跨平台 MACD 差异

不同交易平台的 MACD 实现可能有微小差异（如 EMA 初值、修正系数）。本系统采用**严格 EMA 递推**作为 ground truth，**不**与任何特定平台对齐。

### 8.3 K 线缺失

如果输入数据有缺失（缺一根 K 线），实现应：
- 不补齐（保留 gap）
- MACD 在 gap 处的连续性受 EMA 递推自然处理
- 但要在元数据中标记 gap 的存在，便于追溯
