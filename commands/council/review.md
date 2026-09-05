---
description: Review council tasks that reached state `review` (runs gates, reads the diff, gives a verdict)
argument-hint: [T-001 T-002 ...]
---

For each task id in $ARGUMENTS (or every task in state `review` per `council_status`), delegate to
the `council-reviewer` subagent with the task id. Collect verdicts and show a table: id, verdict,
one-line reason. Rejected tasks are already re-dispatched; approved tasks wait for `/council:merge`.
