---
description: Claude accounts for claude -p executors — add a second profile, verify logins, see fallback chains and how to switch the chair session
argument-hint: [add <name> | verify | remove <name>]
---

Arguments: $ARGUMENTS

- No arguments: call `council_accounts()`; print `table`, `fallback_chains` and `switch_hint`.
- `add <name>`: call `council_accounts(add=<name>)`. Print the `added.login` command **for the user to
  run in a terminal** (it opens a browser; the user picks the organisation there — never ask for or
  type credentials). Explain that `<model>-<name>` copies of the Claude executors were created,
  disabled, and placed first in the fallback chain; after logging in the user runs
  `/council:accounts verify`.
- `verify`: call `council_accounts(verify=true)`; print which models got enabled and the table.
- `remove <name>`: call `council_accounts(remove=<name>)`; print what was removed.

Always end with the one-line `policy_note` (several accounts to bypass usage limits may violate
Anthropic's usage policy; Team seats in different orgs each have their own allowance — the user and
their admin decide). The chair session itself cannot switch accounts; `switch_hint` is the recipe.
