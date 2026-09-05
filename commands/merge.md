---
description: Merge approved council branches into the base branch, in id order
argument-hint: [T-001 T-002 ...]
---

Delegate to the `council-integrator` subagent with the ids from $ARGUMENTS (or none for all
approved tasks). Show its report. If a merge conflict or gate failure is reported, stop and ask the
user how to proceed.
