# Codex Round 2 验证结论

## 总评

5个候选模式中，**F8 是唯一全验证通过**的。其他4个均为 Edge（可选谨慎添加，需持续监控）。

## 各候选判定

### F8: direction=bottom + subtype=weakness ✅ Survives（高置信度）
- n=123, 68.3% hit, +2.63% mean — 最大样本基线
- Bonferroni hit p=0.0145 ✅, mean p=0.0115 ✅ — 均通过
- Newey-West p=0.000018 ✅
- 2022: 仅6/123 (5%) — 非 regime 依赖
- 与 F2 重叠仅 2.4%
- **建议**：加入 downstream_policies.py，weight 1.10，作为 universal bottom-boost 基线

### F5: subtype=standard + leading + in_cycle ⚠️ Edge
- n=31, 83.9% hit, +3.55% mean
- Bonferroni 均通过
- 方向不对称：bottom 100% hit vs top 77.3% — 较强但需 monitoring
- **建议**：可选加入 weight 1.05，监控

### F6: leading + in_cycle + opposing ⚠️ Edge
- n=27, 88.9% hit, +4.43% mean — F2 的方向无关版
- Bonferroni 均通过
- 33.3% 与 F2 重叠
- 方向不对称：bottom 100% / +8.12% vs top 83.3% / +2.58%
- **建议**：可选加入 weight 1.05，监控

### F7: bottom + opposing + W in_cycle ⚠️ Edge
- n=36, 80.6% hit, **+6.72% mean（最高收益）**
- Bonferroni hit p=0.074 不通过（mean p=0.0014 通过）
- **50% 信号来自 2022 熊市**
- Newey-West p=0.000206 通过
- 与 F2 重叠 27.8%
- **建议**：可选加入 weight 1.05，但需持续验证 regime 依赖

### F9: lower_relation=leading（单维）⚠️ Edge（以 direction-agnostic 提法则 ❌ Collapses）
- 统一提法 Bonferroni mean p=0.441 — **不通过**
- bottom+leading (n=47, 78.7%, +4.79%) — 极强
- top+leading (n=37, 64.9%, +0.45%, CI 过零) — 不显著
- **结论：只是 bottom asymmetry 的再发现，不是新的方向无关信号**

## 汇总

| 候选 | 判定 | 建议 |
|------|------|------|
| F8: bottom+weakness | ✅ Survives | Add to policy (w=1.10) |
| F5: standard+leading+in_cycle | ⚠️ Edge | Optional add (w=1.05, monitor) |
| F6: leading+in_cycle+opposing | ⚠️ Edge | Optional add (w=1.05, monitor) |
| F7: bottom+opposing+W in_cycle | ⚠️ Edge | Optional add (w=1.05, 注意regime) |
| F9: leading 单维 | ⚠️ Edge | bottom+leading 真，top+leading 假 |
