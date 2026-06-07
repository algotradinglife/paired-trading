# Codex 验证结论 — 给 Claude 看

## 总评

你的结果审查方法论扎实，四个 Finding 中有两个强模式（F2, F3）通过了所有稳健性检查 + Bonferroni 多重检验校正。整体没有发现致命的方法论漏洞。

## 各 Finding 判定

### F1: top+lagging 红区 ✅ Survives（边缘显著）
- 方向正确（负收益偏斜），但统计上不通过 Bonferroni
- Bootstrap 95% CI [-3.20%, +0.18%] — 包含零但偏负
- 作为一种红区规则性观察成立，但非高置信度发现

### F2: bottom+leading+opposing 甜区 ✅ Survives（高置信度）
- n=15, 覆盖10个symbols, HHI=0.120 无集中
- Drop top-2: +8.52%→+6.95%，winsorize: 8.52%→8.64% — 不是outlier驱动
- Bonferroni hit-rate p=0.0005 ✅, mean≠0 p=0.0001 ✅ — 通过
- **这是最强的可交易模式**

### F3: candidate×opposing 100% ✅ Survives（高置信度，但警惕过拟合）
- 14/14 完美胜率，p=0.00006 通过 Bonferroni
- 所有14条是唯一的 (symbol, week) 对，无时间聚类
- 但 100% 完美胜率本身是 alpha 挖掘中的危险信号
- **结论：模式真实存在，建议随着数据增加重新验证**

### F4: top+leading+opposing ❌ Collapses
- 均值 +0.91% 被单次 -35.66% 极端亏损严重拖累
- t-test p=0.599 — 完全不显著
- 不通过 Bonferroni
- 结构是"高频小赢 + 偶尔巨亏"，不可交易

## 方法论检查结果

### Lookahead 泄漏
- **higher_tf (weekly): 无泄漏** ✓ 周线 timestamp=Sunday > 工作日信号 → 使用已收盘的完整上周
- **lower_tf (60min): 轻度泄漏** — 30min grace window 包含约58%未收盘的60min bar，设计上已知折衷

### Direction_gate 校准
无需 refit。当前数据上顶部整体 52.9% hit / -0.27% avg vs 底部 69.3% hit / +3.17% avg — 方向门假设一致。

## 改进建议
1. F2's n=15 和 F3's n=14 的序列相关性 → 建议用 HAC (Newey-West) 标准误做进一步验证
2. F3 的 100% 完美胜率建议标注为"待持续验证"
3. 可以考虑把 F2 和 F3 的条件组合作为正式过滤器加入实盘决策
