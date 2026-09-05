# Getting started

You have Claude Code plus one or more of: a ChatGPT subscription (Codex CLI), GitHub Copilot
(Copilot CLI), a Google account (Antigravity CLI), an Ollama server. `council` lets Claude Code
hand disjoint tasks to those models, each working in an isolated copy of your repo, while Claude
plans, answers questions, reviews and merges.

## 1. Install the plugin once

```bash
git clone https://github.com/<you>/super-claude-code
cd super-claude-code
uv sync
```

Requirements: Python 3.12, [`uv`](https://docs.astral.sh/uv/) and `git` on PATH.

## 2. Install the executors you own

| Executor | Install | Login |
|---|---|---|
| Codex CLI (ChatGPT Plus/Pro) | `npm i -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm i -g @github/copilot` | `gh auth login` |
| Antigravity CLI (Google account) | installer from https://antigravity.google | run `agy` once |
| Ollama | https://ollama.com, `ollama pull qwen3:8b` | none |
| Claude as cheap executor | already there | none |

You do not need all of them. Models that are missing are disabled automatically.

## 3. Initialise a project

```bash
cd /path/to/your/project
uv run --directory /path/to/super-claude-code council init
uv run --directory /path/to/super-claude-code council doctor
```

`council init` writes `.council/council.json` (models, routing, gates, `never_share`),
`.council/CHARTER.md` (the rules every executor gets), `.council/MEMORY.md` (your project
decisions — executors must follow them), `.mcp.json` (starts the server for Claude Code) and
`.gitignore` entries. `council doctor` probes every CLI and Ollama and prints what is usable.

Edit `council.json`: remove models you do not have, set `never_share` to cover your secrets, and
put your test/lint commands into `gates.before_review` and `gates.after_merge`.

## 4. First session in Claude Code

Open the project. The `council` MCP server starts from `.mcp.json`. Try:

```
/council:ask codex "what does this repo do?" --files README.md
```

Then a real epic:

```
/council:plan add a JSON export to the CLI and document it
```

Claude shows 1–4 cards (goal, scope, acceptance, model). Say **ok**.

```
/council:run
/council:status
```

Executors start in `.council/work/<id>/`; their progress arrives as events. When one reports
`blocked`, Claude proposes an answer — confirm it or type `/council:answer T-001 <text>`.
When a task reaches `review`:

```
/council:review
/council:merge
```

The reviewer runs your gates in the task worktree, reads the diff, and gives a verdict with a
lesson. The integrator rebases, merges `--no-ff`, runs after-merge gates and writes a line to
`MEMORY.md`. Branches `council/<id>` stay until you delete them.

## 5. End of session

```
/council:handoff
```

writes `.council/HANDOFF.md`; the next session reads it first.

## Where things live

```
.council/
  council.json    configuration (versioned)
  CHARTER.md      executor rules (versioned)
  MEMORY.md       project decisions (versioned, executors read it)
  LESSONS.md      one line per rejection/defect, injected into TASK.md (versioned)
  HANDOFF.md      note for the next session
  tasks/*.json    task cards and state
  reports/<id>/   every REPORT.md the executor wrote, gates-*.json
  events.jsonl    audit trail
  stats.json      per-model trust and counters
  worktrees/<id>  git worktrees owned by council-mcp   (ignored)
  work/<id>       what the executor sees: no .git, no secrets (ignored)
  logs/           executor stdout/stderr               (ignored)
```
