---
description: Merge approved council branches into the base branch, in id order; --reconcile closes tasks already merged by hand
argument-hint: [T-001 T-002 ...]
---

Delegate to the `council-integrator` subagent with the ids from $ARGUMENTS (or none for all
approved tasks). Show its report. If a merge conflict or gate failure is reported, stop and ask the
user how to proceed.

If `--reconcile` is in $ARGUMENTS (or the user says the changes were already merged by hand),
call `council_merge(ids?, reconcile=true)` instead: it closes review tasks whose branch content
is byte-identical on the base branch (no gates, no commits, savings not counted) and reports the
rest as skipped with the reason. Suggest it whenever a review task's diff against base is empty
because the chair merged manually.
