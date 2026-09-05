# super-claude-code · `council`

You have several AI subscriptions and one repo. `council` is a Claude Code plugin plus a small MCP
server that lets Claude Code plan, delegate, review and merge while other providers' models (Codex,
Antigravity/Gemini, GitHub Copilot, Ollama, a cheap Claude) execute disjoint tasks in parallel, each in an
isolated copy of your repo.

**Status: Phase 3a — first real epic shipped.** A one-page business-card website was built by
three executors (Codex: logos and PNGs, Copilot: copy from public registry data, Antigravity:
the page), each reviewed and merged through the MCP tools; two adapter bugs found on the way are
fixed and recorded in DESIGN.md §19.16.

**Pipeline status.** Verified end-to-end with Codex and a local Ollama model: plan task cards →
dispatch → watch REPORT.md → snapshot commits on `council/<id>` → `blocked` → answer → resume →
`review`. Review (gates + diff + verdict), merge (rebase, `--no-ff`, after-merge gates, MEMORY.md)
and the reviewer/integrator subagents exist and are unit-tested; the live review→merge run is next.
See [DESIGN.md](DESIGN.md) — the single source of truth (§19.9 is the plan).

## How it works

```
Claude Code ──/council:plan──▶ task cards (.council/tasks/T-001.json)
            ──/council:run───▶ council-mcp: branch council/T-001
                                           worktree .council/worktrees/T-001  (owned by council-mcp)
                                           workdir  .council/work/T-001      (executor's copy: no .git, no secrets)
                                           executor process (codex / copilot / gemini / ollama loop / claude -p)
executor ──── REPORT.md ─────▶ watcher: parse → enforce scope → copy back → snapshot commit → events.jsonl
Claude   ◀── /council:status ── board + new events;  blocked? ──/council:answer──▶ ANSWER.md, re-dispatch
Claude   ── review branch, merge (Phase 2 automates this)
```

Executors never touch git and never see files matching `never_share`. Files outside a task's
`scope` are never copied back (`scope_violation`). Everything an executor writes is data, not
instructions.

## Requirements

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) on PATH; git
- Claude Code
- At least one executor:
  - Ollama (local or remote) with a tool-capable model (`qwen3:8b` works on a laptop)
  - `npm i -g @openai/codex` (ChatGPT subscription; `codex login`)
  - `npm i -g @github/copilot` (Copilot subscription; authenticates via `gh auth login`)
  - **Antigravity CLI** `agy` (Google account; the successor to Gemini CLI for individuals — install
    from https://antigravity.google, run `agy` once to log in). Gemini CLI itself now needs an API key.
  - `claude` itself as a cheap executor (`claude -p --model haiku`)

## Quick start

```bash
git clone <this repo> && cd super-claude-code && uv sync
cd /path/to/your/project
uv run --directory /path/to/super-claude-code council init      # writes .council/, .mcp.json
uv run --directory /path/to/super-claude-code council doctor    # probes models, validates config
```

Edit `.council/council.json` (models, routing, `never_share`), set `COUNCIL_OLLAMA_URL` in
`.mcp.json` if you use Ollama, open the project in Claude Code and try:

```
/council:ask codex "review council_mcp/config.py for pydantic mistakes" --files council_mcp/config.py
/council:plan add a --json flag to the CLI and document it
/council:run
/council:status
```

## MCP tools

| Tool | Purpose |
|---|---|
| `council_models` | configured models, availability (probed at start), roles, privacy |
| `council_ask(model, prompt, files?)` | one-shot question; files inlined, `never_share` refused |
| `council_probe` | re-run the availability probe |
| `council_plan(tasks)` | validate cards (disjoint scope, routing, never_share) and save them |
| `council_dispatch(ids?)` | start queued tasks: branch + worktree + workdir + executor |
| `council_status(task?, report?)` | board, new events, per-task detail, diff stat, full report |
| `council_answer(task, text, remember?)` | answer a `blocked` task and resume it |
| `council_cancel(task)` | kill the executor, mark failed, keep worktree |
| `council_review(task)` | review package: card, report, flags, diff, `before_review` gate results |
| `council_verdict(task, ok, reason)` | `review_ok`, or reject → reason becomes ANSWER.md, attempt+1, re-dispatch |
| `council_merge(ids?, force?)` | rebase + `merge --no-ff` in id order, `after_merge` gates, MEMORY.md line, cleanup |
| `council_handoff(text)` | write `.council/HANDOFF.md` for the next session |
| `council_defect(task, description, lesson?)` | record a post-merge defect: demotes the model's trust, adds a lesson |
| `council_stats` | per-model stats and trust (`probation` → `standard` → `trusted`), LESSONS.md tail |
| `council_why(task)` | the task's history with every automatic decision and its reason |
| `council_compare(prompt, models?, files?)` | same question to several models in parallel (bug-hunt, research) |
| `council_playbooks(goal?, playbook?)` | list playbooks and pick the pattern for a goal (deterministic) |

## Who does what (default routing)

| Work | role | goes to |
|---|---|---|
| code, refactors | `implement`, `refactor` | Codex → Antigravity → Copilot → local |
| icons, logos, buttons, illustrations, diagrams (SVG/CSS/HTML; **PNG/JPG via Codex or Antigravity**) | `assets` | Codex → Antigravity → Copilot |
| documentation | `docs` | Copilot → Antigravity → cheap Claude → local |
| review, second opinion, chores | `review`, `chores` | **local Ollama first** (free tokens) → cloud |
| company data | `data` | local only |

Raster images: Codex CLI (ChatGPT login) and Antigravity CLI (Google login) both have built-in image
tools — verified live, see `docs/research-*.md`. Both save to their own scratch folder by default, so
the task prompt names the workdir explicitly. Copilot CLI has none. Override any card with `assigned_to`.

## Trust, lessons, playbooks

Every model starts on **probation**: small cards, a second opinion is required, merge only after
review. Three first-pass approvals promote it; two consecutive rejections demote it; a defect found
after merge (`/council:defect`) always demotes. State lives in `.council/stats.json`.

Every rejection carries a one-line **lesson** (`.council/LESSONS.md`); the last ten lessons for that
model and role are injected into its next TASK.md. Executors can raise `dissent: true` in a report
when they object to the contract itself — that goes to you, not to another model.

**Playbooks** (`playbooks/*.json`, override in `.council/playbooks/`) tell the planner how to split
work: `feature` (default), `bug-hunt` (split hypotheses, `/council:compare`, Claude fixes),
`data-internal` (everything local-only). Selection is keyword-based and explained.

## Configuration

`.council/council.json` — schema in `council_mcp/config.py`, example in `templates/council.json`.
No secrets in the file; use `${ENV_VAR}`. Routing: a task goes to the first model in
`by_role[role]` that is also in `by_privacy[privacy]` and passed the probe. `local-only` tasks never
leave your Ollama.

Gates (`gates.before_review`, `gates.after_merge` in council.json) are shell commands run in the
task worktree before review and on the base branch after merge; results land in
`.council/reports/<id>/gates-*.json`.

Budget per task: 20 min soft / 25 min hard, 30 agent turns (Ollama). A task that ends without a
final `done|blocked|failed` report is `failed: no_final_report`.

## Development

```bash
uv sync
uv run pytest -q                 # respx / fake adapters; no live models
uv run ruff format . && uv run ruff check .
uv run mypy
```

CI (`.github/workflows/ci.yml`) runs the same gates on Ubuntu and Windows. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT. Company-specific profiles and examples live outside the core (`profiles/`, `examples/`).
