---
description: Install missing executor CLIs (npm) and list the logins still needed — no terminal required
argument-hint: [--install]
---

Call `council_setup` with `install: true` if `--install` is in $ARGUMENTS, otherwise `install: false`
(dry run). Show the executor table, then the install commands (run for the user when installing,
listed otherwise), then the logins still needed — one line each with the exact command, and say
that logins open a browser and must be done by the user. Finish with: "restart Claude Code after
installing CLIs so the new PATH is picked up", then suggest `/council:doctor` to verify.
