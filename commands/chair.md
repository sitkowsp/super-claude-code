---
description: Show or change the chair setup — who drafts plans / summarises reviews for Claude, and whether Claude (Fable) codes
argument-hint: [show | coder fable | coder executors | plan-assist codex | plan-assist off | review-assist codex | review-assist off]
---

Arguments: $ARGUMENTS

- No arguments or `show`: call `council_setup` (no options) and print the `chair` line plus one sentence
  per option explaining what it does.
- `coder <name>`: call `council_setup(coder=<name>)`. `fable` = Claude Fable 5.1 via `claude -p --effort medium`
  codes `implement`/`refactor` tasks first; `executors` = default (Codex GPT-6 Astra first).
  Warn once: Fable as coder spends the user's own Claude usage window; the budget warning will
  fire earlier.
- `plan-assist <model|off>`: call `council_setup(plan_assist=...)`. When on, `/council:plan` first asks
  that model for a draft of the task cards (`council_plan(goal=..., draft=true)`); Claude validates and
  the user approves before anything is saved.
- `review-assist <model|off>`: call `council_setup(review_assist=...)`. When on, `council_review` includes
  `assistant_review` — a 12-line summary from that model; the verdict stays with Claude.

Print the resulting `chair` line and remind: the setting is per project (`.council/council.json`),
takes effect immediately (no restart), and `/council:doctor` shows it.
