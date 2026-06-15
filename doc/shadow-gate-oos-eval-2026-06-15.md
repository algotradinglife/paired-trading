# 影子信号棒质量闸门 — OOS / 部署评估（2026-06-15）

评估对象：`score_today` 中 shadow 落地的 advisory 信号棒质量闸门（commit `057c81f`, t_ffffa8fd），
即 `_signal_bar_quality()` 的 `double_strong` 二元标志。源发现见
[[signal-bar-quality-hardening-2026-06-15]]（样本内中位分层，双强交集 +1.28R）。

工具 `scripts/eval_shadow_gate_oos.py`（复用 canonical `evaluate()` 的 EV，**直接 import score_today
的已发布闸门逻辑**避免漂移；按 id join split/ts_utc/features_det）。**机械统计，研究性，不打 PASS/FAIL。**
复现：`cd src && ./.venv/bin/python scripts/eval_shadow_gate_oos.py --corpus data/review/pa_dataset_rbcuau.labeled.jsonl`

## 两个问题（doc 源 §局限&下一步 (a)/(d) 指定）
- **Q1 部署保真**：发布用**固定阈值** `body_frac>=0.5`、`close_pos>=0.66`；样本内发现来自**逐 cohort 中位分层**
  （body_frac 中位≈0.8、close_pos 中位≈1.0）。固定阈值的 `double_strong` 还能复现 EV 分层吗？
- **Q2 样本外**：在 `train` 行上推导分层规则、冻结、应用到留出 `test`，合取效应能否存活？

## 结果 Q1 — 部署闸门**退化（结构性 no-op）** ⚠️
| 阈值 | body_frac 通过 | close_pos 通过 | 双强(BOTH) 通过 |
|---|---|---|---|
| **发布固定 0.5 / 0.66** | **100.0%** | **100.0%** | **100.0%** |
| 样本内中位 0.8 / 1.0 | 44.7% | 49.0% | 32.1% |

- 全 3512 候选：**最小 body_frac = 0.500、最小 close_pos = 0.667**——发布阈值正好落在特征分布的**地板**上。
- n=88 已结突破做多population：`double_strong` 通过率 **88/88 = 100%**，**无法对总体分区** → EV 对比不存在。
- 根因：**突破候选生成器本身已强制该几何**（突破信号棒按定义实体强、收在上 1/3），影子闸门
  **重测了一个候选过滤已保证的条件**，对突破候选永远不会判 False。
- 反观样本内**中位分层**（0.8 / 1.0）确实分区（44.7/49/32.1%），故源研究能测到 +1.28R 分层；
  发布把阈值设到了分布地板 → 丢失全部分辨力。

## 结果 Q2 — 语料内**无样本外可验证数据**
- 88 条已结突破做多 trade **全部落在 `split=train`**；feature-bearing 已结 trade 在 val/test = **0/0**。
- 语料 split 计数（全候选）train/val/test = 2445/536/531，但 val/test 候选在本 eval 中**不产生已结突破做多 trade**。
- 结论：本语料无法做语料内时序/随机 OOS。合取效应仍是**纯样本内**（n=88，小 cell A_only/B_only 各 n=12）。

## 结论（评估裁决）
1. **影子闸门当前形态不可晋升 active sizing**——不是因为发现错，而是因为**发布阈值退化**：双强标志对每一条
   突破候选恒为 True，晋升后等价于"全仓加权" = 无闸门。
2. **仍无 OOS 证据**。源发现保持样本内、小 cell 状态。
3. **修复路径（两步，须先于任何 active sizing）**：
   - (a) **重设阈值为 cohort-relative / 中位对齐**（如 body_frac≥cohort 中位 ~0.8、close_pos≥~1.0），
     使 `double_strong` 真正二分总体。固定绝对阈值天然不可移植（[[regime-gate-not-portable]]）。
   - (b) **取得 OOS 数据**再验证合取：要么 score_today live 前向 shadow 记录累积，要么向 data-engineer
     建卡补新品种/时段的带 features_det 突破语料。
4. **影子字段保留无害**（不入仓位），但当前对前向证据**零信息量**（恒 True）——修阈值前不要据此累积"OOS 证据"。

## 局限
- 仅评估了已发布 long 闸门在 rb+cu+au 突破语料上的行为；short 边、其它 lane（cn_bond/vflush/context 等
  9 lane 均挂了该字段）未单独取数验证，但退化根因（阈值=分布地板 + 候选器已保证几何）跨 lane 同构，预计一致。
- `features_det` body_frac/close_pos 经四舍五入；synthetic-bar 重构 skipped_recon=0（全部保真路由生产函数）。

工件 `data/review/shadow_gate_oos.json`（gitignore）。
相关：[[signal-bar-quality-hardening-2026-06-15]]、[[spec001-ev-eval]]、[[regime-gate-not-portable]]。
