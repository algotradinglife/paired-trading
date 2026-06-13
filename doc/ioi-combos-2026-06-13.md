# inside / outside / ioi 蜡烛组合 — 机械统计探针（2026-06-13）

卡片 t_26f5a08c（PA 假设，探索性探针）。
**本文件只列机械统计，不打 PASS/FAIL，不解读裁决。**

## 假设 / 目的

评估 inside bar / outside bar / ioi（inside→outside→inside 三根 breakout-pending 组合）
是否值得做成正式 detector。两件事：(a) 这些组合多频繁出现，(b) 出现后的前向 EV
（在底部 / breakout 语境下），用以判断是否值得建 detector。仅输出机械统计。

## 定义（标准 PA，全部无前视，仅用 t 及之前的 bar）

- inside bar：`high[t] <= high[t-1] AND low[t] >= low[t-1]`
- outside bar：`high[t] >= high[t-1] AND low[t] <= low[t-1]`
- ioi：`inside(t-2) → outside(t-1) → inside(t)`，在 t 当根确认

## 方法

**前向结果度量（两套，均无前视）：**

1. **forward_atr_return（主度量）**：`fwd_atr_k = (close[t+k] − close[t]) / ATR[t]`，
   k ∈ {5,10,20}。candle 组合本身无方向，简单前向 ATR 归一化收益最干净、无方向假设；
   ATR 相对而非固定 %（债期整段波动 <2%，固定 % 度量在债上失真）。端点：仅当
   `t+k < len(bars)` 才计入（窗口右端越界则丢弃，不补 NaN、不前视）。
2. **simulate_trade_bottom（辅助度量）**：复用 `backtest_rr_pool.simulate_trade`，
   `direction="bottom"`，组合 bar 收盘进场，ATR×1.5 止损 + 1R/2R 缩仓 + MAX_HOLD=20，
   EV=mean(realized_r)。仅作 bottom 语境的方向化对照（组合本身方向不明，标为辅助）。

**bottom×opposing 共现**：用 `detect_signals` + `enrich_with_higher_tf` 判定组合 bar 是否
同时命中已验证的 bottom × higher_relation=opposing 信号（仅需 higher_relation，故略去
lower_tf enrich）。**共现判定仅在 HTF（60min）覆盖的 daily bar 范围内有效**——覆盖外的
bar coincidence 未知，单列 unknown，不计入 standalone（codex P2：否则零重叠结论被未知 bar 污染）。
covered bar 内分 standalone vs coincident 两组对比。

**Bootstrap**：10000 resample、seed=42，对 `fwd_atr_10` 与 `sim_bottom` EV 给 95% CI
（pooled + by-pool；其余 horizon 只列 ev/hit 不做 CI）。

复现：`cd src && uv run python scripts/analyze_ioi_combos.py --pools CN_BOND CN_METAL US_EQUITY --out data/review/ioi_combos.json`
脚本：`src/scripts/analyze_ioi_combos.py`（17 单测 `src/tests/test_analyze_ioi_combos.py`）
工件：`src/data/review/ioi_combos.json`（派生，gitignore 不提交，命令重生）。

## (a) 出现频率（每 1000 daily bars）

总扫描 19270 daily bars，4346 次组合出现（一根 bar 可同时计入 inside 与 ioi，分别计数）。

| 池 | bars | inside / 1000 | outside / 1000 | ioi / 1000 |
|----|------|---------------|----------------|------------|
| POOLED | 19270 | 117.4 | 104.0 | **4.10** |
| CN_BOND | 3948 | 133.0 | 117.3 | 4.31 |
| CN_METAL | 6540 | 130.3 | 98.3 | 4.74 |
| US_EQUITY | 8782 | 100.9 | 102.3 | 3.53 |

inside ≈ 10–13% 的 bar，outside ≈ 10–12%；**ioi 罕见，约每 1000 根 4 次**（pooled n=79）。

## (b) 前向 EV / hit（主度量 fwd_atr_k，ATR 单位）+ 辅助 sim_bottom

### POOLED

| 组合 | n | f5 EV | f10 EV (95%CI) | f10 hit | f20 EV | sim_bottom EV (95%CI) | sim TP1 | sim full_stop |
|------|---|-------|----------------|---------|--------|----------------------|---------|---------------|
| inside | 2263 | +0.194 | +0.436 [0.340, 0.531] | 60.2% | +0.835 | +0.184 [0.139, 0.231] | 55.3% | 42.1% |
| outside | 2004 | +0.195 | +0.337 [0.229, 0.442] | 57.3% | +0.734 | +0.134 [0.085, 0.184] | 52.8% | 44.5% |
| **ioi** | 79 | +0.553 | **+0.856 [0.338, 1.367]** | **70.3%** | **+1.542** | +0.255 [0.001, 0.508] | 55.3% | 40.8% |

ioi 的 f10 与 sim_bottom CI 下界均 > 0（sim 仅勉强 >0）；f20 EV +1.54、hit 70%。
inside/outside f10/f20 CI 整段 > 0，但 EV 量级远低于 ioi，且大头是横截面上涨漂移
（见下"中性观察 2"）。

### By-pool（f10 EV / 95%CI / hit；sim_bottom EV / 95%CI）

**inside**

| 池 | n | f10 EV (95%CI) | f10 hit | sim_bottom EV (95%CI) |
|----|---|----------------|---------|----------------------|
| CN_BOND | 525 | +0.303 [0.126, 0.481] | 59.7% | +0.262 [0.165, 0.359] |
| CN_METAL | 852 | +0.430 [0.264, 0.595] | 57.2% | +0.152 [0.077, 0.225] |
| US_EQUITY | 886 | +0.520 [0.372, 0.668] | 63.5% | +0.168 [0.094, 0.242] |

**outside**

| 池 | n | f10 EV (95%CI) | f10 hit | sim_bottom EV (95%CI) |
|----|---|----------------|---------|----------------------|
| CN_BOND | 463 | +0.452 [0.259, 0.649] | 61.8% | +0.259 [0.158, 0.359] |
| CN_METAL | 643 | +0.226 [0.026, 0.430] | 53.6% | +0.101 [0.017, 0.185] |
| US_EQUITY | 898 | +0.357 [0.202, 0.511] | 57.7% | +0.094 [0.018, 0.167] |

**ioi**（n 很小，CI 宽）

| 池 | n | f10 EV (95%CI) | f10 hit | f20 EV | sim_bottom EV (95%CI) |
|----|---|----------------|---------|--------|----------------------|
| CN_BOND | 17 | +0.986 [0.398, 1.652] | 76.5% | +1.285 | +0.279 [−0.213, 0.775] |
| CN_METAL | 31 | +0.699 [−0.289, 1.772] | 62.1% | +1.054 | +0.131 [−0.270, 0.536] |
| US_EQUITY | 31 | +0.939 [0.155, 1.666] | 75.0% | +2.202 | +0.378 [−0.060, 0.793] |

ioi f10 EV 三池同号为正；**CN_BOND 与 US_EQUITY 的 f10 CI 整段 > 0，CN_METAL 跨 0**
（n=31）。sim_bottom（方向化）三池 CI 均跨 0——方向化 ATR 止损口径下 ioi 边缘不显著。

## ioi × bottom×opposing 共现（standalone vs coincident）

仅 HTF 覆盖内的 bar 参与分组（covered=3700，unknown 无覆盖=646 单列含 HTF 暖机期，codex P2×2）：

| 口径 | 组合 | n | f10 EV (95%CI) | sim_bottom EV |
|------|------|---|----------------|----------------|
| standalone | inside | 1933 | +0.435 [0.335, 0.537] | +0.196 |
| standalone | outside | 1643 | +0.327 [0.213, 0.443] | +0.152 |
| standalone | **ioi** | 72 | +0.908 [0.369, 1.465] | +0.303 |
| coincident | inside | 13 | +0.250 [−1.31, 1.81] | +0.069 |
| coincident | outside | 39 | +0.520 [−0.12, 1.15] | +0.092 |
| coincident | **ioi** | **0** | — | — |

**共现样本极稀疏**：covered bar 内仅 52 个组合 bar 同时命中 bottom×opposing，**ioi∩(bottom×opposing)=0**
（ioi 全程未与 bottom×opposing 重叠）。coincident inside/outside CI 均跨 0。**无法**对
"ioi 在 bottom×opposing 语境下是否更强"作任何机械判断——样本不存在。

## 中性观察（不裁决）

1. **频率**：ioi 罕见（~4/1000 bars，pooled n=79；单池 17–31）。inside/outside 常见
   （~100–130/1000）。
2. **inside/outside 的正 EV 主要是横截面上涨漂移**，非方向信号：三池 f10/f20 普遍正，
   但 2021–2026 含贵金属/美股上行段，无方向 fwd_atr 会系统性偏正；sim_bottom（带 −1R
   止损的方向化口径）下 inside/outside EV 降到 +0.09~+0.26、full_stop 42–48%，边缘很薄。
3. **ioi 的前向边缘在主度量上最强**：pooled f10 +0.86（CI 不含 0）、f20 +1.54、hit 70%，
   量级约为 inside/outside 的 2×。但 (i) n 小、CI 宽；(ii) 方向化 sim_bottom 口径下
   三池 CI 全跨 0；(iii) 与 inside/outside 共享同一上涨漂移成分，未做漂移基准扣除。
4. **池间异质**：ioi f10 CN_BOND/US_EQUITY CI 整段 > 0、CN_METAL 跨 0。inside/outside
   各池同号正但量级有别（US inside 最高、CN_METAL outside 最弱）。regime 不可移植告诫
   适用——勿把单一 pooled 数字外推到所有市场。
5. **共现 null**：ioi 与 bottom×opposing 零重叠，inside/outside 共现样本 n=13/39 且 CI 跨 0；
   "组合 ∧ 已验证底部信号"这一交集在现有数据上不可统计。

## 是否值得做成正式 detector（证据汇总，不打 PASS/FAIL）

- **频率**：ioi 约 4/1000 bars——若做成 detector，事件密度低（19270 bars 全样本仅 79 次），
  单独成 lane 的样本积累慢；inside/outside 密度高但本身近乎"无信息"的常见形态。
- **EV 证据**：ioi 在无方向 fwd_atr 主度量上显示正向漂移且 hit 偏高（pooled f10 CI 不含 0），
  方向上看似 breakout-pending 朝上释放占优；但方向化 ATR-止损口径（sim_bottom）下边缘
  不显著（三池 CI 跨 0），且未扣除横截面上涨漂移基准、n 小。
- **可做成 detector 的前提（数据层面）**：需要 (i) 更长 / 更多品种以把 ioi 的 n 从几十提到
  几百；(ii) 对 fwd_atr 做"同期无条件 base-rate 漂移"扣除，确认 ioi 超额 EV 而非市场 beta；
  (iii) 一个明确的方向规则（ioi 本身无方向，sim_bottom 仅是单向假设）。
- 现状：ioi 是"信号弱但方向一致、样本太薄"的候选；inside/outside 是"高频但低信息量"。
  本探针给出的是机械证据，不构成建/不建 detector 的裁决。
