# macd-momentum — K线动能理论 Wiki 生成任务

## 你的职责
你是专门用于处理《K线动能理论》（宋建毅著）PDF 解析后内容的 Claude Code session。
你的任务：
1. 读取 `/tmp/mineru-output/` 下的 MinerU 解析输出 MD 文件
2. 对内容进行格式校正和完整性检查
3. 按章节拆分为独立的 wiki 页面
4. 生成符合 `~/wiki/option-timing/` 体系的 YAML frontmatter + wikilinks
5. 将生成的页面同步到 `~/wiki/option-timing/macd-momentum/` 目录
6. 更新 `index.md` 和 `log.md`

## 输出规范

### 页面列表（放在 ~/wiki/option-timing/macd-momentum/）
- `macd-basics.md` — MACD 构成与原理（DIF、DEA、能量柱、0轴）
- `macd-parameters.md` — 参数设置与周期选择
- `divergence-classification.md` — 本堆/邻堆/隔堆背离分类
- `momentum-energy-bar.md` — 能量柱与动能衰竭
- `golden-death-cross.md` — 金叉死叉
- `momentum-five-dimensions-macd.md` — 势能五度与MACD的关系
- `macd-trendline-combo.md` — MACD + 趋势线配合
- `multi-timeframe-macd.md` — 多周期联动

### 每个页面要求
- YAML frontmatter（title, created, updated, type: concept, tags: [macd-momentum, macd], sources, confidence, wikilinks）
- 至少 2 个 [[wikilinks]] 引用现有 wiki 页面
- 表格格式正确
- 数学公式用 LaTeX
- 引用来源标注 ^[source]
- 中文术语与 wiki 现有术语一致

### 参考术语表
- 趋势线 → [[concepts/trend-line]]
- MACD背离 → [[concepts/macd-divergence]]
- 势能五度 → [[concepts/momentum-five-dimensions]]
- 周期理论 → [[concepts/cycle-theory]]
- 裸K结构 → [[concepts/candlestick-structure]]
- 斜率与加速 → [[concepts/slope-and-acceleration]]
- 进场规则 → [[frameworks/entry-rules]]
- 出场规则 → [[frameworks/exit-rules]]
- 交易模型 → [[concepts/trading-models]]

### 系统操作（用 terminal 执行）
- `cd ~/wiki/option-timing` — wiki 根目录
- `jj describe -m "feat: add X from Song Jianyi K-line momentum theory"` — 提交
- `jj new` — 创建新的空变更
