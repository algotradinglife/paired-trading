# 粗市场状态门控 EV 验证 — bottom × h=opposing（2026-06-13）

卡片 t_aeb3cc75（PA 假设，来源 doc/pa-aipccode-repo-review-2026-06-13.md）。
**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 假设

Brooks 把市场切成 8 态（spike / channel / range 等）并断言不同态下反转信号的胜率不同。
本卡把 8 态收敛成 4 个**可编程**粗态——spike / tight_channel / normal_channel / range——
检验已验证的 **bottom × h=opposing** 信号群的 EV 是否随信号 bar 所处粗态而变。

## 方法

复用已验证管道（不 fork backtest_rr_pool）：detect_signals → enrich_with_higher/
lower_tf → simulate_trade（ATR×1.5 止损 + 1R/2R 缩仓 + MAX_HOLD=20），EV=mean(realized_r)，
win_rate=frac(realized_r>0)。口径：原始 bottom×opposing 群（未过 downstream policy gate，
最大化样本量；--apply-policy 可切生产门控群）。

新增：无前视粗状态分类器（scripts/analyze_state_gate.py，13 单测）。每个信号 bar 由
**仅 ≤ 信号 bar** 的 OHLC 派生特征确定（趋势连数、bar 重叠、EMA 距离、swing 腿重叠
全部排除未来 bar，端点含/不含逐项校验）：

- **consec_dir**：信号 bar 结尾的同向趋势 bar 连数（bull/bear 取信号 bar 自身方向）
- **overlap_ratio**：近 6 根 bar 相邻对的平均区间重叠率（overlap/union）；高=横盘/通道
- **ema_dist_atr**：|close − EMA20| / ATR（**ATR 相对，非固定价格 %**——债期整段波动
  <2%，固定 % 阈值在债上必然全判 range）
- **leg_overlap**：近两条**已确认** swing 腿（swing_idx+n ≤ idx）价位带重叠率；腿叠=区间

收敛规则（按优先级先到先得）：
1. **spike** — consec_dir ≥ 3 且 ema_dist_atr ≥ 1.5 且 overlap_ratio ≤ 0.35（强动量爆发）
2. **range** — overlap_ratio ≥ 0.55 且 ema_dist_atr ≤ 1.0 且 leg_overlap ≥ 0.30（横盘）
3. **tight_channel** — consec_dir ≥ 2 且 overlap_ratio ≥ 0.55（缓坡窄通道）
4. **normal_channel** — 其余（兜底）

复现：`cd src && uv run python scripts/analyze_state_gate.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/state_gate_bottom_opp.json`
工件：`src/data/review/state_gate_bottom_opp.json`（派生，gitignore 不提交，命令重生）。

## 头条（pooled，n=315）

| 状态 | n | EV(R) | win_rate | full_stop |
|------|---|-------|----------|-----------|
| spike | 29 | +0.149 | 44.8% | 44.8% |
| tight_channel | 8 | +0.200 | 37.5% | 25.0% |
| normal_channel | 277 | +0.059 | 40.1% | 48.0% |
| range | 1 | +1.040 | 100% | 0.0% |

状态直方图：{spike:29, tight_channel:8, normal_channel:277, range:1}。

best-vs-rest（best=tight_channel，pooled 中 n≥5 且 EV 最高者）：
gap_point = EV(tight_channel) − EV(rest) = **+0.129R**；
bootstrap95 (10k, seed=42) = **[−0.484, +0.794]**（**跨 0**）；ci_excludes_zero = False。

## 池间（regime not portable，分池报告）

| 池 | n | spike (n/EV) | tight_ch (n/EV) | normal_ch (n/EV) | range (n/EV) | best-vs-rest gap / ci95 |
|----|---|--------------|------------------|-------------------|--------------|--------------------------|
| CN_BOND | 18 | 2 / +1.171 | 0 / — | 16 / +0.969 | 0 / — | n/a（best 或 rest 组 n<5） |
| CN_METAL | 173 | 16 / +0.281 | 4 / −0.350 | 152 / +0.061 | 1 / +1.040 | spike: +0.225 / [−0.364, +0.802]（跨 0） |
| US_EQUITY | 124 | 11 / −0.230 | 4 / +0.750 | 109 / −0.076 | 0 / — | normal_ch: −0.108 / [−0.693, +0.463]（跨 0） |

## 中性观察（不裁决）

1. **状态极度失衡**：normal_channel 占 277/315 = 88%。tight_channel（n=8）与 range（n=1）
   在 pooled 仍处/低于 n<5 可解释下限附近；分池后 tight_channel/range 在每个池都 n≤4。
   该粗分类器在 bottom×opposing 群上**几乎不激活非兜底态**——多数底部反转信号当根既
   不满足 spike（强连阳 + 远离 EMA + 低重叠），也不满足 range（高重叠 + 贴 EMA + 腿叠）。
2. **pooled 无 EV 分离**：最高态 tight_channel（n=8）与 rest EV gap 仅 +0.129R，
   bootstrap95 整段跨 0；spike 与 normal_channel 也几乎相等（+0.149 vs +0.059）。
3. **池间方向异质（不可移植）**：spike 在 CN_METAL 为 +0.281（正），在 US_EQUITY
   却为 −0.230（最低态）；同一 spike 定义在两池 EV 符号相反。tight_channel 亦反向
   （CN_METAL −0.350 vs US_EQUITY +0.750，各 n=4）。CN_BOND 两态均强正但 n 太小
   （2/16）。任何池上的 best-vs-rest CI 都跨 0。
4. range pooled n=1（+1.04）——纯噪声级样本，不可解读。
5. 样本：n=315（与 second-entry 卡同一 bottom×opposing 群），spike 29 / tight_ch 8 /
   normal_ch 277 / range 1。
6. 参数（阈值、TREND_WINDOW、EMA_PERIOD、swing_n）未扫，单点口径；本群限 h=opposing、
   未过 policy gate。

## ⚠ 阻塞声明（透明记录）

非兜底状态稀疏（tight_channel pooled n=8，range pooled n=1；分池后均 n≤4）。
pooled best-vs-rest 与每个池的 best-vs-rest bootstrap CI **全部跨 0**。在当前阈值下，
该粗状态门控对 bottom×opposing 群**未显示可统计区分的 EV 分离**，且唯一在两池都
n≥10 的 spike 态在 CN_METAL（+0.281）与 US_EQUITY（−0.230）上 EV 符号相反（不可移植）。
机械统计如上，不下 PASS/FAIL。
