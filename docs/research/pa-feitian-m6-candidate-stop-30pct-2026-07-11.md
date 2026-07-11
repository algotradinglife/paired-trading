# PA / Feitian M6：30% premium stop 候选对比

结论：候选未获比较资格，状态为 `blocked`；不得据此调整策略、进入 M7，或作任何收益推断。

候选仅改变 exit policy：long option 的 stop 从入场 premium 的 50% 改为 30%；2× target、10 个 daily bars、two-tick slippage、gap 处理和同 bar 歧义语义均保持不变。该声明是回溯探索，不是前瞻预注册，也不改变 M4 决策或 M5 baseline。

| 指标 | Baseline | Candidate | 解读 |
| --- | ---: | ---: | --- |
| 记录数 | 4 | 4 | 输入信号相同 |
| observed | 4 | 3 | 候选第四条在更长 traversal 内出现无效 OHLC |
| data_blocked | 0 | 1 | 不可用结果没有被填补 |
| pooled mean premium R | -1.00090361445 | -0.7886668963 | 不可配对，不能作为相对改善 |
| premium-R win rate | 0.0 | 0.0 | 两者均无正 R observed event |
| paired effective events | — | 0 | screening 拒绝使用不同 observed-event 集合 |
| screening | — | blocked | 无排名、无 CI、无晋级 |

候选三个 observed outcome 中，两个仍为 `premium_stop`（R = -1），一个为 `time_exit`（R = -0.3660006889）。第四个 `ag2608c18800` 为 `data_blocked`，因此控制比较若只保留另外三条会事后选择 outcome；系统明确拒绝该操作。

Failure-mode report 同时记录了：受控比较 blocked、一个 data-quality blocked、两个 premium-stop exit，以及一个 time-exit。Dashboard copies 已输出至 [candidate recovery packet](../../doc/repro/pa-feitian-m6-candidate-recovery-2026-07-11/README.md)。

下一步只能是恢复第四条候选路径在完整固定持有窗口内的有效 daily OHLC，并从固定的同一 policy 重跑；在此之前，M6 结果保持 blocked。
