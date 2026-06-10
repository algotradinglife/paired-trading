---
name: feedback_codex_review_default
description: 默认在生成代码、分析脚本或 HTML 报告后立即跑 codex review
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

每次生成代码、分析脚本、或 HTML 报告之后，默认立即运行 codex 审核，不需要用户单独提醒。

**Why:** 用户 2026-05-31 明确要求：生成代码、分析结果或报告时默认让 codex 审核一下。

**How to apply:**
- 生成任何 Python 分析脚本后，commit 之前先运行 `codex review --uncommitted`
- HTML 报告 commit 后，如有对应生成脚本，对脚本跑 `codex review --base <last-reviewed-commit>`
- P1/P2 问题必须修完再报告给用户
- P3 及以下酌情处理，说明理由即可
- 不需要用户每次说"让 codex 审核"——这是默认步骤

**Related:** [[feedback_codex_review_after_fix]]
