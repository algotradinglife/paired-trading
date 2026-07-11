# PA / Feitian M6：30% premium stop 候选对比

结论：数据质量恢复后，baseline 与候选的四个事件均为 `observed`，可生成完整的 matched-event / OOS 描述性比较。由于候选属于 `retrospective_exploratory`，screening 强制为 `inconclusive`，不得晋级 M7、调整生产策略或作收益推断；reviewer status 保持 `pending`。

候选仅改变 exit policy：long option 的 stop 从入场 premium 的 50% 改为 30%；2× target、10 个 daily bars、two-tick slippage、gap 处理和同 bar 歧义语义均保持不变。该声明是回溯探索，不是前瞻预注册，也不改变 M4 决策或 M5 baseline。

| 指标 | Baseline | Candidate | 解读 |
| --- | ---: | ---: | --- |
| 记录数 | 4 | 4 | 输入信号相同 |
| observed | 4 | 4 | `ag2608c18800` 数据路径已恢复 |
| data_blocked | 0 | 0 | 四条结果均有有效 outcome |
| pooled mean premium R | -1.00090361445 | -0.841500172225 | 描述性差值 +0.159403442225 |
| premium-R win rate | 0.0 | 0.0 | 两者均无正 R observed event |
| paired effective events | — | 4 | 四个 event_id 完整匹配 |
| comparable OOS windows | — | 2 | `wf_1` +0.6376137689；`wf_2` 0 |
| adjusted bootstrap CI | — | [0, 0.4782103267] | 描述性回溯区间，不支持晋级 |
| screening | — | inconclusive | 强制 no-promotion；不得进入 M7 |

候选四个 observed outcome 中，三个为 `premium_stop`（R = -1），一个为 `time_exit`（R = -0.3660006889）。与 baseline 的逐事件 premium-R 差值为 `0`、`+0.6376137689`、`0`、`0`；中位数差值为 `0`。

Policy comparison contract 通过显式 `registration_mode` 区分 `prospective` 与 `retrospective_exploratory`：晚注册的 prospective 配置继续 hard block；回溯探索配置可以保留完整配对与 OOS 描述性指标，但 classification 永远不能成为 `promising` 或 `negative`，并显式记录“cannot advance M7”。

新 hash-pinned 证据与 dashboard copies 位于 [data-quality recovery packet](../../doc/repro/pa-feitian-m6-data-quality-recovery-2026-07-11/README.md)。旧 M5 与旧 M6 packets 保持不变。
