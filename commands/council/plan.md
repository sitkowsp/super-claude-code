---
description: Split a goal into disjoint task cards for other models (nothing runs until /council:run)
argument-hint: <goal>
---

Goal: $ARGUMENTS

1. Read `.council/MEMORY.md` (if present) and the relevant parts of the repo.
2. Call `council_models` to see which executors are available and their roles/privacy.
3. Design 1–4 task cards with **disjoint `scope`** (globs the executor may change), read-only
   `context_files`, a one-sentence `goal`, checkable `acceptance`, `role` and `privacy`.
   Rules: `privacy: internal` if scope/context touches config, secrets-adjacent or company-specific
   paths; `local-only` if the task reads database data. Keep the seams (interfaces, integration,
   glue) for yourself — executors get self-contained leaves. Prefer `depends_on` over overlapping scope.
4. Show the cards to the user as a table and ask for "ok" or edits.
5. Only after "ok": call `council_plan` with the cards. Report the created ids and say
   `/council:run` starts them.
