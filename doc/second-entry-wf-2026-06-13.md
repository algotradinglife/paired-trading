# Second-entry 序数梯度 + 嵌套 walk-forward（t_c8aad725 / P1b，2026-06-13）

> 本文件只列机械统计，不打 PASS/FAIL。

## 背景

t_cf7cc3b8 在 **bottom × higher_relation=opposing** 信号群上发现"首测（first test）>
二测+（2nd+ retest）"：gap −0.42R、P=0.002。但该发现只过了**单次 bootstrap，没有
walk-forward**。本次给它补上 `range_vs_avg`（t_6c3f043a）同款 out-of-sample 严格度：

- 序数梯度（first / 2nd+ / 3rd+）EV + win-rate + n，pooled + by-pool + bootstrap。
- **嵌套 train-select-test walk-forward**：gate = 保留 `ordinal <= cutoff`（即 de-weight
  二测+），cutoff 只在 IS 上选，OOS 仅评估（无前视调参）。
- 固定时间序 K=3 折：每折 first-vs-2nd+ EV gap（时间稳定性）。

**复用**：`scripts/analyze_second_entry.py` 的 `run_symbol_second_entry`（含无前视
`test_ordinal` 分类器：锚定信号 bar，只数信号前已确认的 swing low，ATR 相对容差 +
中间反弹要求；详见该脚本 docstring）。本脚本不重新派生分类器，仅新增聚合 / 嵌套 WF。

口径：`bottom × opposing` 原始群（未过 downstream policy gate），最大化样本、隔离回踩
效应。参数 `swing_n=3, tol_atr=1.0, bounce_atr=1.5, lookback=60, stop_mult=1.5`。
样本期 2021-01-28 → 2026-06-09，**n = 314 事件**。

## 复现命令

```bash
# 全池（CN_METAL / US_EQUITY 的 15min 全序富化是主成本，整跑可能 >600s 超时）：
cd src && uv run python scripts/analyze_second_entry_wf.py \
    --pools CN_BOND CN_METAL US_EQUITY --out data/review/second_entry_wf.json
# 无 uv 环境：
cd src && python3 scripts/analyze_second_entry_wf.py --pools ... --out ...
```

**有界复现路径（推荐）**：逐池跑（`--pools CN_BOND` ~5s、`--pools CN_METAL` /
`--pools US_EQUITY` 各 ~5min），再把各池 `events` 合并、对合并行重跑 `build_report`
即得本文件的全池数字。本次 JSON 即按此法生成（`params.reproduction_note` 已记录）。

机械结果 JSON：`src/data/review/second_entry_wf.json`（**gitignored**，不入库）。
单元测试：`src/tests/test_analyze_second_entry_wf.py`。

序数直方图：`{1:85, 2:97, 3:71, 4:25, 5:26, 6:4, 7:5, 8:1}`。

## (a) 序数梯度（EV / win-rate / n）

### Pooled

| 组 | n | EV (R) | win-rate |
|---|---|---|---|
| first (ord 1) | 85 | **+0.3638** | 0.6353 |
| 2nd+ (ord ≥2) | 229 | −0.0285 | 0.4847 |
| 3rd+ (ord ≥3) | 132 | +0.0603 | 0.4924 |

- first − 2nd+ gap = **+0.3923 R**（first 占优）。
- first-vs-2nd+ bootstrap（10k, seed=42）：gap +0.3923，**95% CI [+0.111, +0.668]**，
  P(gap>0) = **0.9977**。CI 不含 0，方向一致为 first 占优。
- 注：3rd+（ord≥3）EV（+0.06）反而高于 2nd+（−0.03）——梯度**非单调**，差主要集中在
  ord=2（恰好二测）这一档，不是"越多次回踩越差"的单调结构。

### By-pool（regime 不可移植，单列）

| 池 | first n / EV | 2nd+ n / EV | first−2nd+ gap | bootstrap P(gap>0) / CI95 |
|---|---|---|---|---|
| CN_BOND | 11 / +0.9402 | 7 / +1.0714 | **−0.1313** | 0.3699 / [−0.833, +0.583] |
| CN_METAL | 49 / +0.3214 | 124 / −0.0191 | +0.3405 | 0.9613 / [−0.035, +0.703] |
| US_EQUITY | 25 / +0.1932 | 98 / −0.1189 | +0.3122 | 0.8917 / [−0.193, +0.824] |

- **CN_BOND 方向相反**：first<2nd+（gap −0.13），但 n 极小（first 11 / 2nd+ 7），
  bootstrap P=0.37、CI 跨 0，方向不可凭。国债两组 EV 都很高（>+0.9R），是已知的强 regime。
- CN_METAL / US_EQUITY 方向均为 first>2nd+，但单池 bootstrap CI 都跨 0（P 0.96 / 0.89）：
  方向一致、单池显著性不足。pooled 的显著性主要由这两池叠加而来。

## (b) 嵌套 walk-forward（IS 选 gate → OOS 评估）

gate = 保留 `ordinal <= cutoff`（de-weight 2nd+）。IS_CUTOFF_DATE = `2025-06-30`
（IS ≤ 该日 < OOS）。在 IS 上扫 `ORDINAL_GRID=(1,2,3)` 选 lane_improvement 最大的 cutoff。

| 阶段 | n | full EV | IS lane_improvement by cutoff |
|---|---|---|---|
| IS (≤2025-06-30) | 244 | +0.1644 | c=1: **+0.1673** / c=2: −0.0637 / c=3: −0.0702 |

- **IS 选出 cutoff = 1**（即"只保留 first-tests"），IS lane_improvement = +0.1673。
  c=2/c=3 的 improvement 为负 → IS 上确认收紧到 first 才提升，与发现方向一致。

| OOS 评估（cutoff=1，无前视） | 值 |
|---|---|
| OOS n | 70 |
| OOS full EV | −0.2245 |
| OOS kept (first) n / EV | 12 / **+0.5589** |
| OOS dropped (2nd+) n / EV | 58 / −0.3866 |
| **OOS lane_improvement @ selected cutoff** | **+0.7834 R** |
| OOS kept-vs-dropped bootstrap | gap +0.9455, 95% CI **[+0.296, +1.548]**, P(gap>0) **0.9968** |

- IS 上选出的 gate（只留 first）在 **OOS 上仍带正提升**（+0.78R），且 kept-vs-dropped
  bootstrap CI 不含 0。**方向在样本外延续**。
- 但 **OOS first 样本极小（n=12）**：这是 12 个事件的 EV，单独看显著性弱——
  bootstrap 的强 P 来自 kept 与 dropped 的分离度，而非 kept 组本身的大样本。报方向 ≠ 报
  单组个体显著性（与 analyze_range_gate 同口径处理）。

## (c) 固定时间序 K=3 折（first-vs-2nd+ gap，时间稳定性）

| 折 | 日期区间 | n | first n/EV | 2nd+ n/EV | gap |
|---|---|---|---|---|---|
| F1 | 2021-01-28 → 2022-11-29 | 104 | 23 / +0.2423 | 81 / +0.2180 | +0.024 |
| F2 | 2022-12-06 → 2025-03-12 | 105 | 39 / +0.5049 | 66 / −0.0846 | +0.589 |
| F3 | 2025-03-19 → 2026-06-09 | 105 | 23 / +0.2461 | 82 / −0.2269 | +0.473 |

IS/OOS 切分（同 2025-06-30）：

| 段 | n | first n/EV | 2nd+ n/EV | gap |
|---|---|---|---|---|
| IS | 244 | 73 / +0.3317 | 171 / +0.0930 | +0.239 |
| OOS | 70 | 12 / +0.5589 | 58 / −0.3866 | +0.945 |

- **三折 gap 全为正**（+0.02 / +0.59 / +0.47），方向稳定。
- F1（最早期）gap 几乎为 0（2nd+ 当时也盈利 +0.22）——早期 regime 下二测惩罚不明显；
  edge 主要在 F2/F3。这与 (b) 的 OOS（最近期）放大 gap 一致：近年二测惩罚更强。

## Bonferroni 注记

序数 cutoff 扫描含 `len(ORDINAL_GRID)=3` 次比较。pooled first-vs-2nd+ 的单点
P(gap>0)=0.9977（即单尾 p≈0.0023）在按 3× 校正后 ≈ 0.0069，仍 < 0.05。嵌套 WF 的
cutoff 是在 IS 上从 3 个候选里选的，OOS 评估本身不引入额外多重比较（cutoff 已锁定）。

## 中性证据汇总：能否做成"回踩二测 de-weight gate"

机械事实（不打裁决）：

1. **pooled 方向 + 显著性都站得住**：first>2nd+ gap +0.39R，bootstrap CI [+0.11, +0.67]
   不含 0，过 Bonferroni 3× 校正。
2. **样本外延续**：IS 自选出"只留 first"为最佳 gate，该 gate 在 OOS 仍带 +0.78R 提升，
   kept-vs-dropped CI [+0.30, +1.55] 不含 0。方向在未来未反转。
3. **时间稳定**：三折 gap 全正，edge 在 F2/F3（近年）更强。
4. **限制条件（必须并列读）**：
   - **OOS first 仅 12 事件**——OOS 提升是小样本，强 P 来自组间分离而非 kept 组体量。
   - **CN_BOND 方向相反**（first<2nd+），n 极小不可凭，但提示该 gate 在国债 regime 不适用；
     by-pool 单池 CI 全跨 0，pooled 显著性靠 CN_METAL+US_EQUITY 叠加。
   - **梯度非单调**：3rd+ EV（+0.06）> 2nd+（−0.03），惩罚集中在 ord=2 档，不是"越多次越差"。
   - 上述数字基于 `bottom×opposing` 原始群（未过 policy gate）；过生产门控后 n 更小，
     需另跑 `--apply-policy` 才能确认 gate 在生产口径上的表现。

综合：若做成 de-weight gate，证据支持"对 CN_METAL / US_EQUITY 的 ord=2 二测降权、保留
first"，但 **CN_BOND 应排除**（regime 不可移植），且 OOS 个体样本小、需后续累积更多
样本与生产口径（`--apply-policy`）复核。以上仅为机械统计，最终取舍交 reviewer。
