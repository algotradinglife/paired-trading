---
name: feedback-codex-review-after-fix
description: Always run codex review after completing any fix or feature implementation
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3c6bc7f2-4594-4d16-89a0-0cb59a248533
---

After completing any fix or implementation, always run a codex review before reporting done.

**Why:** User explicitly requested this as a default workflow step — catches issues the author misses.

**How to apply:** After committing changes, run:
```bash
codex review --base <last-reviewed-commit>
```
Address any P1/P2 findings before moving on. P3 findings should also be fixed unless trivial. Report codex verdict to user as part of the completion summary.
