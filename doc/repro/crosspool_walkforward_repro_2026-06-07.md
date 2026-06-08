# crosspool-walkforward 复现 — 2026-06-07

对照 `doc/legacy/crosspool-walkforward-report-2026-05-31.html`。

## 结论

报告判定 **STRONG PASS** 在新数据下降级为 **基础 PASS**：5 fold 全正与 OOS 无退化两条核心支撑塌了。

## 主指标对比

| 指标 | 报告 (n=102) | 重跑 (n=908) |
|------|-------------|--------------|
| IS EV/signal | +0.855R | +0.160R |
| IS Sharpe | 8.69 | 4.30 |
| F1 OOS EV | +0.786R | +0.242R |
| F2 OOS EV | +0.879R | **+0.085R** |
| F2 Sharpe | 5.11 | **1.29** |

新 detector 的 6 个 `intra_cycle_*` level 变体把样本扩展到 8.9x，EV 因低质量信号稀释而降。

## 池稳定性

| Pool | 报告 F2 | 重跑 F2 | 报告叙事 |
|------|---------|---------|----------|
| US_EQUITY | +0.375R (弱) | **-0.260R** | ✅ 衰减叙事加强 |
| US_MACRO | +1.424R (强) | +0.084R | ❌ "steadily strong" 不成立 |
| CN_METAL | +0.782R | +0.460R | ✅ 跨 fold 最稳保留 |
| CN_AGRI | +1.021R | +0.119R | ❌ 大幅衰减 |
| CN_INDEX | +1.500R (n=2) | +0.667R (n=3) | △ 仍小样本 |

## Verdict 对照

| 报告条件 | 重跑结果 | 保留 |
|---------|---------|------|
| 2/2 fold EV>0 | 2/2 | ✅ |
| 2/2 fold Sharpe>0.6 | 2/2（F2=1.29 险过）| ✅ |
| OOS 无 IS 退化 | F2 EV 衰减 47% | ❌ |
| 5/5 池在两 fold 都正 | F1 5/5、F2 4/5 | ❌ |

## 代码与数据

- `tools/repro_crosspool_walkforward.py` — 复现脚本
- 输入：`data/review/rr_b_{cn_metal,cn_agri,cn_index,us_equity,us_macro}.csv` (2026-06-07 重生成)
- 过滤：`direction='bottom' & higher_relation='opposing'`
- K=3 chronological chunk，Fold1=chunk0→chunk1，Fold2=chunk0+1→chunk2
