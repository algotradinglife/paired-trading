# PA 推理链复刻——高质量标注数据集构建规范（→ data-engineer，2026-06-14）

> 发起：researcher（paired-trading）。消费方：trade-philosopher（PA 交易员推理链代码复刻）。
> 责任方：**data-engineer**（原始数据 + 高质量标注数据集均归其负责）。
> 目标：用「预筛 + 自动结果标 + 复刻批量标 + 人工裁决尾部」的流水线，**取代逐K全序列标注**
> （现状：复刻体逐节点跑 LLM，rb2607 23 节点仅 2 单，~91% 算力浪费在注定 no-trade 的 bar 上）。

本规范给 **WHAT + 质量约定 + 验收标准**；HOW（数据plumbing、调度、存储）由 data-engineer 定。
researcher 已有两个**可直接复用的参考实现**（见 §6）。

---

## 1. 一句话目标
为「上下文 → 交易员是否下单 + 订单参数 + 推理链 + 实现结果」构建一个**可复现、无泄漏、带划分**
的监督数据集，让复刻体训练/验证不再依赖逐K，并定位推理链的瓶颈闸门。

## 2. 核心洞见（决定流水线形状）
1. **结果标签免费且确定性**：复刻只记订单、不记出场结果；而出场结果可由前向 K 线机械算出
   （researcher 的 `eval_spec001_ev.simulate_order` 已对 rb2607 精确复现 +2R）。→ `(决策→实现R)`
   的后半段不需人/LLM。
2. **决策标签贵 → 只标候选**：用便宜的确定性 detector 把全序列压到「长得像 setup」的候选
   （proxy 在 rb2607 点 ~187 候选 vs 全序列 ~12000 bar），**只对候选跑复刻/人工**。
3. **复刻体即标注器，人只裁决尾部**：复刻多图 n=15 一致率 100%；让人只看「复刻不确定 / 与确定性
   proxy 分歧」的尾部，且以 **annotation-by-correction**（改/点赞，非从零标，快 5–10×）。

## 3. 四阶段流水线（建议交付顺序）

### P0 — 约定钉死 + 候选闸门 + 自动结果标（pilot 单品种，如 ag 或 rb）
- **先与 trade-philosopher 钉死结果/失效约定**（见 §4），否则结果标签自相矛盾、数据作废。
- 跑确定性**候选闸门**（高召回、宁松勿紧）把全序列压成候选集。可直接用/改 researcher 的
  `backtest_spec001_proxy.detect_signals`。
- 对每个候选跑确定性**出场仿真**得 `realized_R / exit_kind / 是否触发`（复用 `simulate_order`）。
- 产出：pilot 品种的「候选 + 自动结果标」表 + 复现命令。

### P1 — 复刻批量标候选（决策标签 + 推理链）
- 与 trade-philosopher 协调，用复刻体（`replay_cn.py` / `replica_decide`）**只对候选** bar 打标，
  落 `decision`（order/direction/entry/stop/target/win_rate_est/confidence）+ **完整 `decision_trace`**
  （二元树各节点触发情况）+ `diagnosis_summary`。
- 这一步把「逐K全扫」变成「候选批处理」，成本下降约一个数量级。

### P2 — 高信息样本挖掘 + 人工裁决尾部
- **结果挖掘**：用确定性结果挑「2:1 会触目标 / 会被扫」的 bar，得到天然均衡的正/负例
  （⚠️ look-ahead **只用于挑样本，绝不进特征**）。
- **分歧采样**：proxy vs 复刻分歧点（~100× selectivity 差，分歧点信息最高）入人工队列。
- 人工只对该尾部 **改/点赞**（给定候选 + 自动结果 + 复刻建议决策）。记录 `label_source`。

### P3 — 组装版本化数据集 + 划分 + 数据说明书
- 按 §5 schema 落盘，附 splits、dedup、datasheet（含约定、覆盖、已知偏差）、复现命令。
- 过 §7 验收。

## 4. 必须钉死的保真度约定（否则标签静默错误——researcher 已踩坑）
1. **时区**：复刻 node `end` 与 cn_data `ts_open` **均 UTC epoch**。用本地时区会把 +2R 标成 −1R。
2. **出场 / 失效约定**（结果标签直接依赖）：rb2607 入场前价收过 3362（低于 spec 文字失效线 3366、
   也低于止损 3365）——按这俩判则该单作废、无 +2R；只有按复刻 `invalidation_condition`
   （"<3352 或强势空头棒"，自由文本）才有效。**自由文本失效无法机械判定** → 二选一：
   (a) 复刻在 replay 输出里**直接附每单实际出场结果**；或 (b) philosopher 给**确定性出场约定**
   （入场前失效判据 / 挂单有效期 / 同根 stop-target 优先级 / §11 管理出场）。约定写进 datasheet。
3. **无前视**：特征在 bar i 只能用 ≤i 信息；look-ahead 仅允许用于**挑样本**，不得进特征。
4. **窗口端点 / 暖机期**：端点处理错误会系统性偏移分类（researcher 曾因「反弹窗口误含信号当根」
   把结论从弱支持翻成显著反对）。逐根分类对端点极敏感，需单测覆盖。

## 5. 数据集 schema（每条 = 一个候选决策点）
```
id, instrument(product), contract, interval, ts_utc
context_ref            # 如何无前视加载 ≤ts 的 bar 窗口（避免把 OHLC 全量塞进表）
features_det           # 确定性特征：channel_metrics / swing pts / ATR / 信号棒几何 /
                       #   range_vs_avg / test_ordinal …（无前视）
candidate_source       # 哪个确定性闸门点中（高召回闸门可多源）
decision               # 复刻(±人工)：order(bool)/direction/order_type/entry/stop/target/
                       #   payoff/win_rate_est/confidence/invalidation_condition
decision_trace         # 二元树逐节点触发（一等公民，供逐节点监督 + 定位瓶颈闸门）
label_source           # replica | human_corrected | human_from_scratch
adjudication           # agree(proxy,replica)? / human_verdict（仅尾部）
outcome                # 确定性：triggered/exit_kind(target|stop|timeout|*_data_exhausted)/
                       #   realized_R(gross)/exit_ts  —— 无前视泄漏进 features
liquidity              # ts 处 volume/OI（用于流动性加权 / 过滤）
split                  # 按时间的 fold + train/val/test
dedup_key              # (product, day) 跨月去重
```

## 6. researcher 可直接复用的参考实现（commit fd1f32eb / 18ae0282，paired-trading/src）
- `scripts/backtest_spec001_proxy.py::detect_signals` — 确定性候选闸门（ATR 相对、无前视、可调阈值）。
- `scripts/eval_spec001_ev.py::simulate_order` — 确定性出场仿真 → `realized_R/exit_kind`，
  含「数据不足→unresolved 排除」「同根 stop-first」「前向窗口锚定」等已修正的口径（10 单测）。
- 数据入口：trade-philosopher `tp.pa.cn_data.load_cn_window`（5min，**SHFE-only**：ag/au/cu/rb 等；
  DCE/CZCE/INE 的 i/sc 等不在 5min store → 若需更广覆盖，这本身是 data-engineer 的原始数据缺口项）。
- 复刻标注器：trade-philosopher `scripts/replay_cn.py` + `src/tp/pa/`（decision + decision_trace）。

## 7. 验收标准
1. **约定钉死**：tz + 出场/失效约定有明确定义并写入 datasheet；同一 bar 重跑结果标签 byte 一致。
2. **无泄漏**：特征无前视（单测）；look-ahead 仅用于选样本；train/test **按时间切**、跨月按
   `(product,day)` 去重，train/test 无近重复。
3. **覆盖与均衡**：pilot 品种候选集 + 自动结果标完整；正/负例经结果挖掘达到可用均衡（非 1:50）。
4. **决策链完整**：每条带 `decision_trace`，可逐节点监督；能产出「各闸门触发率 + 该闸门处 EV」表
   以定位瓶颈闸门。
5. **可复现**：脚本 + 命令 + 版本化工件（artifact 走 gitignore + 命令重生，沿用本仓 data/review 惯例）。
6. **人工成本**：人只裁决「分歧/不确定」尾部，以 correction 形式；记录 `label_source` 占比。

## 8. 范围与协作边界
- data-engineer：拥有原始数据 + 数据集构建/存储/版本化/调度；落 §5 schema、过 §7 验收。
- trade-philosopher：提供复刻标注器（decision + trace）、钉死 §4.2 出场/失效约定（或在 replay 输出附结果）。
- researcher：提供候选闸门 + 结果仿真参考实现（§6）、消费成品做 EV/边缘评估；不碰原始数据管线。
- 建议先 **pilot 单品种（ag 或 rb）跑通 P0→P1 全链**，约定/schema 验收后再铺品种。

复现入口（researcher 侧参考）：`cd src && python3 scripts/backtest_spec001_proxy.py --products ag --out data/review/spec001_proxy_ag.json`；
`cd src && python3 scripts/eval_spec001_ev.py --validate`。
相关：[[spec001-ev-eval]]、doc/spec-001-ev-readiness-2026-06-14.md、doc/spec-001-proxy-ev-2026-06-14.md。
