# Obsidian as the project mastermind

Council keeps everything that matters as Markdown: decisions (`MEMORY.md`), the note for the next
session (`HANDOFF.md`), lessons per model (`LESSONS.md`), the board (`TASKS.md`), every executor
report and every task card. Obsidian is the natural place to read, link and search that — and, with
the Claudian plugin, to talk to Claude about it from inside the vault.

## What works today (Phase A)

- **Detection.** `council doctor` and the SessionStart hook read Obsidian's own vault list
  (`%APPDATA%\obsidian\obsidian.json` on Windows, `~/Library/Application Support/obsidian/` on
  macOS, `~/.config/obsidian/` on Linux). A vault that already contains your repo is preferred;
  otherwise the currently open vault. They also report whether the **Claudian** plugin is installed
  (community id `realclaudian`, or the `oh-my-claudian` fork — matched on the plugin manifest id).
  Claudian embeds the Claude Agent SDK and runs Claude Code with the vault as working directory,
  so Claude Code plugin agents and the council MCP server are usable from inside Obsidian
  (details: `research-obsidian-claudian-2026-09.md`).
- **Mirror.** `council_obsidian(mirror=true)`, `council obsidian --mirror`, and automatically after
  `council_plan`, `council_merge` and `council_handoff`: council writes
  `<vault>/Council/<project>/` with `MEMORY.md`, `HANDOFF.md`, `LESSONS.md`, `TASKS.md`,
  `REPORT-*.md`, `reports/<id>/…`, and one note per task in `tasks/T-001.md` with YAML
  frontmatter (`council_task`, `state`, `role`, `model`, `attempt`, `tags`) plus a README with a
  Dataview table. If the repo lives inside the vault, only an index note is written — the
  `.council/` notes are already there.
- **Config** (`.council/council.json`):

```json
"obsidian": {"vault": null, "folder": "Council", "mirror": true, "read_context": []}
```

`vault: null` = auto-detect; set an absolute path to pin one. `mirror: false` turns it off.

## If you do not have Obsidian or Claudian

Council works without them. `council doctor` prints a one-line suggestion:
install Obsidian (https://obsidian.md), open or create a vault, and add the community plugin
**Claudian** to chat with Claude Code inside the vault. Without Claudian you still get the mirrored
notes, links and Dataview boards.

## Phase B — proposal (DESIGN.md §20)

1. **Vault as planning context.** `obsidian.read_context` lists vault notes (specs, ADRs, meeting
   notes) that `/council:plan` reads before writing cards; the planner cites which note drove which
   card. Notes tagged `#council/spec` under `Council/<project>/` are picked up automatically.
2. **Decisions flow both ways.** A `## Decisions` section in the vault project note is merged into
   `MEMORY.md` on plan (vault wins on conflict, with an event `memory_from_vault`).
3. **Blocked questions as notes.** Each `blocked` creates `Council/<project>/inbox/T-007.md` with
   the question and a `answer:` field; when a human fills it in Obsidian, the SessionStart hook
   turns it into `council_answer`. This is the `/council:inbox` from the design, in a vault.
4. **Claudian commands.** Ship a Claudian command set (`/council status`, `/council plan`) that calls
   the same MCP server, so Obsidian becomes a second orchestrator seat with the same audit trail.
5. **Graph.** Task notes link to touched files (`[[src/x.py]]` when the repo is in the vault) and to
   the model's lessons — the graph view shows which model touched what and where lessons cluster.

Deliberately not planned: writing into the vault from executors (they never see it), and any
Obsidian sync/cloud dependency.
