---
name: reference-codex-cli
description: codex CLI 本地可用 (/opt/homebrew/bin/codex)，可直接通过 Bash 调用做代码审查，无需 MCP 或 paste-able 包
metadata: 
  node_type: memory
  type: reference
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

**事实**：本机装了 `codex` CLI（`/opt/homebrew/bin/codex`），登录态保留在 `~/.codex/`。在 macd-momentum project 里通过 Bash 直接调用即可触发 Codex 评审，**不需要** MCP 服务也不需要写 paste-able 评审包。

**常用命令**：
- `codex review --uncommitted` — 审 working tree 未提交的改动（最常用，pre-commit review）
- `codex review --commit <sha>` — 审某个 commit
- `codex review --base <branch>` — 审一个 branch 相对 base
- `codex exec "prompt"` — 通用非交互调用，把 prompt 传进去
- `codex review --help` — 看全部参数

**重要约束**：
- `codex review --uncommitted` **不能**和 PROMPT 参数同时用（CLI 校验拒绝）。要附加指引只能走 stdin 或拆成 `codex exec`。
- 调用是真的对外发请求，会消耗 token + 走网络。typical review 跑 30-60 秒。

**典型工作流**（pre-commit review）：
```
1. 写改动
2. `cd <repo> && codex review --uncommitted`
3. 看 verdict，修问题
4. 重跑 `codex review --uncommitted` 直到 LGTM
5. `jj describe -m "..."` + `jj new`
```

**Why this matters**：早先 R4 + Layer 9 阶段我以为没 Codex 接入，写了大量 `doc/codex-review-*-pasteable.md` 包让用户手动粘贴。实际 CLI 一直可用。后来 Layer 9 三连 (P1-P3) 改用 `codex review --uncommitted`，P1 一次 review 就抓出 4 个真问题（包括 markdown line-wrap 把 `context_topology` 在 rendered 里断成 `context_ topology` 这种我自己审不出来的细节）。

**How to apply**：
- 任何 pre-commit pre-flight 不用再写 paste-able 包，直接 `codex review --uncommitted`
- 复杂场景（要给 codex 额外上下文）改用 `codex exec` + stdin
- 如果未来 codex CLI 不可用了，回退到 paste-able 包模式（参考 `doc/results-review-round4-pasteable.md` 是历史范式）
- 不要默认信 codex verdict 是 ground truth — 它也会漏（比如 P1 第一轮没注意到 instrument_class vs context_topology 混淆，第二轮才提）。多跑几轮直到 LGTM。
