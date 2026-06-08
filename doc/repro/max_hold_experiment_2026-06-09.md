# max_hold 20→30 实验结果 — 2026-06-09

P2/A 拒绝 TP1 0.75R 之后的真正候选：**延长 max_hold daily bar 上限 20 → 30**，给慢速 trade 更多时间触 TP1。重新跑 full_stack 5.5y / 954 trades，**应用 P0+P1c+P2 production 排除集**做 apples-to-apples 比较。

## 头条结论

**接受 max_hold=30 作为新默认**。聚合 +25% EV / +38.72R 累计，没有任何单一 lane 显著恶化。

```
                       max_hold=20       max_hold=30        Δ
n (post-filter)       778               778                +0
EV/trade              +0.1972R          +0.2470R           +25%
sum R                 +153.46R          +192.18R           +38.72R
win%                  57.7%             58.2%              +0.5pp
avg hold bars         16.0d             21.6d              +5.6d
```

## Per lane 分解

| Lane | n | EV20 → EV30 | Δ累计R | 评估 |
|------|---|------------|--------|------|
| **bpull** | 172 | +0.179 → +0.267 | **+15.07R** ⭐ | CN_METAL pullback 需要时间走出来 |
| **context_a** | 223 | +0.226 → +0.295 | **+15.48R** ⭐ | US+CN_METAL 都受益（最大绝对值贡献）|
| **pa_cn_bond** | 73 | +0.123 → +0.190 | +4.90R ⭐ | bond futures cycle 慢，30 bar 更合身 |
| **pa_us_dif_pos** | 49 | +0.186 → +0.220 | +1.67R ⭐ | 用户原始目标 lane，+18% EV |
| **pa_h2_climax** | 64 | -0.040 → -0.020 | +1.28R | 即使 STALE lane 也略改善 |
| pa_h2 (CN_METAL) | 102 | +0.189 → +0.195 | +0.61R | minimal |
| pa_us_60min | 53 | +0.387 → +0.387 | +0.00R | n/a (60min lane 用 max_hold_60min=140) |
| vflush | 42 | +0.404 → +0.397 | -0.27R | 几乎不变（vflush 平均 hold 3.5 bar，max_hold 不咬）|

## Outcome 分布迁移（机制确认）

### pa_h2 (CN_METAL)
| Outcome | n=20 | n=30 |
|---------|------|------|
| max_hold | 39 (38%) | **27 (26%)** ⬇ |
| tp1_tp2 | 20 (20%) | **26 (25%)** ⬆ |
| full_stop | 27 (26%) | 32 (31%) ⬆ |
| tp1_max | 14 | 15 |

12 笔从 max_hold 解放，其中 6 笔变成 tp1_tp2（+1.5R 大胜），但有 5 笔变成 full_stop（多持几 bar 反而被止损）。**净增 R 但要付 stop 风险代价**。

### pa_us_dif_pos
| Outcome | n=20 | n=30 |
|---------|------|------|
| max_hold | 27 (55%) | **23 (47%)** ⬇ |
| tp1_tp2 | 5 (10%) | 6 (12%) |
| full_stop | 9 (18%) | 10 (20%) |
| tp1_stop | 0 | 2 |

少 4 笔 max_hold，多 1 笔 tp1_tp2，多 1 笔 full_stop，多 2 笔 tp1_stop。比 pa_h2 更柔和。

### pa_h2_climax (STALE)
| Outcome | n=20 | n=30 |
|---------|------|------|
| max_hold | 13 (20%) | **7 (11%)** ⬇ |
| tp1_tp2 | 9 (14%) | 11 (17%) ⬆ |
| tp1_max | 13 | 14 |
| full_stop | 27 (42%) | 28 (44%) |

6 笔从 max_hold 解放，4 笔变成 tp1 系列（好）。STALE lane 仍负 EV 但损失减半。

## 年度敏感性（pa_h2 + pa_us_dif_pos）

### pa_h2 CN_METAL
| Year | n | sum20 → sum30 | 备注 |
|------|---|---------------|------|
| 2021 | 18 | +1.80 → +2.17 | 略增 |
| **2022** | 29 | -0.84 → **-2.61** ⚠ | bear regime 多持反而恶化（trade 给市场更多时间走错）|
| 2023 | 14 | +4.70 → +4.68 | 平 |
| 2024 | 13 | +10.79 → +11.55 | 略增 |
| 2025 | 20 | +7.03 → +9.03 | 显著增 |
| 2026 | 8 | -4.21 → -4.96 | 略恶化 |

### pa_us_dif_pos
| Year | n | sum20 → sum30 | 备注 |
|------|---|---------------|------|
| 2021 | 4 | -2.22 → -2.45 | 略恶化 |
| **2022** | 5 | +0.94 → **+2.34** ⭐ | 大幅改善（regime gate 已经只放 2 个 trade 过滤；多持让它们抓到 TP）|
| 2023 | 5 | -0.21 → -0.45 | 略恶化 |
| 2024 | 10 | +2.45 → +1.99 | 略恶化 |
| 2025 | 18 | +8.04 → +9.69 | 改善 |
| 2026 | 7 | +0.12 → -0.35 | 略恶化 |

**有趣对比**：pa_h2 在 2022 恶化，pa_us_dif_pos 在 2022 改善——同样的延长 max_hold，市场 regime 在两条 lane 上效应相反。这说明 max_hold 不是单调改善——它是 winner / loser 重新洗牌的赌注，**总账正但单年波动加大**。

## 为什么 bpull / context_a 受益最大？

avg hold bars 比较：

| Lane | avg hold (20) | avg hold (30) |
|------|---------------|---------------|
| bpull | 17.6d | **24.5d** |
| context_a | 16.9d | **23.1d** |
| pa_cn_bond | 19.9d | **29.6d** |
| pa_h2_climax | 13.4d | **17.1d** |
| pa_h2 | 14.6d | 19.1d |
| pa_us_dif_pos | 16.4d | 23.1d |
| vflush | 3.5d | 3.7d ← 几乎不咬到 max_hold |

bpull / context_a 的 avg hold 在 max_hold=20 接近 cap（17-18 vs 20），说明很多 trade 卡在 cap。放宽到 30 后 avg 也明显增加（到 23-25），说明 trade 真的需要这些 bar 来 mature。

vflush 完全不咬——avg 只 3.5d，因为 V-shape reversal 信号 TP1 通常 1-3 天就触发。

## 部署决策

1. **更改 `backtest_full_stack.py` 默认 `--max-hold-daily 20 → 30`**——所有未来 backtest 用新默认
2. **不改 `max_hold_60min` (140)** —— 60min lane 已经长够，不受影响
3. **不影响 production score_today.py** —— max_hold 是 backtest measurement 参数，production 只 emit 信号，user 自己决定持仓
4. **更新 baseline JSON 的 samples_full_stack_5y** —— 反映新的实测数字
5. **新增 caveat：单年波动加大**——2022 pa_h2 单年恶化是真实成本

## 限制 / Caveats

- **TP1/TP2 simulation 假设固定 1R / 2R 距离**——没考虑 ATR 演变
- **max_hold=30 没做 walk-forward**——这是 in-sample 优化；理论上需要 K=3 验证才 production-grade
- **2022 pa_h2 -1.77R 恶化**是真实代价，不是噪声
- **pa_us_dif_pos 改善源自 2022 单年大增**——n=5 sample，需要 forward 验证
- **vflush 例外**说明这个改动不是普适——某些 fast-signal lane 不受益

## 复现

```bash
cd src
# baseline (production current — already in full_stack_backtest.csv)
DERIVED_ROOT="/Volumes/Data Drive/derived" \
  .venv/bin/python scripts/backtest_full_stack.py --max-hold-daily 20

# experiment (max_hold=30)
DERIVED_ROOT="/Volumes/Data Drive/derived" \
  .venv/bin/python scripts/backtest_full_stack.py --max-hold-daily 30 \
  --out-csv "$DERIVED_ROOT/paired-trading/src-data-review/full_stack_mh30.csv"

# Comparison
.venv/bin/python /tmp/compare_mh.py
```

## 下一轮

| 优先级 | 项目 | 价值 |
|--------|------|------|
| 中 | AGRI_POS dce_p / czce_ma 单 symbol 根因 | 解 STALE |
| 中 | max_hold=30 K=3 walk-forward 验证 | 确认 +38.72R 不是 in-sample 优化 |
| 中 | 2022 pa_h2 单独 regime gate（CN_METAL 不是 SPY）| 解决 -1.77R cost |
| 低 | validate_baselines.py --full 真解析 | infra |
| 低 | Schema v2 字段 | infra |
