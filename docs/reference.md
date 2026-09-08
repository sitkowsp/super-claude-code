# Reference

## council.json

```jsonc
{
  "version": 1,
  "max_parallel": 3,                       // tasks running at once (all models)
  "probe_ttl_hours": 24,                   // re-probe model availability when capabilities.json is older (0 = once per server)
  "budget": {"soft_minutes": 20, "hard_minutes": 25, "max_turns": 30},
  "models": {
    "<name>": {
      "adapter": "ollama | codex | copilot | antigravity | gemini | grok | claude-sub | cursor",
      "enabled": true,
      "max_parallel": 1,
      "roles": ["implement", "refactor", "docs", "assets", "3d", "review", "chores", "data"],
      "privacy": ["public", "internal", "local-only"],   // what the model may see
      "url": "${COUNCIL_OLLAMA_URL}", "model": "qwen3:8b", "num_ctx": 16384,  // ollama
      "cmd": "codex", "model": "gpt-6-astra",                                  // CLIs
      "reasoning": "medium", "context_window": 256000,                          // codex only: -c model_reasoning_effort / model_context_window
      "effort": "medium",                                                       // claude-sub only: claude -p --effort
      "profile": "work2",                                                       // claude-sub only: key of claude_profiles (CLAUDE_CONFIG_DIR)
      "tier": "standard"                                                        // low|standard|high — complexity-based selection (see auto_effort)
    }
  },
  "claude_profiles": {"default": null, "work2": "~/.claude-profiles/work2"},   // Claude accounts for claude -p executors
  "chair": {"plan_assist": null, "review_assist": null, "coder": "executors"},  // see "Chair options"
  "routing": {
    "by_privacy": {"local-only": ["local"], "internal": ["local", "cheap"], "public": ["codex", "..."]},
    "by_role":    {"implement": ["codex", "antigravity", "copilot", "local"], "...": []},
    "second_opinion": ["local", "antigravity", "copilot"]
  },
  "never_share": [".env", ".env.*", "*.pem", "*.key", "*.sql", "secrets/**"],
  "memory_file": ".council/MEMORY.md",
  "gates": {"before_review": ["uv run pytest -q"], "after_merge": ["uv run pytest -q"]},
  "trust": {"promote_after": 3, "demote_after": 2, "probation_max_lines": 150, "initial": "probation"},
  "fallback": {"model": "cheap", "on": ["quota", "no_response", "unavailable"], "cooldown_minutes": 60, "max_fallbacks": 1,
               "by_model": {"fable": ["fable-work2", "codex"]}},              // per-model chain tried before `model`
  "delegation": {"mode": "auto", "auto_effort": true, "min_lines": 40, "min_files": 2, "warn_after_minutes": 210, "session_budget_minutes": 300},
  "obsidian": {"vault": null, "folder": "Council", "mirror": true, "read_context": []}
}
```

Routing rule: a card with `role` R and `privacy` P goes to the first model in `by_role[R]` that is
also in `by_privacy[P]`, is enabled, and passed the probe. No intersection = the plan is rejected.
`assigned_to` on a card overrides routing but still must respect privacy.

### Daily availability probe (`probe_ttl_hours`, default 24)

`.council/capabilities.json` records when every provider was last probed. Before each dispatch the
server checks that age: older than `probe_ttl_hours` → the full probe reruns (first use of the day),
so routing and the complexity-based tier/effort choice always work from a current picture. A model
that recovered since the last probe comes back automatically (its `enabled` is restored from
council.json before re-probing). The probe also asks each CLI to **list its models** (`agy models`
works today; CLIs without a list command fail silently and your configured `model` stays
authoritative) and records the **reasoning-effort values** the CLI accepts. `council_models` shows
the probe age, per-model `available_models` + `efforts`, and warns when a configured model is not in
a non-empty discovered list; `council_probe` forces a refresh now; the SessionStart hook prints a
one-line hint when the probe is stale. `0` disables the daily refresh (probe once per server
process).

### Cursor adapter (optional)

`"adapter": "cursor"`, binary `cursor-agent` (installed by Cursor's own script, not npm). Runs
headless with `-p … --output-format text --force`, reads `AGENTS.md`/`CLAUDE.md` from the workdir
natively, and picks its backend via `"model"` (e.g. `composer-2.5`, `gpt-5.6`, `opus-5`) — there is
no separate effort knob, so the complexity automation influences it only through tier-based model
choice. `cursor-agent models` is used by the probe to discover the account's model list. The
template ships it `enabled: false`; `/council:doctor` prints the install command when the binary is
missing. Executor run verified as detection-only (no Cursor subscription on the dev machine).

Placeholders `${ENV_VAR}` are expanded at load time; never put secrets in the file.

### Complexity → tier and effort (`delegation.auto_effort`, default on)

Every dispatch runs a deterministic assessment of the card (`complexity.assess`): role weight,
scope breadth (`**`, whole dirs, glob count), goal length, acceptance-criteria count, dependencies,
complexity/simplicity keywords in the title+goal, and the attempt number (a retry after a rejection
raises the level). Score ≤2 = `simple`, ≤7 = `standard`, else `complex`. Effects:

| level | model choice (within the routing candidates) | effort sent to the executor |
|---|---|---|
| simple | first candidate with `tier: "low"` (template: `cheap`, `local`) | `low` |
| standard | routing order unchanged | `medium` |
| complex | first candidate with `tier: "high"` (template: `codex`, `fable`) | `high` |

Effort reaches executors that have such a knob: codex as `-c model_reasoning_effort="…"`,
`claude -p` as `--effort …`; others ignore it. `assigned_to` on a card still overrides the model
choice (effort still applies). The decision and its reasons are in the `dispatched` event
(`council_why`), the level in the task JSON (`complexity`, `effort`), and `council_plan` returns a
per-card preview. `"auto_effort": false` restores static routing and the cfg-level
`reasoning`/`effort` values.

### Chair options

`chair.plan_assist` / `chair.review_assist`: a model name or `null`. With `plan_assist` set,
`council_plan(goal=…, draft=true)` asks that model for a JSON array of cards (prompt:
`templates/plan_draft.j2`: goal, `council_analyze` output, selected playbook, MEMORY.md, vault notes,
existing tasks, never_share) and returns them **validated but unsaved** (`draft`, `errors`); ids and
`assigned_to` are always assigned by the server. With `review_assist` set, `council_review` adds
`assistant_review` (`templates/review_assist.j2`, max 12 lines; failures are reported, never block).
`chair.coder`: `"executors"` or a model name that `candidates()` puts first for `implement`/`refactor`
only. The template ships `fable` (`claude-sub`, `claude-fable-5-1`, `effort: medium`, disabled);
`council_setup(coder="fable")` enables it; `coder="executors"` disables a Claude-backed coder again. Change with `/council:chair`, `council_setup(...)` or
`council setup --coder … --plan-assist … --review-assist …`; `council_doctor` reports the `chair` line.

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
| `council_plan` | tasks[]? , goal?, draft?, playbook? | validate + save cards; `draft=true` + `goal`: the `chair.plan_assist` model drafts cards (validated, not saved) |
| `council_dispatch` | ids? | start queued tasks |
| `council_status` | task?, report? | board, new events, HANDOFF.md, task detail |
| `council_answer` | task, text, remember? | answer blocked, resume |
| `council_cancel` | task | kill, mark failed |
| `council_review` | task | diff, flags, gates, trust, second-opinion requirement, `assistant_review` when `chair.review_assist` is set |
| `council_verdict` | task, ok, reason, lesson? | review_ok / reject (+ANSWER.md, attempt+1) |
| `council_merge` | ids?, force?, reconcile? | rebase + merge --no-ff, after-merge gates, MEMORY.md, cleanup; `reconcile=true` closes review tasks already merged by hand (content byte-identical on base; counts merged + savings from the branch diff) |
| `council_defect` | task, description, lesson? | post-merge defect: trust down, lesson |
| `council_stats` | – | trust table, counters, LESSONS tail, `savings` (estimate) |
| `council_accounts` | add?, verify?, remove? | Claude profiles for `claude -p` executors: table (logged in, account/org, models, cooldown), login command for a new profile, enable models of logged-in profiles, fallback chains, chair switch recipe, policy note |
| `council_savings` | backfill? | estimated Claude tokens saved: total, per model, assistants, method; `backfill=true` counts earlier merges from their commits |
| `council_why` | task | history with reasons |
| `council_handoff` | text | write HANDOFF.md (+ Obsidian mirror) |
| `council_obsidian` | mirror?, kit? | vault detection / mirror / Claudian command kit |
| `council_context` | – | vault planning notes |
| `council_analyze` | write? | deterministic repo scan, proposed gates |
| `council_should_delegate` | role, est_lines, est_files?, touches_seams?, privacy? | delegate / self / ask |
| `council_budget` | – | session minutes, offload hint |
| `council_doctor` | – | environment check (same as `council doctor`) |
| `council_ping` | – | no-config diagnostics (root, env, uv) |
| `council_setup` | install?, coder?, plan_assist?, review_assist? | executor table, npm installs, logins needed; chair switches (`coder`=`executors`\|model, assistants = model or `off`) |

## CLI

Available as `uv run council …` in a clone, or `uv run --directory <plugin cache dir> council …`
with a plugin install (`~/.claude/plugins/cache/super-claude-code/council/<version>`). The plugin
does not put `council` on your PATH; the slash commands and MCP tools cover the same functions
(`/council:setup` ≈ `council setup`, `/council:doctor` ≈ `council doctor`, hooks run `session-start`
and `events` for you).

```
council init [--root DIR] [--force] [--obsidian]   bootstrap .council/ and .mcp.json (+ vault kit)
council setup [--root DIR] [--install] [--coder M] [--plan-assist M|off] [--review-assist M|off]
                                      executor table; install missing npm CLIs; chair switches
council doctor [--root DIR]           probe models, validate routing
council events [--root DIR]           brief of new events (used by the UserPromptSubmit hook)
council reconcile [--root DIR] [IDS...]  close review tasks already merged by hand (one-shot, no server)
council savings [--root DIR] [--backfill]  savings summary; backfill counts older merges/reconciles
council report [--root DIR] [--out F]  one-page Markdown report: tasks, reviews, trust, time
council obsidian [--root DIR] [--mirror] vault status / mirror
council session-start [--root DIR]     what the SessionStart hook runs
```

## Slash commands (plugin)

`/council:ask`, `/council:plan`, `/council:run`, `/council:status`, `/council:answer`,
`/council:stop`, `/council:review`, `/council:merge`, `/council:compare`, `/council:why`,
`/council:defect`, `/council:handoff`, `/council:analyze`, `/council:offload`, `/council:doctor`,
`/council:setup`, `/council:chair` (show / `coder fable|executors` / `plan-assist <model|off>` /
`review-assist <model|off>`), `/council:savings [--backfill]` (estimated Claude tokens saved), `/council:accounts [add <name> | verify | remove <name>]` (second Claude account for executors). Subagents: `council-planner`, `council-reviewer`,
`council-integrator`.

## Environment variables

| Var | Meaning |
|---|---|
| `COUNCIL_REPO_ROOT` | target repo (set by `.mcp.json`) |
| `COUNCIL_OLLAMA_URL` | Ollama base URL |
| `COUNCIL_LOG_LEVEL` | server log level (stderr) |
| `CLAUDE_CONFIG_DIR` | set by council-mcp per `claude -p` executor from `claude_profiles[model.profile]`; selects the Claude account |
| `COUNCIL_OBSIDIAN_VAULT` | vault for all council projects; `off`/`none`/`0` disables the Obsidian layer (simulations, CI) |
| `COUNCIL_EXECUTOR` | set to `1` by council-mcp for executor processes; the plugin's hooks exit silently when they see it (a `claude -p` executor must not init `.council/` in its workdir) |
