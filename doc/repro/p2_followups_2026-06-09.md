# P2 后续实验结果 — 2026-06-09

P2 regime gate（commit `113f6520`）已部署。本文记录后续三个并行评估结果，**两个 REJECT 一个 DEPLOYED**。

## P2/A：TP1 1R → 0.75R（REJECT）

### 假说
PA H2 US daily lane 58% max_hold rate（pa_us_dif_pos）和 38% max_hold rate（pa_h2 CN_METAL）——直觉认为 TP1 设得太远，trade 等不到 TP1 就 timeout 被 clip。

### 测试
CSV 上保守模拟（保持 outcome 分类，调整 R 计算）：

| Lane | n | 当前 EV | TP1=0.75R 后 EV | ΔR/trade | Δ累计 |
|------|---|---------|-----------------|----------|-------|
| pa_us_dif_pos | 49 | +0.186R | +0.151R | **-0.035** | **-1.71R** |
| pa_h2 (CN_METAL) | 102 | +0.189R | +0.143R | **-0.046** | **-4.66R** |

### 为什么失败？

诊断错了。检查 max_hold 子集的 realized R：

| Lane | max_hold trades | realized R ≥ 0.75 |
|------|-----------------|-------------------|
| pa_us_dif_pos | 27 | **2** |
| pa_h2 | 39 | **2** |

**只有 4 个 max_hold trade 的 realized R 达到 0.75R**——绝大多数 max_hold trades 是"价格 20 bars 几乎没动" 而不是"等不到 TP1"。

降低 TP1 反而损失：
- tp1_tp2 outcome 的 +1.5R 中第一腿从 +1R 降到 +0.75R → 新 R = +1.375R（损 -0.125R/trade）
- tp1_max 同样损失
- 唯一受益的是 max_hold 转 tp1_max（4 个 trade）—— 杯水车薪

### 正确方向
要解决 max_hold 问题：
- **延长 max_hold 20 → 30 bars**，给 slow trades 时间到 TP1（需要真正 re-simulate，CSV 不够）
- 或者接受 lane 的本质特征：US daily PA H2 是慢信号，cycle 周期长

## P2/B：us_regime_gate baseline 治理（DEPLOYED）

### 产物
1. `baselines/us_regime_gate.json` — meta-gate baseline with kind=meta_gate
   - calibration_per_year_pct_risk_off_days
   - counterfactual_us_h2_family_2022 - 71→4 trades, -21.4R → +0.5R
   - counterfactual_us_pool_total_5y - 423→257 trades, +34.7R → +54.7R
   - lanes_NOT_gated_with_rationale（why pa_us_dif_pos / pa_h2_climax / CN lanes are not gated）
2. `baselines/EXPECTED_LANES.json` — registered as kind=meta_gate
3. `validate_baselines.py` — 加入 `DEPLOYED` verdict

新 dashboard：
```
11 entries audited; 9 OK; 1 STALE; 1 PENDING
[ OK ]  us_regime_gate  us_equity  DEPLOYED  —  valid for 183d
```

valid_until: 2026-12-09（6 个月）—— SPY-VIX 关系结构性变化时需要重新校准 vol threshold。

## P2/C：pa_us_dif_pos regime gate（REJECT）

### 假说
和 pa_us_60min + context_a US 一样，US daily PA H2 在 2022-style bear 应该也被压制。

### 测试
2022 年（risk_off 86.5% of days）pa_us_dif_pos 实测：

| Year | 当前 (post-P1c) | 加 regime gate 后 |
|------|----------------|--------------------|
| 2021 | n=4 sum-2.22 | unchanged (gate 不开)|
| **2022** | **n=5 sum+0.94R** | **n=2 sum+0.50R** ⚠ |
| 2023 | n=5 sum-0.21 | unchanged |
| 2024 | n=10 sum+2.45 | unchanged |
| 2025 | n=18 sum+8.04 | unchanged |
| 2026 | n=7 sum+0.12 | unchanged |

### 为什么 reject？
2022 那 3 个被 gate 抹掉的 trade **净贡献 +0.44R（正的）**。pa_us_dif_pos 的 DIF>0 + h=opp filter 是**自然 regime filter**：
- DIF>0 要求 daily 处于 bullish MACD 阶段——2022 大部分时间不满足
- h=opp 要求 60min DIF<0——"daily 上升 + 60min 下降" 正是经典 bottom 场景，2022 zoom-in 反弹时常见

所以 pa_us_dif_pos 在 2022 已经稀少发火，但发的火质量好。叠加 SPY-based gate 反而剔了好 trade。

### 学到
不要假设所有 US lane 都应同等 regime-gate。pa_us_dif_pos 自带 macro filter（DIF>0），不需要外部 gate。

## 综合状态

**当前 production 累计（P0+P1c+P2）counterfactual on full_stack 5.5y**：

```
                  baseline       current
n                 954            778
EV/trade          +0.131R        +0.197R         (+50%)
sum R             +124.52R       +153.46R        (+27R)
win%              53.2%          57.7%           (+4.5pp)

US pool:          +0.082R    →   +0.213R         (+160%)
CN_METAL:         +0.212R    →   +0.241R         (+14%)
```

US H2 family 2022（pa_us_60min + context_a US）：从 -21.4R drag → +0.5R。**2022 灾难年被驯服**。

## 下一轮路线图

| 优先级 | 项目 | 价值 |
|--------|------|------|
| 中 | max_hold 20 → 30 实验（PA H2 daily lanes）| 真正再跑 backtest 才能确定 |
| 中 | AGRI_POS dce_p / czce_ma 单 symbol 根因 | depends |
| 低 | validate_baselines.py --full 真正解析 backtest 输出 | infra |
| 低 | Schema v2 字段（owner/data_hash/fold_dates/slippage）| infra |
| 低 | regime gate vol threshold 季度复核（SPY-VIX 关系漂移检测）| forward |
