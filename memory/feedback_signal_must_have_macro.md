---
name: feedback-signal-must-have-macro
description: "讨论或汇报任何信号时，必须先给出\"大方向判定\"（多周期 + 趋势结构 + 上下文多空对比），再谈信号本身"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

每次跟用户讨论或汇报具体信号——无论是 score_today 的某条记录、backtest 的某个 cell、还是设计方向时举例的信号——**必须先**给出"大方向判定"，才能再谈信号本身。

**Why:** 用户 2026-06-08 直接说："你每次讲信号时，必须伴随大方向的判定：多周期（从周线开始一直到h或者15m），走势结构是趋势（哪种趋势）或者TR，上下文的多空对比和变化是如何的。有了这些，再谈信号。" 这是肖淳心 + PA 体系的认知方式——信号脱离大方向的解读是失真的、容易误判的。

**How to apply:**

汇报任何具体信号时，模板是：

```
信号: <symbol, date, level, weight>

大方向判定:
  多周期:
    W:    <weekly 趋势状态>
    D:    <daily 趋势/结构>
    1h:   <hourly DIF / 趋势>
    15m:  <15min 状态，如果有>
  走势结构 (D): <BULL / TR / TR_FORMING / BEAR / UNCLEAR>
  上下文多空对比:
    多方力量:  <强/弱/耗竭>
    空方力量:  <强/弱/耗竭>
    近期变化:  <谁占上风、是否出现转换迹象>

信号在大方向中的位置: <顺势 / 逆势 / 转换点 / 等等>
```

只有在这个上下文里，"GDX 2026-05-22 emitted pa_us_60min weight 0.80" 才是有意义的——否则就是数字游戏。

对工程的影响：
- `pa_direction_assessment.py` 必须包含 W / D / 1h / (15m) 全多周期，不能只到 1h
- 上下文不能只是 Context A/B1，必须有 bull/bear 力量对比 + 耗竭检测
- score_today 的输出格式将来也要 reformat 成"大方向打头、信号附后"，不是现在的纯表格
- 我自己写报告 / 回答用户时也要按这个模板，不能再罗列"X symbol Y weight Z policy_rule"
