---
description: Hand the remaining work of this session to other models (use when Claude's usage window is running out)
argument-hint: [what is left to do]
---

Claude's 5-hour usage window is the scarce resource. Call `council_budget` and `council_status`.
Then turn everything that is not yet done — from $ARGUMENTS, the current plan, open TODOs in the
conversation — into task cards: `implement`/`docs`/`assets`/`chores` cards for executors, disjoint
scope, acceptance commands, `depends_on` where needed. Keep for Claude only: contracts already in
flight, the final review and merge. Show the cards, get "ok", call `council_plan` then
`council_dispatch`. Finish with `council_handoff` so the next session (possibly after the window
resets) can pick up with `/council:review` and `/council:merge`.
