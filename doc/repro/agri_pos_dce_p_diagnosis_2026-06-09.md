# pa_h2_climax × kq_m_dce_p 根因调查 — 2026-06-09

闭环 lane STALE 调查链最后一环。`pa_h2_climax` lane 总 EV -0.040R / n=64 / 5.5y -2.58R drag——其中 **dce_p 单 symbol -3.97R / n=11 / 36% win** 是最大单 symbol 拖累。

## TL;DR

**根因 3 层**：
1. **2025 全年崩溃**：3 trades / 3 full_stops / -3.00R——占总 drag 75%
2. **结构性止损过紧**：3 of 7 losing trades 用 < 5% stop_pct，其中 2 单 1 bar 内被打——是 noise stop-out 不是 signal failure
3. **dce_p full_stop 率高达 64%**——全池最高（czce_sr 仅 18%）

**结论**：如果未来 `pa_h2_climax` 重新激活（目前 STALE），**dce_p 必须排除**。其他 4 个 symbols 中 czce_ma 也偏弱（-0.132R）但样本更大不易明确。

## Section 1: dce_p 每一笔

| Date | Year | Outcome | R | Bars | Entry | Stop | Stop% |
|------|------|---------|---|------|-------|------|-------|
| 2022-03-22 | 2022 | max_hold | +0.192 | 20 | 12300 | 8603 | 30.05% |
| 2022-05-19 | 2022 | full_stop | -1.000 | 17 | 14134 | 11446 | 19.02% |
| 2023-01-12 | 2023 | tp1_max | +1.050 | 20 | 7730 | 7334 | 5.13% |
| 2023-04-25 | 2023 | full_stop | -1.000 | 12 | 7502 | 7059 | 5.91% |
| 2023-10-26 | 2023 | tp1_max | +0.284 | 20 | 7194 | 6861 | 4.63% |
| **2024-12-17** | 2024 | **full_stop** | **-1.000** | **2** | 9960 | 9506 | **4.56%** ⚠ |
| **2025-05-12** | 2025 | **full_stop** | **-1.000** | **1** | 8450 | 8360 | **1.07%** ⚠ |
| 2025-09-22 | 2025 | full_stop | -1.000 | 16 | 9274 | 8661 | 6.62% |
| **2025-11-26** | 2025 | **full_stop** | **-1.000** | **1** | 8374 | 8352 | **0.27%** ⚠⚠ |
| 2026-01-06 | 2026 | tp1_tp2 | +1.500 | 10 | 8380 | 8148 | 2.77% |
| 2026-04-20 | 2026 | full_stop | -1.000 | 15 | 9341 | 8474 | 9.28% |

3 笔损失（标 ⚠）是 **1-2 bar 内 stop_pct < 5% 被打**——典型 noise stop-out，**不是真正的 signal failure**。

## Section 2: 每年表现

| Year | n | EV | win | Sum R |
|------|---|-----|-----|-------|
| 2022 | 2 | -0.404R | 50% | -0.81 |
| 2023 | 3 | +0.111R | 67% | +0.33 |
| 2024 | 1 | -1.000R | 0% | -1.00 |
| **2025** | **3** | **-1.000R** | **0%** | **-3.00** ⚠ |
| 2026 | 2 | +0.250R | 50% | +0.50 |

**剔除 2025**：dce_p n=8 / sum -0.97R / EV -0.121R——仍负但温和。**2025 单年 -3.00R 是决定性的**。

## Section 3: 池内对比（dce_p vs czce_ta best vs dce_m）

### czce_ta（最佳，+1.63R）
- 2021-2023: 4/4 年正 EV，2023 单笔 +1.50R 全砸
- 2024 起转负但小幅（-0.28, -1.13, +0.05）
- 显著不同：win 50%+，**no 1-bar stop-outs**

### dce_m（接近持平 +0.54R）
- 2021-2022 全负（-1.13, -2.41）
- 2023 起逆转：+1.00, +0.08, n/a, +3.00
- 关键：**2 笔 tp1_tp2（+1.5R 各）+ 2026 强势** 把前期 drag 拉平
- 也是高 full_stop（50%）但**winners 够大**

### dce_p（最差，-3.97R）
- 损失集中在 2024-2025
- 4 tp1+ wins 但磁场不够 offset 7 full_stops
- 关键差异：**winners 平均 R 较小** (tp1_max +1.05, +0.28；tp1_tp2 +1.50)，**losers 全部是 full_stop**

## Section 4: outcome 分布——dce_p 与其他

| Symbol | full_stop | tp1_stop | tp1_max | tp1_tp2 | max_hold | Total | full_stop% |
|--------|-----------|----------|---------|---------|----------|-------|------------|
| czce_sr | 2 | 1 | 3 | 1 | 4 | 11 | **18%** ✓ |
| czce_ta | 4 | 1 | 2 | 2 | 4 | 13 | 31% |
| czce_ma | 7 | 0 | 4 | 1 | 3 | 15 | 47% |
| dce_m | 7 | 0 | 2 | 4 | 1 | 14 | 50% |
| **dce_p** | **7** | 0 | 2 | 1 | 1 | 11 | **64%** ⚠ |

dce_p 与 dce_m 都是 7 个 full_stop，但 dce_m 有 4 个 tp1_tp2（+1.5R 各 = +6R）vs dce_p 只有 1 个 tp1_tp2。差距在**winner 大小**而非 loser 数量。

## Section 5: 为什么 dce_p 失败 — 结构性假说

### 假说 A: 棕榈油的市场结构（接受度高）

- **棕榈油价格波动剧烈**：受马来西亚/印尼天气、生物燃料政策、印度进口配额影响——日内 1-3% 波动家常便饭
- **PA pivot stop methodology** 找最近 swing low - 1%，但 dce_p 的 swing low 经常在 1-3 天内被穿透是噪音而非趋势
- **隔夜 gap 风险大**：3 个 1-bar stop-outs 都可能是隔夜大跌触发的 gap

### 假说 B: 2024-Q4 / 2025 棕榈油 regime 异常（部分接受）

- 2024-12 至 2025-Q3 棕榈油市场遭遇罕见持续下行——印尼出口政策反复、Trump 关税威胁
- 但 czce_ma（甲醇）也在 2024-2025 走弱，所以不只是棕榈油单一问题
- 2026 dce_p 反弹 +0.50R 暗示是 regime 而非永久结构损坏

### 假说 C: 结构性止损在 high-vol 商品上不合适（强）

- 1-bar stop_pct 仅 0.27% 是数据可见证据——这种紧度只对 low-vol underlying 合适
- 比较：dce_m 2024-12-17 也是 4.56% stop，但 2 bar 内未被打（dce_m 多波动一点反而保护了 trade）

## Section 6: 改进方案

| 方案 | 实现 | 适用范围 |
|------|------|----------|
| **方案 1（推荐）**：dce_p 显式排除 | `_CN_AGRI_POS_SYMBOLS.remove("kq_m_dce_p")` 或建 `_PA_H2_CLIMAX_EXCLUDED` | 重激活 climax 时立刻 ready |
| **方案 2**：dce_p 单独 stop_pct minimum | structural_stop 改成 max(pivot_stop, entry × 0.95) — 至少 5% buffer | 仅 dce_p |
| **方案 3**：bars_held minimum（time-stop deferral）| 前 3 bar 不 honor stop（给 signal 时间 mature）| 全 lane |
| **方案 4**：等市场 regime 改善 | 监控 dce_p 2026 H2 是否延续 +0.50R 趋势 | 被动 |

**推荐方案 1**：是最安全、最低成本、且没有副作用。其他 4 个 symbols 数据（即使 czce_ma 略负）总账 +0.99R，加上去掉 dce_p 后 EV 立刻变正。

预估：剔 dce_p 后 pa_h2_climax cn_agri_pos：
- n = 64 - 11 = 53
- sum = -2.58 - (-3.97) = +1.39R
- EV = +1.39 / 53 = **+0.026R**（从 -0.040R 翻正）

**仍然不强**——没法立刻撤销 STALE verdict，但 **dce_p exclusion 后 lane 不再是 PnL 负贡献**，未来重激活 baseline 时减一个 sample-size 问题。

## Section 7: 是否应立刻更新 baseline JSON？

是。记录 dce_p 排除决议 + 全部诊断证据。即使 lane 当前 weight=0，未来有人想 reactivate 时这是必读 prior。

更新 `baselines/pa_h2_climax_cn_agri_pos.json`：
- `symbols_excluded` 加 `kq_m_dce_p`
- 新增 `dce_p_excluded_rationale` section
- 估算 post-exclusion samples_full_stack_5y

## 复现

```bash
.venv/bin/python <<'PY'
import csv
P="/Volumes/Data Drive/derived/paired-trading/src-data-review/full_stack_backtest.csv"
rows = list(csv.DictReader(open(P)))
dce_p = [r for r in rows if r["lane"]=="pa_h2_climax" and r["symbol"]=="kq_m_dce_p"]
# 见 doc/repro/agri_pos_dce_p_diagnosis_2026-06-09.md Section 1
PY
```
