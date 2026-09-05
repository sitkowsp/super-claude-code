# super-claude-code · `council`

You have several AI subscriptions and one repo. `council` is a Claude Code plugin plus a small MCP
server that lets Claude Code plan, delegate, review and merge while other providers' models (Codex,
GitHub Copilot, Gemini, Ollama, a cheap Claude) execute disjoint tasks in parallel, each in an
isolated copy of your repo.

**Status: Phase 2a.** Verified end-to-end with Codex and a local Ollama model: plan task cards →
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
  - `npm i -g @google/gemini-cli` (run `gemini` once interactively and pick *Login with Google*)
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

## Who does what (default routing)

| Work | role | goes to |
|---|---|---|
| code, refactors | `implement`, `refactor` | Codex → Copilot → Gemini → local |
| icons, logos, buttons, illustrations, diagrams **as SVG/CSS/HTML** | `assets` | Codex → Gemini → Copilot |
| documentation | `docs` | Copilot → Gemini → cheap Claude → local |
| review, second opinion, chores | `review`, `chores` | **local Ollama first** (free tokens) → cloud |
| company data | `data` | local only |

Raster images (PNG/JPG) are not produced by these CLIs; that would need an image-API adapter and is
deliberately out of scope for v1. Override any card with `assigned_to`.

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
