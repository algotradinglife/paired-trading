---
name: project-vcs-jj
description: 这个项目用 jj (Jujutsu) 做版本管理，禁止直接用 git 命令做日常操作
metadata: 
  node_type: memory
  type: project
  originSessionId: 21670370-30ce-49e7-a9d4-6a2653ae09d9
---

paired-trading 仓库**用 jj (Jujutsu)** 做版本管理，与 git 共置（colocate 模式）。

**Why:** 用户的 global CLAUDE.md 第 2 条明确："默认使用 jj 进行版本控制 ... 不要在 jj 项目里用 git 直接操作"。用户在 2026-06-08 对话中第二次提醒（第一次是 global CLAUDE.md，第二次是这条直接反馈），说明这是硬规则。

**How to apply:**

日常操作必须用 jj，不要再用 `git commit / git add / git push`：

| 任务 | 对的命令 | 错的命令 |
|------|---------|---------|
| 看状态 | `jj st` | ~~git status~~ |
| 看 log | `jj log` | ~~git log~~ |
| 写 commit message | `jj describe -m "..."` | ~~git commit -m "..."~~ |
| 开始新变更 | `jj new` | ~~git checkout -b~~ |
| 推送到远端 | `jj git push` | ~~git push~~ |
| 看 diff | `jj diff` | ~~git diff~~ |

工作流模式：
- 每个逻辑变更先 `jj new`（创建空的 working copy change）
- 改文件、加 staging（jj 不需要单独 add，文件改动自动包含）
- `jj describe -m "..."` 设 commit message
- `jj git push` 推上去（jj 会自动同步 git refs）

特殊情况：
- 钩子绕过：本项目仍用全局 git pre-commit hook（黑名单 dirs / path literals 等检查）。jj 不会直接触发 git hooks——但 `jj git push` 会通过 git，所以会触发 pre-receive 一类的服务端 hook。客户端 pre-commit 检查可能要走 `jj git push --no-verify` 或在 `jj describe` 之前手动跑检查（待实测，先按正常流程跑，遇到问题再说）
- 真要看 git 内部状态可以 `git log` 等查询命令，但**禁止 commit / push / branch 等写操作**
- 已知例外：本项目 .git/ 是 colocated 的、`jj` 通过 .jj/ 管理，两者共享对象库

补充说明：
- 当前 main 分支 bookmark 已通过 `jj bookmark track main --remote=origin` 启用追踪
- 当前 working copy change id 不稳定（每次 amend 都换 id），但 commit 在 git 侧的 SHA 稳定

**混提交防护（2026-06-12 教训）：`jj describe` 前必须先 `jj st` 核对文件清单。**
jj 自动快照会把用户/其他 session 的在途改动卷进当前 change —— 2026-06-12
把用户的 attribution 改动（+174 行）混进了我的 coverage-script 提交并 push。
若发现外来文件：用 `jj split <我的文件> -m "..."` 拆分后再 describe/push。
