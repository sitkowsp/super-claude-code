---
description: Answer a blocked task and resume it
argument-hint: <T-001> <answer text> [--remember]
---

Arguments: $ARGUMENTS. First token is the task id, the rest is the answer. Call `council_answer`
(`remember: true` if `--remember` was given, which also records the answer as a project decision
in MEMORY.md). Confirm the task is running again.
