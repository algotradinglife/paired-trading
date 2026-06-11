# score_today US 日评输出质量审查（2026-06-11，WSL 迁移后）

审查对象：`score_today.py --pool US --window-days 30`，新数据层（quant-cli
store，SPY/QQQ/IWM）。窗口内 1 条信号：IWM 2026-05-15 context_a bottom，
conf 0.60，score 3，pos half，invd 236.30。

## 健康项 ✅

- 管线端到端正确：seam → detector → policy → scorecard 全链路在新数据上
  工作；信号密度与 5 年回放吻合（context_a IWM n=29/5y ≈ 0.5 条/月）。
- 缺失标的优雅跳过（11/14 不在库），JSON 兜底逻辑保留。
- 结构止损机制正确：236.30 = 最近 HL pivot 238.69（2026-03-30）× 0.99，
  符合用户锁定的"止损架在支撑线附近"规则。
- DIR weekly_trend 有 daily 重采样兜底（US 无 W 数据时降级而非失效）。

## 问题与观察 ⚠️

| # | 发现 | 性质 | 建议 |
|---|------|------|------|
| 1 | **context_a 无 DIR 注释**：记录无 direction_* 字段。STATUS 已记录 context_a/vflush/bpull/pa_h2_climax 未接 DIR，但 context_a 在本机是 US 最活跃 lane（30 天唯一信号即出自它）——"信号必带多周期宏观"方法论在当前主输出上落空 | 已知 wiring 缺口，迁移后变 material | **建议下一个策略任务**：context_a 接 DIR（纯代码，数据无关）|
| 2 | minute15_state 在 US 全降级（无 15min 数据，加载返回 None）| 数据缺口（已记录转 pipeline）| 等 15min 回填；或接受 8 源里少 1 源 |
| 3 | 该 context_a 止损距离 −14.9%（pivot 距信号 2.5 个月）| 机制如设计，但 R 定距下"half"仓位的实际风险敞口偏大 | 观察项；与 STATUS followup #11（position sizing 重做）合并考虑 |
| 4 | 每次运行 11 条 missing-data 告警噪音 | 外观 | 池定义保留全 14 标的是对的（缺口可见性）；可考虑汇总成一行 |
| 5 | iso/15m 列全空（仅 pa_h2 填充）| STATUS followup #7 已知 | 不动 |

## 结论

输出可用于日常 US 评估，机制无错误。最有价值的数据无关后续工作是 #1
（context_a 接 DIR）。SPY 相关任何输出在数据洞回填前不可信
（见 `us_backtest_post_migration_2026-06-11.md`）。
