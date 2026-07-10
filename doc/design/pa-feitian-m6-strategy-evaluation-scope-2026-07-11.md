# PA / Feitian M6 策略评估与筛选范围 - 2026-07-11

状态：设计文档，等待 ChatGPT 在 M6 开始前做阶段级审核。

基线：`main` at `bdcce5d`，包含 M5 merge PR #16。

## 1. M6 定位

M6 的目标是把 M5 的单次 premium-space outcome harness 扩展成可复现、
可比较、可审计的策略评估层，用于回答：

> 哪些 PA / Feitian 主观决策链节点、IV gate、期权 leg 和 exit policy，
> 在严格无前视的时间外样本上，具有稳定且可解释的 premium-space 结果？

M6 只产生评估证据和候选筛选结果，不改变生产决策链，不自动批准 setup，
不进入下单或 live monitoring。

## 2. 输入与输出边界

M6 读取 M4/M5 已提交的 artifact，不重新扫描前端，也不绕过已有 contract：

```text
真实 score_today artifacts
  -> pa_feitian_snapshot_v1
  -> pa_feitian_decision_intent_v1
  -> pa_feitian_premium_outcome_v1
  -> M6 evaluation dataset
  -> aggregate metrics + uncertainty + failure modes
  -> candidate screening report
```

所有 M6 运行必须记录：

- 输入 artifact 的路径、schema version 和 SHA-256；
- source commit、CLI 参数、policy 配置和数据访问状态；
- evaluation dataset 的行数、过滤原因和时间边界；
- train/validation/test 或 walk-forward 时间切分；
- 代码版本、随机种子、bootstrap 配置和结果 artifact hash。

M6 的主结果必须以 premium R 为主口径，同时保留 underlying R 作为独立
对照。不得把 underlying R 直接当作 option premium outcome。

## 3. 评估维度

M6 首批只评估已经存在于 decision-intent / premium-outcome contract 中的
维度，不在评估过程中发明新的主观标签：

1. Decision-trace node：节点状态、evidence、action、reason_codes、
   input_refs 和最终 decision_state。
2. IV gate：明确记录的 IV 条件和 gate 状态；缺失或无法回溯的 gate 不得
   被隐式归类为通过。
3. Option leg：call/put、underlying、到期结构、moneyness 或 contract
   family；使用决策时已经选定的 leg。
4. Exit policy：M5 固定 policy 作为 baseline，并在预先声明的候选集合
   内比较 stop、target、timeout 和 gap 处理规则。
5. Data regime：pool、时间段、数据访问状态和可用性 warning，作为分层
   诊断维度，不作为事后挑选最佳子集的依据。

每个维度必须支持 `unknown` / `not_evaluable`，不能把缺失信息转成普通
的负样本或正样本。

## 4. 主要统计量

每个候选组合至少输出：

- premium-space mean R（EV）；
- median R、标准差和中位数绝对偏差；
- 样本数、有效样本数和缺失/blocked/ambiguous/not_evaluable 数量；
- win rate，且明确定义为 `R > 0`，不能把 target hit 当作 win 的替代；
- stop、target、timeout、gap、ambiguous 的比例；
- MFE、MAE 的中位数和尾部摘要；
- bootstrap 95% CI，及按事件/日期聚类时使用的依赖结构说明；
- worst-case / lower-quantile 指标，用于识别只靠少数 runner 的虚高 EV；
- premium R 与 underlying R 的相关性和差异摘要。

报告必须同时展示 pooled、按 pool、按 underlying、按时间段和按关键
decision-trace 节点的结果。任何 `n` 很小的分组必须显式标记为
`insufficient_sample`，不能进入候选晋级排序。

## 5. 无前视与时间切分

M6 的时间纪律比统计显著性更优先：

- 任何分组、gate、leg 或 exit policy 的选择只能使用训练窗口；
- validation 只能用于锁定候选配置，不得反复试验后把结果当 test；
- test/OOS 只运行一次或按预先注册的 walk-forward fold 运行；
- decision timestamp 之后的 outcome、label、MFE、MAE、exit reason 和
  posterior 字段不得出现在决策输入中；
- 不能用全样本先筛出“有结果的 contract”再回填决策日；
- 同一事件的多个 option legs 必须按事件分组切分，禁止跨 leg 泄漏；
- 时间边界、时区和交易日历必须记录在 manifest 中；
- 同日 bar 的先后顺序未知时沿用 M5 的 `ambiguous` 语义，不得用最终收盘
  结果推断 stop/target 先后。

推荐首版使用固定时间序列 walk-forward：每个 fold 用过去窗口锁定候选
policy，在紧随其后的 OOS 窗口评估；不得使用随机 train/test split 作为
主证据。

## 6. 候选筛选规则

筛选是审计性 shortlist，不是自动策略晋级。候选进入 shortlist 前必须
同时满足：

- 预先声明的最小有效事件数；
- 至少两个非重叠 OOS 时间窗口有可比较结果；
- premium EV、win rate、退出分布和 CI 均已记录；
- 结果不是由单一 contract、单一日期或少数 runner 主导；
- 与 M5 baseline 的比较使用同一输入事件、同一数据可见性和同一成本口径；
- 对参数候选集合进行多重比较说明，不能只报告最佳组合；
- 发现结果冲突时保留 `inconclusive`，不能强行归入 pass/fail。

首版不设一个脱离样本量和置信区间的固定 EV 门槛。输出应包含
`promising`、`inconclusive`、`negative` 和 `blocked` 四类，并说明分类
依据。任何 shortlist 项仍需经过 M7 的人工审核，不能直接转成 execution
permission。

## 7. Failure-mode 分析

M6 必须把失败作为一等结果，至少按以下维度统计：

- decision state / trace node；
- option leg 与 moneyness；
- IV gate；
- gap、流动性不足、数据缺失和 daily-bar ambiguity；
- stop-first、target-first、timeout；
- underlying 正收益但 premium 亏损，及其反向情形；
- policy 在不同 pool、时间段和合约族的方向不稳定。

failure-mode 表必须能回到原始事件和 input_refs，允许 reviewer 检查其
是否因数据缺失、contract 选择、时间切分或 outcome 规则造成。

## 8. Artifact 与可视化要求

M6 至少生成四类可复现 artifact：

1. evaluation dataset：每行对应一个事件/leg/policy 组合，并含 provenance；
2. aggregate result：统计量、CI、样本和状态计数；
3. failure-mode report：可追溯到事件和 trace node；
4. screening report：候选分类、比较基线、限制和 reviewer 状态。

manifest 必须绑定这些 artifacts 的 hash，并记录是否来自真实数据、是否
包含 fixture fallback。frontend 仍只消费 copied artifacts，不直接访问
OptionStore、score_today 或 Python pipeline。

M6 dashboard 应支持：

- baseline 与候选 policy 的并排比较；
- EV/CI、样本量、状态分布和时间窗口；
- 按 trace node、IV gate、leg、pool 筛选；
- failure-mode drill-down 到事件和原始 artifact refs；
- `generated`、`fixture`、`review` 和 `insufficient_sample` 的明确标识；
- hash mismatch、data blocked、ambiguous 和 not_evaluable 的防御性状态。

## 9. Non-goals

- 不自动修改 decision-intent 或 snapshot；
- 不把 M6 shortlist 写回生产策略默认值；
- 不自动下单，不接 broker，不做 live monitoring；
- 不实现 M7 的人工确认、否决和 override ledger；
- 不把 M6 的历史结果宣称为未来收益保证；
- 不使用随机切分替代时间外样本；
- 不在没有真实 premium 数据时用 underlying R 伪造 option outcome；
- 不在首个 M6 slice 同时扩展新的决策节点、全量参数搜索和执行风控。

## 10. 建议实施切片

### M6-A：Evaluation contract and dataset

定义 evaluation row、aggregate result、failure-mode、screening report 的
schema 和 manifest extension；把 M5 outcome sidecar 转成不可变、可重放的
评估输入。

### M6-B：Baseline and walk-forward evaluator

实现 M5 baseline 的 pooled/by-pool/时间窗口统计、bootstrap CI、固定时间
序列 walk-forward 和 no-lookahead verifier。先证明 baseline 结果稳定，
再加入候选维度。

### M6-C：Controlled policy comparison

在预先注册的有限候选集合内比较 exit policy、IV gate 和 option leg；固定
事件集合，输出相对 baseline 的差异、置信区间和多重比较记录。

### M6-D：Failure modes and reviewer dashboard

提供 trace node / failure-mode drill-down、候选 shortlist 及审阅状态。
完成后才提交 M6 final review packet，等待 ChatGPT 阶段验收。

## 11. M6 完成验收标准

M6 final review 前必须同时具备：

- schema、manifest 和 provenance 可验证；
- 固定输入可重复生成相同 evaluation dataset 和 aggregate artifacts；
- no-lookahead verifier 通过，并覆盖时间切分、input_refs 和同事件多 leg；
- M5 baseline 与至少一个受控候选比较完成；
- pooled、分层、时间窗口和 failure-mode 结果均可追溯；
- bootstrap/不确定性和最小样本规则有测试；
- frontend 仅消费 copied artifacts，能显示 hash/data/review 状态；
- 真实数据与 fixture fallback 的状态不混淆；
- 不存在 live trading、order execution 或自动策略晋级路径；
- final packet 能让外部 reviewer 仅凭公开路径复核目标、输入、命令、结果
  和已知限制。

## 12. 阶段决策

M6 的最终产物是“可解释的候选评估证据”，不是“可执行策略”。只有在
M6 完成并经 ChatGPT 阶段验收后，才进入 M7 半自动决策台设计；任何
`promising` 结果都必须重新经过人工决策链和 M7 审核闭环。
