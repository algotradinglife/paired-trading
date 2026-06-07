# macd-momentum 开发文档

> 本目录提供宋建毅《K 线动能理论》分析系统的开发指导文档。
> **本目录不包含可执行代码**——它是供另一个独立项目参考实现的工程规范。

---

## 项目定位

**输入**：多时间级别的 K 线 OHLC 数据流
**输出**：基于宋建毅 K 线动能理论的多周期分析结论，含连续置信度，供下游交易系统调用
**不做**：具体交易动作、多维度特征工程、与券商对接

完整范围见 [`01-scope-and-boundaries.md`](./01-scope-and-boundaries.md)。

## 理论基础

理论来源：宋建毅，《K 线动能理论》（中国财富出版社）。

宋理论两条核心主线：
- **背离判定**——周期内 / 周期间 / 线段间，含跳空、隐形、动能不足
- **多周期分析**——时间级别嵌套、底部变盘四阶段、级别升级、级联失效

本系统的工程任务是把这两条主线**算法化**，输出结构化的分析结论。

## 关键设计原则

1. **后验性 + 连续置信度**——所有"事件"（归零轴、背离、变盘）实时不可知，系统输出连续置信度而非布尔触发
2. **多周期信息融合是结构层，不是叠加层**——每个形态置信度都是跨级别融合后的结果
3. **每个时间级别独立计算**——大级别 MACD 不可从小级别采样得来
4. **completed 与 live 双轨**——已收盘状态用于严格判定，未收盘漂移值用于早期信号
5. **输出 API 稳定**——schema 版本化，向后兼容

## 阅读建议

按编号顺序阅读最高效。如果只读三份：

1. [`02-architecture.md`](./02-architecture.md)——系统全貌
2. [`11-output-schema.md`](./11-output-schema.md)——输出接口
3. [`14-glossary.md`](./14-glossary.md)——术语统一

实现阶段需要重点查阅：

- 数据结构 → [`03-data-model.md`](./03-data-model.md)
- 状态机 → [`06-vector-units.md`](./06-vector-units.md), [`07-zero-axis-crossing.md`](./07-zero-axis-crossing.md)
- 算法核心 → [`08-multitimeframe-fusion.md`](./08-multitimeframe-fusion.md), [`09-divergence-detection.md`](./09-divergence-detection.md)
- 参数调优 → [`12-thresholds-and-params.md`](./12-thresholds-and-params.md)
- 测试用例 → [`13-edge-cases.md`](./13-edge-cases.md)

## 文档清单

| 文件 | 内容 |
|------|------|
| [README.md](./README.md) | 本文 |
| [01-scope-and-boundaries.md](./01-scope-and-boundaries.md) | 项目范围与边界 |
| [02-architecture.md](./02-architecture.md) | 整体架构、模块划分、数据流 |
| [03-data-model.md](./03-data-model.md) | 核心数据结构 |
| [04-feature-extraction.md](./04-feature-extraction.md) | 5 个基础观测流 |
| [05-form-detection.md](./05-form-detection.md) | 形态识别（高位空/隐形/黏合/倒挂） |
| [06-vector-units.md](./06-vector-units.md) | 量能堆/单位调整周期/线段 + K 线结构 |
| [07-zero-axis-crossing.md](./07-zero-axis-crossing.md) | 穿零轴的严格判定 |
| [08-multitimeframe-fusion.md](./08-multitimeframe-fusion.md) | 多周期信息融合机制 |
| [09-divergence-detection.md](./09-divergence-detection.md) | 背离判定的统一框架 |
| [10-confidence-model.md](./10-confidence-model.md) | 置信度合成与传播 |
| [11-output-schema.md](./11-output-schema.md) | 输出 API schema |
| [12-thresholds-and-params.md](./12-thresholds-and-params.md) | 超参清单与默认值 |
| [13-edge-cases.md](./13-edge-cases.md) | 边界情形与陷阱 |
| [14-glossary.md](./14-glossary.md) | 中英术语对照 |

## 与 wiki 的关系

理论概念与方法论的人类可读版本在 `~/wiki/option-timing/macd-momentum/`：

- wiki 偏**理论与方法论**——为什么这么做
- doc 偏**工程规范**——具体怎么做

两者交叉引用、互相印证。

## 版本

- v0.1 — 2026-05-20 — 初稿
