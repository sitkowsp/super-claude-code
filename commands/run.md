---
description: Start queued council tasks
argument-hint: [T-001 T-002 ...]
---

Call `council_dispatch` with ids from $ARGUMENTS (or none to start every queued task).
Reply with one line per started task: id, model, branch. Then tell the user that
`/council:status` shows progress and that you will react to `blocked` reports.
