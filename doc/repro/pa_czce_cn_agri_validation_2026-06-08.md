# PA czce / cn_agri 0.0 weight 验证 — 2026-06-08

Followup to `pa_policy_validation_2026-06-08.md` pending row "czce/cn_agri 0.0 suppressed (未验证)"。
拆 CN_COMMODITY 聚合 (+0.044R, n=183) 成 CZCE_ONLY 与 DCE_AGRI 两个 sub-pool，直接验证 docstring "negative OOS — suppressed" 的声明。

## 一句话总结

CZCE 与 DCE_AGRI 的 OOS EV 都贴近零（+0.032R / +0.017R），fold 退化（F1 正 → F2/F3 负），hit% 仅 35-37%——**0.0 suppression weight 保留**。两个 pool 都不能算 "强负"，但也无法 promote 到 monitoring 级 (≥ +0.05R)。

## 方法

`scripts/backtest_pa_cn_phasefilter.py` 加 POOLS 子键：

```python
"CZCE_ONLY": ["kq_m_czce_ta","kq_m_czce_ma","kq_m_czce_cf","kq_m_czce_sr"],
"DCE_AGRI":  ["kq_m_dce_m","kq_m_dce_i","kq_m_dce_j","kq_m_dce_jm","kq_m_dce_p","kq_m_dce_y"],
```

PABottomDetector(min_h_legs=2, min_quality=0.3, min_gap=5) + ATR 1.5× stop, max_hold=40, K=3 walk-forward (IS ≤ 2022 / F1 2023 / F2 2024 / F3 2025+)，过滤 `higher_tf_relation == "opposing"`。

## 结果

### CZCE_ONLY (n=46 OOS, 4 symbols)

| 切片 | n | EV | F1 | F2 | F3 |
|------|---|----|----|----|----|
| All h=opp OOS | 46 | **+0.032R** | +0.294 (n=14) | -0.068 (n=17) | -0.100 (n=15) |
| TR phase | 44 | +0.022R | +0.294 | -0.166 | -0.036 |
| TR + at_bot | 18 | -0.318R | -0.013 | -0.707 | +0.000 |

IS: n=39 EV +0.278R → OOS 退化到 ~0。BULL phase: 0 signals（CZCE 几乎全 TR_FORMING）。
hit% = 37% (17 win / 29 loss)。

Per-symbol OOS：ta +0.250R(14) / sr +0.111R(10) / cf -0.022R(7) / ma -0.199R(15)

### DCE_AGRI (n=105 OOS, 6 symbols)

| 切片 | n | EV | F1 | F2 | F3 |
|------|---|----|----|----|----|
| All h=opp OOS | 105 | **+0.017R** | +0.239 (n=23) | -0.086 (n=35) | -0.014 (n=47) |
| BULL excluded | 102 | +0.013R | +0.238 | -0.088 | -0.014 |
| TR phase | 98 | -0.007R | +0.238 | -0.088 | -0.062 |
| TR + at_bot | 48 | +0.042R | +0.000 | -0.026 | +0.167 |

IS: n=48 EV +0.347R → OOS 退化到 ~0。
hit% = 35% (37 win / 68 loss)。

Per-symbol OOS：m +0.607R(14) ⭐ / i +0.139R(18) / p -0.028R(24) / j -0.095R(21) / y -0.200R(15) / jm -0.269R(13)

## 关键判断

1. **EV 极弱 + fold 退化**：CZCE F1+0.294 → F3-0.100，DCE F1+0.239 → F3-0.014。F1 完全靠 2023 单年支撑，2024/2025 都负，与 CN_METAL 的 3 fold 全正 (F1+0.59/F2+1.05/F3+0.26) 反差极大。
2. **hit% 35-37%**：典型负期望分布——靠零星 1.5R 拉平，去掉 14-35 个 1.5R 高位会立刻塌成强负 EV。生产路径不稳。
3. **IS→OOS 衰减**：IS +0.28 / +0.35 → OOS +0.03 / +0.02，over-fit 痕迹明显。
4. **CN_METAL TR phase = +0.666R** 对比 CZCE TR +0.022R / DCE TR -0.007R——同样的 detector 同样的 phase，metal vs agri 行为完全不同，**0.0 weight 区分 cn_metal 与 cn_agri 是正确的**。
5. **DCE 内部分化**：dce_m (豆粕) 单独 OOS +0.607R(n=14)，可能是 sub-sub-pool 候选，但 n 太小 (14)、距 production 门槛 (n≥50/fold) 远。**不建议**单独 promote。

## 结论

**保留 czce/cn_agri 0.0 weight (suppression)**。docstring 表述可微调：
- 现：`czce/cn_agri: 0.0 (negative OOS — suppressed)`
- 建议：`czce/cn_agri: 0.0 (OOS EV ≈ 0 with fold degradation, hit% 35-37% — suppressed)`

理由 "negative OOS" 不完全准确（实际 +0.02~+0.03），但 suppression 决定本身是正确的。

## 下一步建议

- 不建议把 czce 或 cn_agri 整体加入 policy table。
- 若未来想挖：单独看 dce_m (豆粕)，需要扩样到 n≥50/fold（加 60min 或更早数据）。
- 本次 CSV 未持久化，复跑命令：
  ```
  cd src && .venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool CZCE_ONLY
  cd src && .venv/bin/python scripts/backtest_pa_cn_phasefilter.py --pool DCE_AGRI
  ```

## 代码

- 修改：`scripts/backtest_pa_cn_phasefilter.py` POOLS 新增 `CZCE_ONLY`、`DCE_AGRI` 两个 sub-key。
- 复用：`data/bar_loader.load_bars_quant_or_json`（Parquet → JSON fallback）。
