# 14 — 术语对照

> 本系统使用的核心术语清单，含中文、英文、定义、出处。供下游实现者、文档编写者保持一致。

---

## A. 基础指标术语

| 中文 | 英文 / 代码标识 | 定义 | 出处 |
|------|--------------|------|------|
| MACD | MACD | Moving Average Convergence / Divergence，异同移动平均线 | 标准技术指标 |
| DIF | DIF / `dif` | $\mathrm{EMA}_{12}(close) - \mathrm{EMA}_{26}(close)$，又称白线、快线 | MACD 三件套 |
| DEA | DEA / `dea` | $\mathrm{EMA}_9(\text{DIF})$，又称黄线、慢线 | MACD 三件套 |
| 能量柱 / 柱体 / Histogram | Hist / `hist` | $2 \cdot (\text{DIF} - \text{DEA})$ | MACD 三件套 |
| EMA | EMA | Exponential Moving Average，指数加权移动平均 | 标准 |
| EMA24 | EMA24 / `ema24` | 24 周期 EMA，主图均线 | 宋建毅 |
| EMA52 | EMA52 / `ema52` | 52 周期 EMA，主图均线 | 宋建毅 |
| 零轴 | zero axis | MACD 副图的 y=0 横线 | 通用 |

## B. 零轴位置术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 多方市场 | bullish market | DIF > 0 且 DEA > 0 |
| 空方市场 | bearish market | DIF < 0 且 DEA < 0 |
| 高位 | high position | DIF 远离零轴（绝对值大）。零轴上下统称"高位" |
| 远离零轴 | distant from zero | 同上 |
| 高位空 | high position void / HPV | 高位 + 柱体衰减形成的空间夹角 |
| 归零轴 | near zero axis / `near_zero_axis` | DIF 无限接近零，或价格触 EMA52 |
| 完美形态 | perfect formation | DIF ≈ 0 + 价格 ≈ EMA52 同时满足 |
| 穿零轴 | zero axis crossing | DEA 穿过零 + K 线击穿 EMA52 + 次根确认 |
| 归零轴反弹 | rebound from zero | 黄白线归零后向远离方向移动 |
| 归零轴反抽 | pullback from zero | 同上（在零轴下方时） |

## C. 形态术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 隐形 / 隐形形态 | hidden form / `hidden` | 柱高 ≈ 0 但价格在推进 |
| 高位隐形 | high position hidden / `hidden_subtype: high` | 隐形发生在 DIF 远离零轴时 |
| 归零轴隐形 | near-zero hidden / `hidden_subtype: near_zero` | 隐形发生在 DIF 接近零轴时 |
| 零轴黏合 | zero stick / `zero_stick` | DIF 刚穿零 + 柱与 DIF 同向 + 持续 |
| 零轴倒挂 | zero inverted / `zero_inverted` | DIF 接近零 + 柱与 DIF 异向 |
| 零轴引力 | zero axis gravity | DIF 远离零轴后被回拉的现象（数学上 = 均值回归） |
| 强势调整 | strong adjustment / `k_structure: strong` | 高位横盘震荡型调整 |
| 超强势调整 | ultra-strong adjustment / `k_structure: ultra_strong` | 倾斜向上 + K 在 EMA24 之上 |
| 弱势调整 | weak adjustment / `k_structure: weak` | 快速下跌至 EMA52 型调整 |
| 顶分型 | top fractal | 三根 K 线呈倒 V，中间最高（辅助参考） |
| 底分型 | bottom fractal | 三根 K 线呈 V，中间最低（辅助参考） |
| 送钱形态 | goldmine form / `goldmine_form` | 隐形 + 高位空 + 分型 + 同向多级别 + 分立背离 五重共振 |

## D. 时间矢量单元术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 能量柱 | bar (in MACD histogram) | 单根 K 线对应的 Hist 高度 |
| 量能堆 | heap | 连续同号 Hist 的集合（容忍中间短暂归零） |
| 单位调整周期 | unit adjustment cycle / cycle | DIF 从零轴出发到回归零轴的一段区间 |
| 线段 | segment | DEA 第一次穿零轴到下一次反向穿零轴的整段 |
| 上涨线段 | up segment | DEA 上穿零轴启动的线段 |
| 下跌线段 | down segment | DEA 下穿零轴启动的线段 |
| 1 号参考点 | reference point / `reference_*_id` | 容器内首个或最高的代表，用于背离比较的基线 |
| 量能堆失效 | heap reset / reference reset | 新堆峰值更高时旧参考点失效 |
| 连续跳空 | continuous gap | 量能堆内 Hist 短暂归零但未释放反向柱 |
| 分立跳空 | discrete gap | 多个量能堆之间被反向柱分割 |

## E. 背离术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 背离 | divergence | 价格创新极值但能量端衰减 |
| 顶背离 | top divergence | 上涨线段中的背离 |
| 底背离 | bottom divergence | 下跌线段中的背离 |
| 周期内背离 | intra-cycle divergence | 同 cycle 内不同 heap 之间的背离 |
| 周期间背离 | inter-cycle divergence | 同 segment 内不同 cycle 之间的背离 |
| 线段间背离 | inter-segment divergence | 升级后相邻两线段的背离 |
| 跳空背离 | gap divergence | 周期内通过跳空形成的背离 |
| 连续跳空背离 | continuous gap divergence | 周期内连续跳空形态的背离 |
| 分立跳空背离 | discrete gap divergence | 周期内分立跳空形态的背离 |
| 隐形跳空背离 | hidden gap divergence | 周期内隐形（柱 ≈ 0）的背离 |
| 动能不足 | weakness / momentum insufficiency | 价格未破前极值但能量衰减 |
| 隐形动能不足 | hidden weakness | 动能不足 + 柱 ≈ 0 |
| 跳空非背离 | gap non-divergence | 跳空形态但新堆 > 旧堆（背离不成立，参考点重置） |
| 顶背离强信号 | strong top divergence | 多周期协同 + 隐形 |

## F. 多周期与级别术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 时间级别 | time level / `level_id` | K 线的聚合周期（如 "1h", "D"） |
| 当前级别 | current level / `L` | 你正在分析的级别（相对概念） |
| 次级别 | sub level / `sub(L)` | 当前级别 ÷ 2 的级别 |
| 长级别 | super level / `super(L)` | 当前级别 × 2 的级别 |
| 主级别 | main level / `main_level` | 当前正在归零轴并产生趋势的那个大级别 |
| 直系第一代 | direct children | 主级别直接包含的所有较小级别（集合） |
| 嵌套链 | nesting chain | 沿"每层取最大子级别"递归向下展开的有序序列 |
| 当值任务 | active duty | 某级别正在为主级别趋势提供动能 |
| 当值有效性 | validity / `is_active` | 某级别是否仍能有效当值 |
| 级联失效 | cascade failure | 小级别失效导致长级别也失效的传播现象 |
| 时间级别升级 | level upgrade | 周期间背离不破零的归宿，产生新线段 |
| 底部变盘 | bottom reversal / bottom phase | 主级别归零后的反弹启动过程 |
| 底部四阶段 | four-phase bottom | ①单边下跌 → ②超跌反弹 → ③反抽背离 → ④零轴黏合 |
| V 字反转 | V reversal | 跨级别突破横盘区间的特殊反转形态 |
| 漂移期 | drift period | 大级别 K 线未收盘时 MACD 随 close 变化的阶段 |
| 对齐时刻 | alignment moment | 多个级别 K 线同时收盘的时刻 |

## G. 系统状态术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 已收盘 | completed | K 线/单元已结束，状态固定 |
| 未收盘 | live | K 线/单元仍在进行，状态会变 |
| 完成度 | completion | 容器已运行的根数 / 预期总根数 |
| 持续根数 | persistence | 当前状态已保持的连续 K 线根数 |
| 启动 | start | 容器或事件的起点 |
| 终结 | termination / end | 容器或事件的终点 |
| 候选 | candidate | 事件已满足部分条件，待确认 |
| 确认 | confirmed | 事件已满足全部条件 |
| 失效 | invalidated | 事件被反向证据否定 |
| 反转 | reversal | 趋势方向改变 |
| 变盘 | regime change | 同上（中文俗称） |
| 多空切换 | bull-bear switch | 多方/空方市场切换 |

## H. 置信度术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 置信度 | confidence | 系统对某事件的概率估计 ∈ [0, 1] |
| 单级别先验 | local prior / `conf_local` | 仅基于当前级别信号的置信度 |
| 多周期协同因子 | multi-level factor / `f_multi_level` | 跨级别融合的乘性因子 |
| 自下而上 | bottom-up | 小级别支持大级别的传播 |
| 自上而下 | top-down | 大级别约束小级别的传播 |
| 协同度 | alignment strength | 多个级别同向程度 |
| 档位 | stage | 置信度的离散分级 |
| 后验确认 | post-hoc confirmation | 事件实际发生后的事后判定 |

## I. 输出术语

| 中文 | 英文 / 代码标识 | 定义 |
|------|--------------|------|
| 快照 | snapshot | 某时刻的状态记录 |
| 主标签 | primary label | 当前最重要的合成结论 |
| 辅助标签 | secondary labels | 次要的并存判定 |
| 关注事件 | events | 按置信度排序的待关注事项 |
| schema 版本 | schema version | 输出结构的版本号 |
| 系统时间戳 | system_ts | 系统计算输出的时间 |
| 数据时间戳 | data_ts | 数据本身的时间戳 |

## J. 操作时间尺度（仅供参考，下游消费）

| 时间尺度 | 触发的事件类型 | 矢量单元 |
|---------|------------|-------|
| 短线 | 周期内背离、归零轴接近 | heap |
| 中线 | 周期间背离、底部变盘、动能不足 | cycle |
| 长线 | 线段间背离、级别升级、级联失效 | segment |

注：操作时间尺度的解释**属于下游项目**——本系统只输出事件本身。

## K. 哲学性概念（不直接计算）

| 中文 | 英文 | 备注 |
|------|------|------|
| 能量 / 动能 | energy / momentum | 宋的物理隐喻，实际是价格的二阶动力学滤波 |
| 力度 | force | 单根 K 线的强弱（在本系统中未单独建模） |
| 加速度 | acceleration | Hist 序列的趋势变化 |
| 零轴引力 | zero gravity | DIF 的均值回归性质 |
| 桥面失支撑 | unsupported bridge | 高位空的物理隐喻 |
| 火箭无燃料 | rocket without fuel | 隐形的物理隐喻 |
| 万物负阴抱阳 | yin-yang duality | 宋引《道德经》的多空对立 |

这些概念用于理解，**不直接对应代码**。

## L. 与外部体系的术语对照（参考，不在本系统）

某些理论体系有相似概念但定义不同。**本系统采用宋建毅的定义**：

| 概念 | 宋建毅 | 肖淳心课程 | 缠论 |
|------|------|---------|------|
| 背离的容器 | 单位调整周期 | 趋势线 + MACD 背离 | 中枢 |
| 趋势确认 | 穿零轴 + EMA52 + 次根 | 趋势线突破 | 走势级别破坏 |
| 反弹判定 | 归零轴 + 嵌套链 | 趋势线 + 五度 | 中枢延伸 |

注：本系统**不使用**肖淳心和缠论的术语。wiki 内有这些体系的并行页面（理论参考），但 doc 严格只用宋的语言。

## M. 缩写

| 缩写 | 全称 |
|------|------|
| DIF | Difference (白线) |
| DEA | DIF Exponential Average (黄线) |
| Hist | Histogram (能量柱) |
| EMA | Exponential Moving Average |
| HPV | High Position Void (高位空) |
| MTF | Multi-Timeframe (多周期) |
| K 线 | K-line / candlestick |

---

**用法约定**：

- 代码中**严格用英文 / 代码标识**（如 `hist`, `dif`, `zero_stick`）
- 文档中**优先中文 + 第一次出现附英文**（如 "高位空（high position void, HPV）"）
- 跨文档保持术语一致——任何概念有疑问回查本文
