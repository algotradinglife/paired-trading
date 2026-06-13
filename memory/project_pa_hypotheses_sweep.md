---
name: pa-hypotheses-sweep-2026-06-13
description: AipcCode/pa 仓库引出的 4 个 Brooks 假设在 bottom×opposing 群上的机械验证结果：1 个显著正交、1 个反 Brooks、2 个 null
metadata: 
  node_type: memory
  type: project
  originSessionId: bfb52110-df3c-4deb-b492-f1526868a5c8
---

2026-06-13：基于 AipcCode/pa（见 [[pa-aipccode-repo-review]]）的 Brooks 方法论，在
已验证 bottom×opposing 群（CN_BOND/CN_METAL/US_EQUITY）上跑了 4 个机械假设验证
（卡 t_cf7cc3b8 / t_ecb98b40 / t_aeb3cc75 / t_26f5a08c，均只统计不裁决，已交 reviewer）。
复用 backtest_rr_pool 管道，bootstrap 10k/seed=42。结果：

1. **二次入场（t_cf7cc3b8，doc/second-entry-bottom-opp-2026-06-13）**：**反 Brooks 且显著**。
   首测 EV +0.380 vs 二测 −0.037，gap −0.417R，CI[−0.690,−0.139] 整段<0，P=0.002。
   即 bottom×opp 上**首测显著优于回踩二测**（与 Brooks "二测更优" 相反）。
   ⚠ 教训：初版反弹窗口误含信号 reversal 当根高点 → 结论从"弱支持"翻转为"显著反对"；
   reversal-bar 二次入场分类对端点处理极敏感。

2. **信号棒质量（t_ecb98b40，doc/signalbar-quality-bottom-opp-2026-06-13）**：**唯一正向发现**。
   Brooks 的 close_pos/body_pct 与现有 bar_quality_bull 冗余（corr 0.76/−0.73）；
   **range_vs_avg（过度延伸/棒长 ≤1.5× 规则）正交（corr≤0.19）且显著**——modest-length 棒
   EV +0.316 vs over-extended −0.111，gap +0.43R，CI[+0.160,+0.687] 整段>0，过 policy gate 稳健。
   池间一致（US +0.60/CN_METAL +0.17/CN_BOND tiny-n）。**值得纳入 confidence/gate 的是"棒长"维度。**
   **后续验证（t_6c3f043a，doc/range-gate-validation-2026-06-13）**：阈值扫描**紧切点 1.0 主导但
   非严格单调**（1.75<2.0、尾部噪声），强 edge 在 **cutoff 1.0（≈中位数，非 Brooks 1.5×）**——
   full-sample gate@1.0 kept +0.392 vs dropped −0.092，gap +0.484R CI[+0.217,+0.745] P=0.9998（显著）。
   时间外：固定 1.0 各折 IS+0.386/OOS+0.091/F3+0.323 全正，嵌套 train-select-test（IS 选 1.0）
   OOS improve +0.091 **方向一致为正但 OOS 子样本(n=57)的 gap CI 跨 0(P=0.75)、不单独显著**。
   代价：cutoff 1.0 砍 ~60% 信号。**productionize 建议：1.0~1.25 作 de-weight 而非硬砍**（待 Hermes）。

3. **状态 gate（t_aeb3cc75，doc/state-gate-bottom-opp-2026-06-13）**：**null + 状态失衡**。
   粗态分类器 88% 落兜底 normal_channel，best-vs-rest gap +0.129R CI 跨 0；spike 在
   CN_METAL +0.28 vs US −0.23 符号相反（不可移植）。当前阈值无可用分离，需重调阈值才能复看。

4. **ioi detector（t_26f5a08c，doc/ioi-combos-2026-06-13）**：**偏 null**。ioi 稀有(~4/1000)，
   direction-free 前向漂移最强但方向化 sim CI 三池全跨 0；inside/outside 高频近零信息；
   ioi∩bottom×opp=0。无明确 edge，样本饥饿，ioi 值得更大样本复看。

**净结论**：Brooks 民间断言不能照搬到我们的池——"二测更优"在 bottom×opp 上反向，
"强信号棒=好"被证冗余，唯一稳健正交增量是**过度延伸/棒长惩罚**。
方法学教训：固定 % 阈值对债期失效（用 ATR 相对）；窗口端点/暖机期处理错误会系统性
偏移分类（codex 在整合阶段抓出多个翻转级 P2）。相关：[[validated-bottom-setup]]、
[[regime-gate-not-portable]]。
