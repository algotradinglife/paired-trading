# 二次入场分组 EV 验证 — bottom × h=opposing（2026-06-13）

卡片 t_cf7cc3b8（PA 假设，来源 doc/pa-aipccode-repo-review-2026-06-13.md 假设 2）。
**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 假设

Brooks（AipcCode/pa 文件15）：第一次反转信号胜率 35-40%，第二次（双底二测 /
回踩前低）55-60%——即"二测应优于首测"。在我们已验证的 **bottom × h=opposing**
信号群上检验。

## 方法

复用已验证管道（不 fork backtest_rr_pool）：detect_signals → enrich_with_higher/
lower_tf → simulate_trade（ATR×1.5 止损 + 1R/2R 缩仓 + MAX_HOLD=20），EV=mean(realized_r)。
口径：原始 bottom×opposing 群（未过 downstream policy gate，最大化样本量、隔离回踩效应）。

唯一新增：无前视测试序数分类器（scripts/analyze_second_entry.py，7 单测）：
- **当前测试 = 信号 bar 自身的低**（codex P2：信号常在回踩低当根触发，该低尚未能
  确认为 swing；以"最近已确认 swing low"为锚会误判）。锚=bars.low[signal_idx]，
  再数信号前已确认的同位 swing low。
- 同位判定 **ATR 相对容差**（|前低−ref_low| ≤ 1.0×ATR）+ **严格介于两低之间**的中间
  反弹 ≥ 1.5×ATR（codex P2：反弹窗口须排除信号 bar 自身高点，否则 outside/反转当根
  会伪造"反弹"——这正是初版的致命 bug，见下"修复改写结论"）。
- ordinal = 1 + 满足条件的更早同位低数；first=1，second+≥2

复现：`cd src && uv run python scripts/analyze_second_entry.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/second_entry_bottom_opp.json`
工件：`src/data/review/second_entry_bottom_opp.json`（派生，gitignore 不提交，命令重生）。

## 头条（pooled，n=315）

| 组 | n | EV(R) | TP1 命中 | full_stop | tp1_tp2(+1.5R) |
|----|---|-------|---------|-----------|----------------|
| first（ordinal 1） | 84 | **+0.380** | 64.3% | 35.7% | 41.7% |
| second+（ordinal ≥2） | 231 | **−0.037** | 48.1% | 51.1% | 26.4% |

EV gap (2nd+ − first) = **−0.417R**；bootstrap95 (10k, seed=42) = **[−0.690, −0.139]**
（整段 < 0）；P(gap>0) = **0.002**。

**结论方向：首测 EV 显著优于二测，与 Brooks "二测更优" 相反。** 首测同时在胜率
（64.3% vs 48.1%）与右尾（tp1_tp2 41.7% vs 26.4%）两端都占优。

ordinal 直方图：{1:84, 2:98, 3:72, 4:25, 5:26, 6:4, 7:5, 8:1}。

## 池间（方向一致，2/3 显著偏首测）

| 池 | first n / EV | 2nd+ n / EV | 方向 |
|----|-------------|-------------|------|
| CN_BOND | 11 / +0.940 | 7 / +1.071 | 大致持平（n 极小，略偏二测） |
| CN_METAL | 48 / +0.349 | 125 / −0.027 | **首测显著更优** |
| US_EQUITY | 25 / +0.193 | 99 / −0.128 | **首测显著更优** |

pooled 首测优势由 CN_METAL + US_EQUITY 主导；CN_BOND n 太小（11/7）不构成反证。

## ⚠ 修复改写结论（透明记录）

初版分类器的"中间反弹"窗口**误含信号 bar 自身的高点**。bottom×opposing 信号常
落在强反转/外包当根（高点很大），该高点伪造出"反弹"，把大量**强势首测**误分进
second+ 组。初版（buggy）因此得出相反且不显著的结论：

| 口径 | first EV | 2nd+ EV | gap | P(gap>0) |
|------|----------|---------|-----|----------|
| 初版（含信号 bar 高，**错**） | −0.010 | +0.111 | +0.121 | 0.82（似支持 Brooks） |
| 修复（严格介于两低，**对**） | +0.380 | −0.037 | **−0.417** | **0.002（反 Brooks，显著）** |

教训：reversal-bar 信号的"二次入场"分类对"反弹是否含触发当根"极度敏感；端点处理
错误会系统性地把首测漂移成二测。codex P2 抓到此点后结论从"弱支持"翻转为"显著反对"。

## 中性观察（不裁决）

1. 修复后 pooled：首测 EV +0.380 显著优于二测 −0.037，gap −0.42R，bootstrap95 整段 <0。
2. 机制：首测在胜率与右尾两端均占优——强反转当根的"首次"capitulation 低质量高于
   被反复回踩侵蚀的同位低（distribution）。
3. 池间方向一致：CN_METAL / US_EQUITY 显著偏首测；CN_BOND n 太小。
4. 样本：n=315（first 84 / 2nd+ 231）。
5. 参数敏感性（tol_atr / bounce_atr / lookback）未扫，单点口径；本群限 h=opposing。
