# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

`DESIGN.md` is the single source of truth. Section 0 lists closed decisions — do not reopen them; **section 19 amends some of them** (executor dir without `.git`, Grok pull mode cut) and **table 19.9 is the only authoritative phase plan** (older plan sections are history). If the implementation diverges from the doc, fix the doc in the same commit and bump its revision number. The doc is Polish; user-facing docs and README are English first.

## Repository state

Obsidian Phase B (`vault.py`: context, decisions sync, inbox, Claudian kit), `/council:analyze` (`analyze.py`), delegation policy + session budget (`policy.py`, DESIGN §22), quota/no-response fallback to `cheap` with cooldown (§23) — all done 2026-09-05, tag v1.0.0-rc1. Install/ops layer done (2026-09-05, DESIGN §21): marketplace install, SessionStart hook (`council session-start`), `council setup/doctor` with login checks (`setup.py`), privacy check in CI, Obsidian bridge Phase A (`obsidian.py`, DESIGN §20). Phase 3a done (2026-09-05): user docs in `docs/` (EN), `council report`; first real epic run through the MCP tools on `WORKSPACE/sitek-site` (business-card site: Codex assets, Copilot copy, Antigravity page). Phase 2b done: 17 MCP tools (`council_models/ask/probe/plan/dispatch/status/answer/cancel/review/verdict/merge/handoff/defect/stats/why/compare/playbooks`), `council init/doctor/events` CLI, agents `council-planner/reviewer/integrator`, `UserPromptSubmit` hook, gates, trust per model in `.council/stats.json` (§19.13), `LESSONS.md` injected into TASK.md, playbooks in `playbooks/` (+ user `.council/playbooks/`), `dissent` in reports, routing by task type incl. `assets` (§19.12). Verified live (Phase 1): Codex + local Ollama in parallel → `review`, blocked → answer → resume. Unit-tested only: merge, conflict re-dispatch, reject → attempt+1 → failed at 3. Not yet / deferred past v1.0: repo publication (user decision), `council bench/night`, profiles, `council_recall`, `/council:analyze|spec|architect|docs`, solo-vs-council estimate, remaining playbooks. Environment: `docs/probe-2026-09.md`; lessons: DESIGN §19.11.

## What this is

`super-claude-code` — a Claude Code plugin named `council` plus a Python MCP server `council-mcp` (package `council_mcp`). Claude Code plans, delegates, reviews and merges; other providers' models (Ollama on remote srv-ai, Gemini CLI, Codex CLI, Grok Build CLI, `claude -p` cheap model) execute disjoint tasks in parallel in the same repo, each in its own git worktree + branch `council/<id>`. MIT, public project; company (NUCO) specifics live only in `profiles/nuco.json`, `playbooks/merit-integration.json`, `examples/nuco-wms/` — never in the core.

## Commands

```bash
uv sync                                  # install (dev group included)
uv run pytest -q                         # all tests (respx mocks; nothing hits a live model)
uv run pytest -q tests/test_ollama.py::test_ask_retries_once_with_half_ctx_on_5xx
uv run ruff format . && uv run ruff check .
uv run mypy                              # strict; package configured in pyproject
uv run council-mcp                       # MCP server over stdio (wired via .mcp.json)
```

On this machine `uv` is not on PATH: in Git Bash prefix with `export PATH="$APPDATA/Python/Python312/Scripts:$PATH"`. Live smoke test of the local adapter needs `ollama serve` running and `COUNCIL_OLLAMA_URL=http://localhost:11434`.

Gates (same commands, run in a task worktree before review and after merge) are defined in `.council/council.json` → `gates`; output goes to `reports/<id>/gates.json`.

## Architecture (see design doc §2–5)

- **Plugin layer** (`.claude-plugin/plugin.json`, `commands/council/*.md`, `agents/*.md`, `hooks/hooks.json`, `templates/`): slash commands `/council:plan run status answer review merge stop`, subagents `council-planner`, `council-reviewer`, `council-integrator`, a `UserPromptSubmit` hook that injects a summary of new `events.jsonl` entries. Fallback if plugin format differs: same files under `.claude/` installed by `council init`.
- **MCP server** (`council_mcp/`, flat layout, no `src/`): `server.py` (`MCPServer` from `mcp` 2.x — `FastMCP` was renamed; tools `council_*`; raise `ToolError` for user-facing validation errors so Claude sees the message), `config.py` (pydantic model of `council.json`), `store.py` (TaskStore: `.council/tasks/*.json` + lock, task state machine), `scheduler.py` (asyncio semaphores: global 3, max 1 on Ollama, `depends_on` waves), `watcher.py` (polls `REPORT.md` every 2 s → `events.jsonl`), `worktree.py` (git worktree add/remove, strips `never_share` files, rebase + `merge --no-ff` in id order), `render.py` (jinja: `TASK.md`, `AGENTS.md`, `GEMINI.md`, Ollama system prompt), `probe.py` (detects CLI flags from `--help` → `.council/capabilities.json`; adapters never hardcode flags), `adapters/` (`Adapter` protocol `probe/ask/run`; `ollama.py` HTTP + agent loop with confined tools; `cli.py` one generic subprocess adapter for codex/antigravity(`agy`)/copilot/gemini/grok/claude-sub — approval flags chosen from probed `--help`, never hardcoded; `make()` factory), `store.py` (Task/Report/Event models, state machine, `TASKS.md`), `worktree.py` (GitRepo: create/export/sync_and_snapshot/diff_stat/remove under one lock), `watcher.py` (REPORT.md polling → events, scope enforcement, `done_without_changes`), `scheduler.py` (semaphores, `depends_on`, job lifecycle, `answer`), `render.py` + `templates/*.j2`, `globs.py` (scope/never_share matching), `cli.py` (`council init|doctor`).
- **Contracts, not prompts**: executor→Claude only via `REPORT.md` (YAML front-matter, `status: done|blocked|failed`); Claude→executor via `TASK.md` at start and `ANSWER.md` on `blocked` (stateless re-dispatch). Adapters only start the process in `cwd=worktree`, enforce budget (20 min soft / 25 min hard, 30 turns) and report exit code; the Watcher parses reports. Missing final report = `failed: no_final_report`.
- **Ollama adapter** is the only one with its own agent loop (tools `read_file/write_file/list_files/run/write_report`, `run` whitelisted to test/lint commands, `git` blocked). Default model `qwen3-coder:30b`, `num_ctx` 32768; retry once with half context on 5xx/timeout.
- **Raster assets (§19.14–19.15)**: Codex (ChatGPT login) and Antigravity CLI `agy` (Google login) both generate PNGs with built-in tools, but save to their own scratch dirs by default; the CLI adapter prefixes every prompt with the absolute workdir and the `assets` prompt demands copy + size check. Gemini CLI is dead for individual accounts (`enabled: false`, needs API key); Copilot cannot make images.
- **Trust & lessons (§19.13)**: `stats.py` owns `.council/stats.json` and `LESSONS.md`; `council_verdict` updates trust and takes a `lesson`; `council_defect` records post-merge defects (always demotes); `render.write_all` injects the model/role lessons into TASK.md. `playbooks.py` selects by trigger keywords, user playbooks override shipped ones.
- **Review/merge (Phase 2)**: `council_review` runs `gates.before_review` in the task worktree and returns diff + flags; `council_verdict(ok=false)` writes the reason as ANSWER.md and re-dispatches from state `review` (attempt+1, 3rd rejection = failed); `council_merge` rebases + `merge --no-ff` in id order, runs `gates.after_merge`, appends to MEMORY.md, removes worktree; rebase conflict → re-dispatch with conflict text. The main worktree must be clean and on the base branch.
- **Resume (§19.3)**: after `blocked` the executor exits on its own; on `council_answer` the workdir is rebuilt, the old report lands as `PREVIOUS_REPORT.md` next to `ANSWER.md`, attempt+1, stateless re-dispatch.
- **Executor isolation (§19.1)**: executors work in `.council/work/<id>/`, a `git archive` export with no `.git` and no `never_share` files; only council-mcp touches the real worktree and `.git`, under one asyncio lock, syncing and enforcing `scope` deterministically on each REPORT status change.
- **Security**: `privacy` field mandatory per task (`internal` when scope touches `config|merit|nuco|receptur|*.fml|*.sql`; `local-only` for DB data); `never_share` globs removed from worktrees; secrets only in env, never in `council.json`; executors never commit (the system makes snapshot commits); all executor output is untrusted content; `events.jsonl` + `reports/` are the audit trail.

## Code conventions (design doc §9)

Python 3.12, `uv`, type hints everywhere, pydantic v2 for anything read from disk, `ruff` (E,F,I,UP,B), asyncio only (no threads), `pathlib` for paths, `structlog` to **stderr** (stdout belongs to MCP). Adapter tests use recorded CLI output fixtures, never live CLIs. Commits: `feat|fix|docs(scope): …`. Any PR that changes a contract updates the design doc. Target repo `.gitignore` must include `.council/worktrees` and `.council/capabilities.json`.

## Token policy for this repo too

When working here, follow the same rule the plugin enforces: docs/assets/chores/review go to executors via the council tools; changes ≥40 lines or ≥2 files are candidates for `council_plan`; keep contracts, integration and merges. Ask the user only for borderline cases.

## Privacy

`uv run python scripts/privacy_check.py` must pass before any push (CI enforces it). Use placeholders: `<user>`, `<srv-ai>`, `user@example.com`.

## Shell gotchas

**npm .cmd shims + multi-line args**: cmd.exe truncates argv at the first newline. `cli.py` bypasses shims via `shim_target()` (runs `node <script>`); keep it that way for any new npm-based CLI.

## Shell gotcha (Bash tool)

The Bash tool mangles `\\n` inside heredoc-fed Python patch scripts (it became a real newline twice this project). Write patch scripts to the scratchpad with the Write tool, or use Edit directly.

## Testing notes

Unit tests use `respx` for Ollama and a `FakeAdapter` for the scheduler; git tests run on a temp repo. The live acceptance script (Codex + Ollama on a throwaway repo) is not in the suite — rerun it manually after adapter changes; the pattern is in DESIGN.md §19.11.

## Stop rule

If after Phase 1 delegation does not save time on a real task, stay at Phase 0 (`council_ask` as second opinion) and finish the project small.
