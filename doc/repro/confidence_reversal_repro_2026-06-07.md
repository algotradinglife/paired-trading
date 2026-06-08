# confidence-reversal 复现 — 2026-06-07

对照 `doc/legacy/confidence-reversal-report-2026-05-31.html`。

## 结论

**第一份核心定量结论成功复现**：报告关键发现"TOP × mid 弱化"逐项对得上。

## §4 TOP × mid 弱化（报告核心发现）

| 段 | 报告 EV | 重跑 EV | 是否保留 |
|----|---------|---------|---------|
| TOP × low | +0.360R | +0.354R | ✅ |
| TOP × mid | +0.157R | +0.145R | ✅ |
| TOP × high | +0.376R | +0.323R | ✅ |

数字逐项接近，pattern 完全一致。

## §2 池合并 EV by band

| Band | 报告 | 重跑 |
|------|------|------|
| low  | +0.431R | +0.242R |
| mid  | +0.359R | +0.150R |
| high | +0.417R | +0.154R |

EV 量级降但 CIs 重叠，"置信度无单调预测力"成立。

## §3 单调性

报告：0/10 pool×direction 满足 low<mid<high。
重跑：**2/10** 满足（CN_AGRI bottom + US_EQUITY top）。"无一"不完全成立，但 8/10 仍非单调。

## §6 h=opposing 是否覆盖 confidence

报告 bot×opp×band：+0.900 / +0.952 / +0.699R（CIs 重叠）
重跑：+0.225 / +0.095 / +0.165R（CIs 仍重叠）

EV 量级降 4x，但**"h=opp 已覆盖 conf 信息"成立**。

## §7 时间稳定性

| 期 | 报告 mid EV | 重跑 mid EV |
|----|-------------|-------------|
| 早期 | +0.400R 强 | +0.178R |
| 晚期 | +0.314R 弱 | +0.116R |

报告"mid 在 2023-11 后由强转弱、属 regime 现象"叙事失败 —— 新数据下 mid 在两期都是最弱，**mid 弱化已是结构性，不再是 regime 偏倚**。

## 行动结论保留

报告"不要按 conf=mid 过滤"、"不在 h=opp 场景再用 conf"——重跑数据下这两条结论加强。

## 代码

`tools/repro_confidence_reversal.py`，输入 `data/review/rr_b_*.csv`，按 confidence_band ∈ {low/mid/high} 切片。
