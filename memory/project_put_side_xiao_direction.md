---
name: put-side-xiao-direction
description: Put 侧重新立项——按肖式权利金空间风险几何验证，不走 PA top 镜像老路；数据补完在另一台服务器，代码将迁移
metadata: 
  node_type: memory
  type: project
  originSessionId: d57576d7-7a7f-4dc8-950a-32c56cc8f1d9
---

2026-06-10 用户披露：选择"标的找顶底 + 浅虚 naked call/put"方向源于肖老师实战（CN 期货为主，**她偏重 put**），其学生精通此道。因此 put 侧不挂起，重新立项。

关键区分：[[project_retired_and_historical]] 里 PA TOP 三机制 K=3 全 REJECT 仍然成立，但那是在**标的 R 空间**（结构止损、-1R full stop）的否决。肖式 put 的风险几何完全不同：飞天止损只有期权 K 线几个 tick（见 [[project_ag_options_swing_findings]]），低胜率靠凸性赔付。标的 R 空间负 EV 的信号在权利金空间可以正 EV。**验证 put 必须直接在期权权利金空间建 harness，不要再用标的 R 空间回测否决它。**

品种逻辑反转：cu/rb call 负 EV 的原因是缺上涨偏态（[[project_ddline_options_findings]]）——同一事实提示工业品/黑色/化工可能是 put 候选；ag/au 的上涨偏态对 put 是逆风。

基础设施状态：详尽期权数据补完在**另一台服务器**进行（WSL，见 repo MIGRATION.md），本项目代码将迁移过去。put 研究对回填数据的要求：put 合约链、全 strike 链、15min 或更细（tick 级止损模拟）、bid/ask（几 tick 止损在价差噪声量级内）、品种扩到工业品。

肖的机制链（2026-06-10 用户口述，待视频/实盘截图确认细节）：
1. **信号层**：标的 MACD 顶背离/底背离（注意：repo 退役的 classical divergence detector 在此重新成为信号源——退役只针对标的 R 空间 emit lane，迁移时勿删该机器）
2. **结构层**：她自定义的走势结构 1B/2B/3B 划分（未形式化；疑似类缠论买卖点分级，待确认）
3. **执行层**（两条路径）：左侧 = DD 线（repo 已实现为期权 K 线 W 底回踩：反弹≥10% 后回踩初始低点 ±3 tick，止损"一滴不剩"几个 tick，见 `analyze_ag_options_ddline.py`）；右侧 = 标的破趋势线（repo 无趋势线检测，需新建）
4. **期权腿**：浅虚 naked call/put

关键架构理解：背离只是 alert（低精度可接受，符合 [[project_signals_are_posterior]]），真正的风险几何由执行层提供（tick 级权利金止损 / 趋势线破位确认）。两条执行路径可在权利金空间 harness 里 A/B。

用户将提供肖的视频和实盘截图用于机制提取。
