---
description: Stop a running council task (keeps its worktree for inspection)
argument-hint: <T-001>
---

Call `council_cancel` with the id from $ARGUMENTS. Confirm the final state and remind the user that
the branch `council/<id>` and `.council/worktrees/<id>` are kept.
