# Council — the manual

Every command, where it runs, and what to do in each task state. Shorter intro:
[getting-started.md](getting-started.md); argument details: [reference.md](reference.md).

## The three places you can type commands

| Place | What it is | What works there |
|---|---|---|
| **Claude Code session on the repo** | Desktop app with the project open, or `claude` in the repo directory | Everything: all `/council:*` commands and `council_*` MCP tools. This is the chair. |
| **Claudian chat in the Obsidian vault** | The Claudian plugin runs Claude with the **vault** as working directory | Only the file-based kit: `/council-status`, `/council-answer`, `/council-decide`, `/council-handoff`. These read and write the mirrored notes — they cannot start executors, review or merge, because the council MCP server there is bound to the vault, not to your repo. |
| **Terminal (no session)** | `uv run council …` from a clone, or `uv run --directory <plugin cache> council …` | One-shot maintenance: `init`, `doctor`, `setup`, `events`, `report`, `obsidian --mirror`, `reconcile`, `savings [--backfill]`, `session-start`. No executors are started. |

Rule of thumb: **work happens in the repo session; the vault is for reading and for answering
blocked tasks; the terminal is for maintenance.** In the desktop app there is no `/plugin` dialog,
but all `/council:*` commands work in the chat box; from scripts use `claude -p "/council:…"`.

## The task lifecycle and what to do in each state

```
queued ── /council:run ──▶ running ──▶ review ── /council:review + /council:merge ──▶ merged
              ▲                │  │
              │                │  └──▶ blocked ── /council:answer (or vault inbox) ──▶ re-dispatch
              └── fallback ◀───┴────▶ failed  ── /council:why, fix the card, re-plan
```

| State | Meaning | In the repo session | In the vault (Claudian) |
|---|---|---|---|
| `queued` | Card saved, nothing runs yet | `/council:run` starts it; `/council:stop T-001` drops it | read the task note |
| `running` | Executor works in `.council/work/<id>/` | `/council:status` (board + new events); `/council:stop` kills it | watch the note change (auto-mirrored) |
| `blocked` | Executor asked a question and exited | `/council:answer T-001 <text>` — resumes with your answer as ANSWER.md | `/council-answer T-001 <text>` fills `Council/<project>/inbox/T-001.md`; the next `council_status` in the repo session applies it |
| `review` | Work done, branch `council/<id>` waits for a verdict | `/council:review` (gates + diff + verdict; a rejection re-dispatches with attempt+1, 3rd rejection = failed), then `/council:merge`. **Merged it by hand yourself?** `/council:merge --reconcile` closes it without commits | read the diff summary in the task note; verdict stays in the session |
| `merged` | Rebased + merged `--no-ff`, gates ran, MEMORY.md updated | `/council:defect T-001 <desc>` if a bug surfaces later (drops the model's trust) | read `MEMORY.md`, `Savings.md` |
| `failed` | 3 rejections, no final report, cancelled, or a real error | `/council:why T-001` explains every automatic decision; fix the card and `/council:plan` again. Quota/no-response failures re-queue on the fallback model automatically | read the task note's `reason` |

## Command reference by purpose

**Plan and run**
- `/council:plan <goal>` — split the goal into 1–4 disjoint task cards (playbook-driven); with
  `chair.plan_assist` on, an assistant model drafts the cards first. Nothing runs until you say ok.
- `/council:run` — dispatch queued cards (branch + isolated workdir + executor per card). Each card
  is complexity-scored on the way out: simple → cheaper model + `low` effort, complex → top model +
  `high` effort (`delegation.auto_effort`; `/council:why` explains the pick). A stale availability
  probe (older than `probe_ttl_hours`, default 24 h) reruns automatically first, so the model choice
  works from today's list of what each provider can run.
- `/council:status` — board, new events, HANDOFF.md; also applies answers from the Obsidian inbox.
- `/council:answer T-001 <text>` — answer a blocked task and resume it.
- `/council:stop T-001` — kill the executor, mark failed, keep the worktree for inspection.

**Review and merge**
- `/council:review [ids]` — gates in the task worktree, full diff, flags, optional assistant
  summary; verdict `ok`/reject with a one-line lesson.
- `/council:merge [ids]` — rebase + `merge --no-ff` in id order, after-merge gates, MEMORY.md line.
- `/council:merge --reconcile` — close review tasks whose content you already merged by hand
  (verified byte-identical on the base branch); counts savings from the branch diff.
- `/council:defect T-001 <description>` — record a post-merge defect (always demotes trust).

**Ask instead of delegate**
- `/council:ask <model> "<question>" [--files …]` — one-shot second opinion.
- `/council:compare "<question>" [models]` — the same question to several models in parallel.

**Configure**
- `/council:setup [--install]` — executor table; installs missing npm CLIs; lists logins needed.
- `/council:doctor` — everything: executors, chair line, tools (Blender/Unreal), Claude profiles,
  Obsidian vault, routing gaps. Start here when something is off; `council_ping` when even that fails.
- `/council:chair [coder fable|executors | plan-assist <m|off> | review-assist <m|off>]` — who
  assists the chair and who codes.
- `/council:accounts [add <name> | verify | remove <name>]` — second Claude account for
  `claude -p` executors, with automatic failover on usage limits.

**Insight and end of session**
- `/council:why T-001` — the task's history with reasons, ~10 lines.
- `/council:savings [--backfill]` — estimated Claude tokens saved (heuristic, documented method).
- `/council:analyze` — deterministic repo scan → proposed gates, privacy rule, routing notes.
- `/council:offload [notes]` — turn the rest of the session into executor cards + a handoff.
- `/council:handoff [text]` — write `.council/HANDOFF.md` for the next session.

**Vault kit (Claudian only)** — installed by `council_obsidian(kit=true)` or `council init --obsidian`:
- `/council-status` — read the mirrored board across projects.
- `/council-answer T-001 <text>` — answer a blocked task via `inbox/` (picked up by the repo session).
- `/council-decide <text>` — append to `DECISIONS.md`; merged into the repo's MEMORY.md at next plan.
- `/council-handoff` — read/extend the handoff note.

## Typical days

**Feature**: `/council:plan add CSV export` → check the cards, "ok" → `/council:run` →
`/council:status` until `review` → `/council:review` → `/council:merge`. Total chair involvement:
approve cards, read one diff summary, merge.

**Blocked while you are away**: the task note lands in `Council/<project>/inbox/` — answer it from
Obsidian on any device with `/council-answer`; the repo session applies it on its next
`/council:status` (the SessionStart hook reminds you when answers are waiting).

**You merged by hand**: the board shows phantom `review` rows → `/council:merge --reconcile`
(or `council reconcile --root <repo>` from a terminal, safe next to a live session).

**Claude window running out**: the hooks warn after ~3.5 h → `/council:offload` hands the remaining
work to executors; with a second Claude profile (`/council:accounts`) the `fable`/`cheap` executors
fail over on their own, and `council_budget.switch_hint` prints the recipe for moving your own
session to the other account.

## Where the state lives

`.council/` in the repo is the source of truth: `tasks/*.json` (cards + state), `events.jsonl`
(audit trail), `reports/<id>/` (executor reports, gate results), `stats.json` (trust + savings),
`MEMORY.md`, `LESSONS.md`, `HANDOFF.md`. The Obsidian vault under `Council/<project>/` is a mirror,
rewritten on every plan, merge, handoff **and every task state change**; `Dashboard.md` carries the
auto-maintained *Council status* block plus Dataview boards. If a Dataview table looks stale while
the auto block is current, refresh the note — the notes on disk are already right.
