# 综合 gate 设计（P2，2026-06-13）

卡片 t_6fe02de5（epic t_d6dccbab）。综合 Phase 1 两个验过的 gate，给 P3 productionize
提供设计依据。**P3（接 policy/confidence）需 Hermes 对 de-weight 决策签字；本文件是
设计提案 + 叠加证据，不替 Hermes 拍 productionize 的板。**

## 输入（Phase 1 验过的两个 gate，均限 bottom×opposing）

| gate | 定义 | full-sample 证据 | OOS（nested） |
|------|------|-----------------|---------------|
| **A 过度延伸惩罚**（P1a/t_6c3f043a） | keep range_vs_avg ≤ 1.0（剔过度延伸信号棒） | gap +0.52R, P=1.000 | +0.159（方向稳，OOS 样本偏小） |
| **B 二次入场偏好**（P1b/t_c8aad725） | keep ordinal == 1（首测，de-weight 回踩二测） | gap +0.39R, P=0.998 | +0.78R, P=0.997（OOS 显著） |

P1a 另见 bottom×neutral 也显著（gap +0.77, P=0.998）；top 侧不成立/反向——A 限 bottom 侧。

## 叠加测量（同一 bottom×opposing 事件群，n=312，CN+US）

| 组 | n | EV(R) | win | lane improve vs full |
|----|---|-------|-----|----------------------|
| full | 312 | +0.069 | 52.2% | — |
| A only（not over-ext） | 122 | +0.385 | 67.2% | +0.316 |
| B only（first test） | 85 | +0.364 | 63.5% | +0.295 |
| **A ∧ B** | **35** | **+0.665** | **74.3%** | **+0.596** |

- **边际增量**：both − A = **+0.280**、both − B = **+0.301**——每个 gate 在另一个之上仍各加
  ~+0.29R，**两者互补/正交、非冗余**（捕捉不同质量维度：入场时序 vs K 线几何）。
- both vs full bootstrap：gap +0.596，CI [+0.218, +0.961]，**P=0.999**（显著）。
- 2×2 列联：first 85 个里仅 35 个同时 not-over-ext（50 个首测是过度延伸的）；
  retest 227 个里 87 个 not-over-ext——两条件大体独立。
- **代价**：A∧B 硬筛只留 35/312 = **11%** 信号，交易机会锐减——硬 AND 过激进。

## 设计提案（供 P3/Hermes）

1. **范围**：A、B 都限 **bottom 侧**（A 在 bottom×opposing + bottom×neutral 显著；
   top 侧 A 反向）。不要套到 top/支撑 lane。
2. **不要硬 AND 筛**（留 11% 太狠）。鉴于两 gate 正交且各有连续强度，建议**连续 de-weight**：
   - 对 range_vs_avg：权重随过度延伸程度递减（P1a 阈值扫描已显示单调趋势，1.0 是拐点）。
   - 对 ordinal：首测全权重，回踩二测降权（B 的 OOS 证据最强，可给较实的降权）。
   - 组合：两权重相乘（正交 → 乘法合理），而非布尔 AND。这样保留信号量、又把 EV 往
     高质量端倾斜。
3. **与现有 policy weight 的关系**：作为现有 downstream_policies 权重的**乘法调整因子**接入，
   不替换现有 lane 路由；需做联合增量回测（接入前后 portfolio EV / OOS 折）。
4. **置信度 vs 门控**：B（二次入场）OOS 证据强、可入 gate；A（过度延伸）full-sample 强但
   OOS 样本小，建议先作 confidence 特征/软降权，待更多 OOS 样本（含 US 已延至 1999 但
   bottom×opp 受 60min HTF 限止于 ~2016）再考虑硬门控。

## 开放问题（留 Hermes/P3 决）

- de-weight 力度（连续函数形状 / 档位）与 A、B 的相对权重。
- 是否接受 A∧B 的信号量锐减，或只用连续降权保量。
- 联合增量回测口径（在 backtest_full_stack / validate_baselines 上验接入前后无意外漂移）。
- A 的硬门控是否等 OOS 样本充实（HTF 覆盖 / 更多品种）再上。

## 局限

bottom×opp 限 60min HTF 覆盖（~2016 起）；A∧B 的 n=35 小；raw 群非生产门控群；
单 cutoff 1.0 / ordinal==1 二值，未扫连续 de-weight 曲线（P3 设计时再标定）。
脚本 scripts/analyze_combined_gate.py + 3 单测；工件 src/data/review/combined_gate.json（gitignore）。
复现：`python3 scripts/analyze_combined_gate.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/combined_gate.json`。
