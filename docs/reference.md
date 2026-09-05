# Reference

## council.json

```jsonc
{
  "version": 1,
  "max_parallel": 3,                       // tasks running at once (all models)
  "budget": {"soft_minutes": 20, "hard_minutes": 25, "max_turns": 30},
  "models": {
    "<name>": {
      "adapter": "ollama | codex | copilot | antigravity | gemini | grok | claude-sub",
      "enabled": true,
      "max_parallel": 1,
      "roles": ["implement", "refactor", "docs", "assets", "review", "chores", "data"],
      "privacy": ["public", "internal", "local-only"],   // what the model may see
      "url": "${COUNCIL_OLLAMA_URL}", "model": "qwen3:8b", "num_ctx": 16384,  // ollama
      "cmd": "codex", "model": "gemini-3.8-flash-high"                        // CLIs
    }
  },
  "routing": {
    "by_privacy": {"local-only": ["local"], "internal": ["local", "cheap"], "public": ["codex", "..."]},
    "by_role":    {"implement": ["codex", "antigravity", "copilot", "local"], "...": []},
    "second_opinion": ["local", "antigravity", "copilot"]
  },
  "never_share": [".env", ".env.*", "*.pem", "*.key", "*.sql", "secrets/**"],
  "memory_file": ".council/MEMORY.md",
  "gates": {"before_review": ["uv run pytest -q"], "after_merge": ["uv run pytest -q"]},
  "trust": {"promote_after": 3, "demote_after": 2, "probation_max_lines": 150, "initial": "probation"},
  "fallback": {"model": "cheap", "on": ["quota", "no_response", "unavailable"], "cooldown_minutes": 60, "max_fallbacks": 1},
  "delegation": {"mode": "auto", "min_lines": 40, "min_files": 2, "warn_after_minutes": 210, "session_budget_minutes": 300},
  "obsidian": {"vault": null, "folder": "Council", "mirror": true, "read_context": []}
}
```

Routing rule: a card with `role` R and `privacy` P goes to the first model in `by_role[R]` that is
also in `by_privacy[P]`, is enabled, and passed the probe. No intersection = the plan is rejected.
`assigned_to` on a card overrides routing but still must respect privacy.

Placeholders `${ENV_VAR}` are expanded at load time; never put secrets in the file.

## Task card

```json
{"title": "...", "role": "implement", "privacy": "public",
 "goal": "one sentence: what exists when done",
 "scope": ["src/api/", "tests/test_api.py"],      // globs the executor may change
 "context_files": ["src/models.py"],               // read-only
 "acceptance": ["uv run pytest -q tests/test_api.py"],
 "depends_on": ["T-001"], "assigned_to": "codex"}
```

Scope globs: `dir/` (prefix), `path/file.py`, `*.ext` (any directory), `dir/**`. Two cards may not
overlap. Files changed outside `scope` are never copied back and are logged as `scope_violation`.

States: `queued → running → review → merged`; `running → blocked → running`; `review → running`
(rejected, attempt+1, third rejection = `failed`); anything → `failed`.

## REPORT.md (executor → Claude)

```markdown
---
task: T-001
status: plan | progress | blocked | done | failed
percent: 0-100
touched: [files]
needs: [questions, only when blocked]
verify: [how to check, only when done]
dissent: false
---
free text
```

Front-matter is parsed leniently (`needs: [why?]` is fine). Two unparseable reports in a row fail
the task. Ending without a final `done|blocked|failed` = `failed: no_final_report`.

## MCP tools

| Tool | Args | Effect |
|---|---|---|
| `council_models` | – | models, enabled, roles, privacy, probe errors |
| `council_probe` | – | re-probe, rewrite `capabilities.json` |
| `council_ask` | model, prompt, files? | one-shot question |
| `council_compare` | prompt, models?, files? | same question to several models |
| `council_playbooks` | goal?, playbook? | list playbooks, deterministic selection |
| `council_plan` | tasks[] | validate + save cards |
| `council_dispatch` | ids? | start queued tasks |
| `council_status` | task?, report? | board, new events, HANDOFF.md, task detail |
| `council_answer` | task, text, remember? | answer blocked, resume |
| `council_cancel` | task | kill, mark failed |
| `council_review` | task | diff, flags, gates, trust, second-opinion requirement |
| `council_verdict` | task, ok, reason, lesson? | review_ok / reject (+ANSWER.md, attempt+1) |
| `council_merge` | ids?, force? | rebase + merge --no-ff, after-merge gates, MEMORY.md, cleanup |
| `council_defect` | task, description, lesson? | post-merge defect: trust down, lesson |
| `council_stats` | – | trust table, counters, LESSONS tail |
| `council_why` | task | history with reasons |
| `council_handoff` | text | write HANDOFF.md (+ Obsidian mirror) |
| `council_obsidian` | mirror? | vault detection / mirror |
| `council_context` | – | vault planning notes |
| `council_analyze` | write? | deterministic repo scan, proposed gates |
| `council_should_delegate` | role, est_lines, est_files?, touches_seams?, privacy? | delegate / self / ask |
| `council_budget` | – | session minutes, offload hint |
| `council_doctor` | – | environment check (same as `council doctor`) |

## CLI

```
council init [--root DIR] [--force]   bootstrap .council/ and .mcp.json
council doctor [--root DIR]           probe models, validate routing
council events [--root DIR]           brief of new events (used by the UserPromptSubmit hook)
council report [--root DIR] [--out F]  one-page Markdown report: tasks, reviews, trust, time
```

## Slash commands (plugin)

`/council:ask`, `/council:plan`, `/council:run`, `/council:status`, `/council:answer`,
`/council:stop`, `/council:review`, `/council:merge`, `/council:compare`, `/council:why`,
`/council:defect`, `/council:handoff`, `/council:analyze`, `/council:offload`, `/council:doctor`. Subagents: `council-planner`, `council-reviewer`,
`council-integrator`.

## Environment variables

| Var | Meaning |
|---|---|
| `COUNCIL_REPO_ROOT` | target repo (set by `.mcp.json`) |
| `COUNCIL_OLLAMA_URL` | Ollama base URL |
| `COUNCIL_LOG_LEVEL` | server log level (stderr) |
