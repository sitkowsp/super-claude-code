---
description: Estimated Claude tokens saved by delegating to the council, per model and for the assistants (heuristic)
argument-hint: [--backfill]
---

Call `council_savings` with `backfill: true` if `--backfill` is in $ARGUMENTS (counts tasks merged
before the estimate existed, from their merge commits), otherwise `backfill: false`. Print the
`markdown` field as-is (headline number, per-model table, method line). Then one sentence: this is a
documented heuristic (base per merged task + per changed line by role; fixed values for a plan draft
and a review summary), not a measurement — the CLIs do not report tokens and Claude's own review and
merge tokens are not subtracted. The same numbers are in `council report`, the Obsidian note
`Council/<project>/Savings.md`, and the SessionStart line.
