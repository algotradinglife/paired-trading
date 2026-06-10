---
name: project-recall-first-paradigm
description: 2026-05-25 引入 recall-first 范式 — 用历史 swing labeler 作 ground truth，反向测各 detector 的覆盖率
metadata: 
  node_type: memory
  type: project
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**事实**（2026-05-25 user 提出 + 同日落地）：项目分析视角增加 recall-first 范式 —— 先用 ZigZag-style swing labeler 在历史日线上标注**已实现的可交易波段**，再问"各类 detector 能捕到多大比例"。complement 而非替代 precision-first 的 sweet-spot 分析。

**新工具**：
- `src/engine/labels/swing_labeler.py`：`label_swings(bars, reversal_pct, min_duration_bars)` → list[SwingLabel(head_idx, tail_idx, direction, magnitude_pct, duration_bars)]。只 emit confirmed swings（最后一段 unconfirmed leg 不出）
- `src/scripts/swing_coverage_report.py --pool X`：per (threshold, direction) 算 recall + precision + false-positive，输出 CSV
- 三个 pool CSV: `data/review/swing_coverage_{us,cn,cn_commodity}.csv`
- 报告: `doc/swing-coverage-2026-05-25.md`

**最 brutal 的发现**（在 commit `ttstwuvm 05bf55c7`）：

MACD divergence 的 recall 在所有 pool / 所有 magnitude 阈值上都是 **5-14%**：

| Pool | thr | dir | n_swings | recall | precision |
|---|---|---|---|---|---|
| US | 3% | up | 1041 | 11.1% | 45.9% |
| US | 5% | up | 497 | 8.0% | 19.1% |
| US | 8% | up | 234 | 6.0% | 7.7% |
| US | 10% | up | 144 | 6.2% | 5.5% |
| CN | 3% | up | 624 | 11.1% | 45.5% |
| CN | 3% | down | 622 | 14.0% | 55.9% |

**含义**：之前几个月所有 sweet-spot / OOS / walk-forward 工作都在 **5-11% 的可见机会空间**里精修。**89-95% 的可盈利波段引擎根本看不到** —— 不是信号噪音问题，是信号缺失问题。

**对未来 session 的强制指令**：
1. 任何讨论"提高胜率"的方向，**先问 recall 在哪一档** —— 大概率 recall 才是 binding constraint，不是 precision
2. 新加 detector / feature 时 **必须跑 `swing_coverage_report.py` 看 recall lift**，不只看自身 precision
3. 任何 ship 到 production 的 "sweet spot rule" **应附带其所在子集的 recall**，避免误以为是覆盖式 alpha
4. 真正能涨 alpha 的方向（按 recall 贡献排）：
   - 新 detector：trend line break / S/R rejection / candle pattern (Brooks)
   - 多 TF 共振：但需要先解决 timing infra（参见 [[feedback-multi-tf-sweet-spot-timing-pitfall]]）
   - Z4+ K线特征：可能填补一部分 divergence-missed 的反转
5. 现有 `score_today.py` SWEET_SPOTS 4 条规则 **都是 ~10% 可见空间 + walk-forward fold2-only** —— 双重 caveat，不是 durable production rule
6. 这个范式 complements [[project-initial-sweet-spots-2026-05-25]]，两者一起看才完整：sweet spot = 找精度高的窄信号；recall = 看自己覆盖了多少机会

**Methodology notes**：
- Labeler 是 ground truth，**不能**让 detector 反向影响 swing 定义（循环验证）
- 默认 lookback=10 bars 看 head 之前的 divergence；可调
- Direction 配对：up swing ↔ bottom divergence，down swing ↔ top divergence
- 多 magnitude threshold 都跑（3/5/8/10%），看 recall-magnitude 曲线
- n_signals 必须 dedupe by (sym, bar_idx)，否则 multi-level same-bar 会 understate precision (codex 2026-05-25 review caught)
- precision = NaN only when n_signals==0；有信号没 swing 应 report 0%（codex 2026-05-25）

**Walk-forward roadmap**：当前 coverage 只跑全窗 in-window。下一步该加 `--walk-forward K` 看 recall 在不同时段是否稳定。预期会比 sweet-spot walk-forward 更稳，因为 swing labels 本身不依赖 regime（5% reversal 就是 5% reversal）。

---

**2026-05-25 missed-swing 多 TF 状态诊断**（commit `kuvkzvvz c091109d`）

`scripts/missed_swing_state.py` 对 US 918 个 missed swings 做多 TF MACD 状态快照：

| 盲点 | 占比 | 含义 | 推荐新 detector |
|---|---|---|---|
| 三 TF 全多头时的顶 | 30% down misses | 强势 trend 中每个顶都是 MACD 新高，divergence 不可能 fire | exhaustion (vol spike + reversal K) |
| in_cycle 中段反转 | 77% (all dir) | 缺 prior same-direction extreme，divergence 不能比较 | first-pullback (新 segment 第一回撤) |
| Lower-TF 反向 | 80% up / 83% down | 1h 仍 bearish 时 daily 已 bottom，反之亦然 | B1 对称扩展到 bottom |

**最 cheap 大单**：现有 B1 (top+higher_opposing) 只 cover top，对称扩展到 `bottom+lower_opposing` 可能把 up swing recall 从 8% 翻倍。policy 加一条规则 + 重跑 coverage。

**对未来 session 的指令**：
- 任何"add detector"决策必须**先查 missed_swing_state CSV** 看具体盲点占比，再决定 detector 类型
- 不要做"通用 detector"—— 针对最大盲点桶做最贴合的检测
- B1 对称扩展应该是**下一个 detector PR**（成本最低 + 已有 missed pattern 支撑）
- exhaustion / first-pullback 需要先有 Z4-class K线特征支撑，scope 较大

---

**2026-05-25 三 pool 跨市场对比**（US/CN/CN_COMMODITY missed-swing 诊断完整跑完）

| 指标 | US (918) | CN (467) | CN_COMM (3180) |
|---|---|---|---|
| in_cycle 占比 | 77% | 67% | 69% |
| 三 TF 全多头 down config | **30%** | 12% | **7%** |
| Lower-TF NaN | 0% | **75%** | **86%** |
| Higher-TF NaN | 29% | 18% | **45%** |

**修正的检测器优先级**（按跨市场 ROI 重排，**覆盖前面的 B1-symmetric 单一推荐**）：

1. **first-pullback detector**：cycle-early reversal，**跨市场 67-77% 盲点**，universal 高 ROI
2. **CN intraday data 扩展**：用 TqSdk 拉更长 60/15min 历史，否则 CN multi-TF 任何检测都缺 75-86% 数据
3. B1-symmetric：US 上高 ROI；CN 上因 75-86% lower NaN，覆盖只 15-25% 信号 → 优先级降为 US-only
4. exhaustion detector：US 30% / CN 7-12%，**仅做 US 不要做 CN**

**关键洞察**：
- 强势趋势顶是 **US-specific** (30% vs CN 7-12%)，CN 期货更 mean-revert，trend-following exhaustion 不是 CN 主要模式
- in_cycle 盲点 (67-77%) 在三 pool 上稳定 → MACD divergence 需要 prior reference 的硬性约束跨市场都成立
- Daily DIF 错向 (60-70%) 也稳定 → 反转往往发生在 MACD 还没穿零轴之前

**强制约束**：任何打算用 multi-TF lookup 的 CN detector 必须**先**报告 lower/higher NaN 比例。如果 >50% NaN，detector 实际只在小子集上验证，不能 ship 作 general CN rule。

---

**🚨 2026-05-26 修正 — "CN trend exhaustion 占比低" 之前是 data 假象**

用 qveris 拉了 CN 14y 60min 后（commit pending）重跑 CN missed_swing_state.py，三 TF 配置分布**完全变样**：

| 配置 | 60min 浅 (旧 TqSdk) | 60min 深 (新 qveris 14y) |
|---|---|---|
| up "三 TF 全空头" | 10% | **36%** ⬆ |
| down "三 TF 全多头" | 12% | **35%** ⬆ |

之前"CN 期货 mean-revert，trend-following exhaustion 不是主要模式"的结论是 **higher-TF NaN 太多 (75-86%) 导致的数据假象**。真实情况：**CN 和 US 在 missed swing structure 上几乎一致**（US 30% / CN 36% 强势 trend exhaustion）。

**修正后的 detector 跨市场优先级**：
1. **first-pullback**（67-77% 跨市场盲点）—— 仍然第一
2. **exhaustion detector (climax + reversal K)** —— 从 "US-only" 升级到 **universal**（跨 US/CN 都~30% 盲点占比）
3. **B1-symmetric**（bottom + lower=lagging）—— 等 CN 15min 也补完后再评估，CN 这边 lower NaN 仍未解决
4. 其他

**Methodology 教训**：在数据覆盖度不足时下"市场特性"结论极不可靠。任何 cross-market 结论都必须**先验证数据完整度**。这条尤其适用于 multi-TF 分析。

**待 15min backfill 完后再验证一次**：lower-TF 也补 14y 后，CN missed swing 的 lower 维度是否也呈现新模式。如果是，可能还有更多隐藏共性。
