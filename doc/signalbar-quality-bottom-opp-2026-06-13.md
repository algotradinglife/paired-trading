# 信号棒质量特征增量 — bottom × h=opposing（2026-06-13）

卡片 t_ecb98b40（PA 假设，来源 doc/pa-aipccode-repo-review-2026-06-13.md 假设 3）。
**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 假设

已验证：swing tight/wick 双独立信号。Brooks（文件16）信号棒质量给出更多同族
特征：收盘近极点（close_pos）、实体/全幅比（body_pct）、棒长 ≤1.5×近期均长
（not_overext）。问题：这些**相对已验证 tight/wick + 现有 bar_quality_bull 是
正交信息还是冗余**。

## 方法

复用 backtest_rr_pool 已验证可交易管道（detect→enrich→**apply_policy 门控**→simulate，
ATR×1.5/1R-2R/MAX_HOLD），限 bottom × h=opposing。win = outcome ∈ {tp1_stop,
tp1_tp2, tp1_max}。信号棒特征无前视（均长窗口取信号前 20 根，严格不含信号 bar）。

policy gate（codex P2）：与 run_symbol 一致剔除被禁用 sublevel（CN2 砍 CN_METAL
`intra_cycle_dea/slope` bottom×opp）；cn_bond 无策略规则 → 放行（与 production 一致）。
n=266（CN_BOND 18 / CN_METAL 125 / US_EQUITY 123），overall win 53.8% / EV +0.103R。

复现：`cd src && uv run python scripts/analyze_signalbar_quality.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/signalbar_quality_bottom_opp.json`
工件：`src/data/review/signalbar_quality_bottom_opp.json`（派生，gitignore 不提交，
命令重生；events 含 pool 标签 + by_pool 内嵌 range_vs_avg 池级切分，池级表自工件可复现）。
脚本 + 5 单测 scripts/analyze_signalbar_quality.py / tests/test_analyze_signalbar_quality.py。

## 冗余度（Pearson 相关）

| Brooks 特征 | vs bar_quality_bull | vs tight | vs wick_lo |
|------------|--------------------|---------|-----------|
| close_pos | **0.757** | — | 0.51 |
| body_pct | 0.374 | — | **−0.73** |
| range_vs_avg | **0.134** | 0.08 | −0.193 |

- close_pos 与 bar_quality_bull 高度相关（后者 = body×close_pos）→ **冗余**。
- body_pct 与 wick_lo 强负相关（大实体=小下影）→ 信息被既有特征覆盖。
- **range_vs_avg（棒长/过度延伸）与所有既有特征相关都低（≤0.19）→ 最正交**。

## 每特征上半 vs 下半（中位数切，win / EV）

| 特征 | hi 半 win / EV | lo 半 win / EV |
|------|---------------|---------------|
| tight_consol（高=不紧） | 0.504 / +0.044 | 0.571 / +0.161 |
| wick_lo | 0.564 / +0.148 | 0.511 / +0.057 |
| bar_quality_bull | 0.526 / +0.029 | 0.549 / +0.176 |
| close_pos | 0.579 / +0.113 | 0.496 / +0.092 |
| body_pct | 0.481 / −0.009 | 0.594 / +0.214 |
| **range_vs_avg** | 0.436 / **−0.111** | 0.639 / **+0.316** |

方向一致：大实体 / 强 bar_quality / **过度延伸**的信号棒前向 EV 反而更差——与朴素
"强信号棒=好"相反，但与 Brooks "过长棒=过度延伸=差" 一致。

## 标志性：range_vs_avg（过度延伸惩罚）

modest-length（≤median）vs over-extended：

| | n | EV(R) |
|--|---|-------|
| lo（不过度延伸） | 133 | **+0.316** |
| hi（过度延伸） | 133 | **−0.111** |

lo−hi EV gap = **+0.427R**；bootstrap95 (10k, seed=42) = **[+0.160, +0.687]**（整段 > 0）；
P(lo>hi) = **0.999**。

池间（方向一致，大池显著）：

| 池 | lo n/EV | hi n/EV | gap |
|----|---------|---------|-----|
| CN_BOND | 9 / +0.833 | 9 / +1.149 | −0.32（n 太小） |
| CN_METAL | 63 / +0.216 | 62 / +0.042 | +0.17 |
| US_EQUITY | 62 / +0.240 | 61 / −0.356 | **+0.60** |

## 长度规则条件增量（bar_quality 上半内）

| | n | win | EV |
|--|---|-----|-----|
| good & not_overext | 100 | 0.540 | +0.036 |
| good & overext | 33 | 0.485 | +0.010 |

ev_diff +0.025R，bootstrap95 [−0.407, +0.459]，P=0.55——条件增量不显著；
standalone range_vs_avg 切分（gap +0.43R 显著）才是干净信号。

## 中性观察（不裁决）

1. close_pos、body_pct 与既有 bar_quality_bull/wick **冗余**，且高值非更优——无正交增量。
2. **range_vs_avg（Brooks 过度延伸/棒长规则）是唯一正交且显著的新特征**：modest-length
   信号棒 EV +0.316 vs over-extended −0.111，gap +0.43R，bootstrap95 整段 >0（P=0.999），
   过 policy gate 后结论稳健（n=312 未门控 → n=266 门控，gap +0.44→+0.43）。
3. 方向呼应 Brooks "过长棒=过度延伸"，但与"强收/大实体=好"相反——增量在"棒长"维度，
   不在"收盘位置/实体"维度。
4. 池间一致（US 最强 +0.60，CN_METAL +0.17，CN_BOND tiny-n 反向）。
5. 局限：6 特征 × 切分无多重检验校正；中位数单点切；复合格 n 小；本群限 h=opposing。
