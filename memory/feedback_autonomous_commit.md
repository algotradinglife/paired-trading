---
name: autonomous-commit
description: "User delegates commit decisions to Claude — commit autonomously when a logical unit is complete, without waiting for instruction"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4f102adb-fbb4-4528-950c-8149a46bb51b
---

Commit autonomously when all four conditions are met:
1. Logical unit (feature/fix/refactor) is complete and validated
2. Code is not temporary debug or intermediate state
3. Conventional commit format: `feat/fix/chore/docs: English short description`
4. Appropriate granularity — one coherent change per commit, not micro-commits or giant batches

**Why:** User explicitly delegated commit timing decisions on 2026-06-05 to keep momentum without waiting for instruction.

**How to apply:** After each logical completion (new script works, bug fixed, analysis done) — just commit. No need to ask.
