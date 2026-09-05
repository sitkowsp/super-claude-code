# super-claude-code · `council`

You have several AI subscriptions and one repo. `council` is a Claude Code plugin plus a small MCP
server that lets Claude Code plan, delegate, review and merge while other providers' models (Codex,
GitHub Copilot, Gemini, Ollama, a cheap Claude) execute disjoint tasks in parallel, each in an
isolated copy of your repo.

**Status: Phase 1 (dispatch).** Working today, verified end-to-end with Codex and a local Ollama
model: plan task cards → dispatch to executors → watch REPORT.md → snapshot commits on
`council/<id>` branches → `blocked` → answer → resume → `review`. Review and merge are still
manual (Claude does them in chat); automated reviewer/integrator subagents are Phase 2.
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
  - `npm i -g @google/gemini-cli`
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

## Configuration

`.council/council.json` — schema in `council_mcp/config.py`, example in `templates/council.json`.
No secrets in the file; use `${ENV_VAR}`. Routing: a task goes to the first model in
`by_role[role]` that is also in `by_privacy[privacy]` and passed the probe. `local-only` tasks never
leave your Ollama.

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
