---
name: strategy-repo-boundary
description: paired-trading 是策略 repo，数据回填/修复是 data-pipeline (quant-cli) 的职责 — 发现数据问题只记录上报，不自己跑 sync/探针
metadata:
  type: feedback
---

paired-trading 不负责数据回填或数据修复。数据层（覆盖缺口、主连可用性、
格式问题）归 data-pipeline（~/workspace/quant, quant-cli）管。

**Why:** 2026-06-11 WSL 迁移时我提议自己跑 `quant sync` 探针验证 cu0 主连
可用性，用户明确纠正：「这不是你的事……你不需要自己去跑探针，也不需要
关心当前有没有 sync 在跑。」职责分离 — 策略 repo 消费数据契约，不操作
数据管线（minishare 还是单进程，并发会撞别人的 sync）。

**How to apply:** 发现数据缺口/疑点 → 写一份记录文档（如
`doc/data_gaps_*.md`）或直接报给用户转 data-pipeline，然后继续做不被
该数据阻塞的策略工作。永远不要在这台机器上主动运行 `quant sync` 或向
数据存储写入。相关：[[put-side-xiao-direction]]（数据补完本来就排在
data-pipeline 侧）。
