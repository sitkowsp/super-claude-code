---
description: Check executors (installed / logged in / action), Obsidian vault and config; suggest exact install and login commands
---

Call `council_doctor`. If it errors, call `council_ping` and show its output (repo root, env). Show the executor table as-is. For every row with an action, print the exact
command the user should run (install or login — logins open a browser and must be done by the
user). Report the Obsidian line and any routing warnings. If the tool itself is unavailable
(server not connected), tell the user: the council MCP server did not start — `uv` must be on the
PATH of the process that launched Claude Code (restart Claude Code after installing uv, or set
`COUNCIL_UV` to the full path of uv.exe), then run `/mcp` to reconnect.
