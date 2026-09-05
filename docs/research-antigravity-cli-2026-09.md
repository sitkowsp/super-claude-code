# Research: Google Antigravity CLI (`agy`) as a council executor

Date checked: 2026-09-05. Web research only; nothing was installed or run.
Latest CLI release at time of check: **1.1.27 (2026-09-05)**. Flags below were verified against the
official headless docs and third-party transcripts of `agy --help` (v1.1.5 / v1.1.26); items marked
**(unverified)** appear in only one source and must be confirmed with `agy --help` before use.

## 0. Official sources

| Source | URL |
|---|---|
| Product page | https://antigravity.google/product/antigravity-cli/ |
| Docs root (CLI) | https://antigravity.google/docs/cli/overview/ |
| Getting started / install | https://antigravity.google/docs/cli/getting-started/ , https://antigravity.google/docs/cli/install/ |
| **Headless mode** | https://antigravity.google/docs/cli/headless/ |
| Permissions | https://antigravity.google/docs/cli/permissions/ |
| Sandbox | https://antigravity.google/docs/cli/sandbox/ |
| Settings | https://antigravity.google/docs/cli/settings/ |
| MCP (CLI) | https://antigravity.google/docs/cli/mcp/ |
| Features | https://antigravity.google/docs/cli/features/ |
| Best practices | https://antigravity.google/docs/cli/best-practices/ |
| Gemini CLI migration | https://antigravity.google/docs/cli/gcli-migration |
| Models | https://antigravity.google/docs/models/ |
| Plans | https://antigravity.google/docs/plans/ , https://antigravity.google/pricing , https://antigravity.google/blog/changes-to-antigravity-plans |
| GitHub (issues + releases + CHANGELOG; source NOT published) | https://github.com/google-antigravity/antigravity-cli |
| Google Developers blog (transition) | https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/ |
| Gemini Code Assist deprecation | https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals |
| Codelab | https://codelabs.developers.google.com/antigravity-cli-hands-on |

**npm package: none.** Distribution is an installer script, not `@google/...`:
- Linux/macOS: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
- Windows PowerShell: `irm https://antigravity.google/cli/install.ps1 | iex`
- Binary `agy`; Windows path `%LOCALAPPDATA%\agy\bin\agy.exe`; Unix `~/.local/bin/agy`.
- Self-update: `agy update`.

## 1. What it is

- **Agentic coding CLI**, terminal (TUI) surface of the Antigravity platform. Google states the CLI and the
  Antigravity 2.0 desktop app/IDE "run on the exact same agent core"; settings/permissions sync between them and
  a CLI conversation can be exported to the desktop editor (docs/cli/overview).
- **Relation to Gemini CLI:** it is *not* a fork of the TypeScript Gemini CLI codebase. It is a **Go rewrite**
  (developers.googleblog.com), closed source: the GitHub repo hosts only issues, releases, CHANGELOG and docs
  (gemini-cli issue #27304 asking for open source was closed "not planned", 2026-05-20). Gemini CLI features
  carried over: Agent Skills, Hooks, Subagents, Extensions (now "plugins"), MCP, headless mode, `GEMINI.md`/`AGENTS.md`.
  Google explicitly said "there won't be 1:1 feature parity right out of the gate".
- **Timeline:** CLI GA 2026-05-19; on **2026-06-18** Gemini CLI + Gemini Code Assist stopped serving free /
  Google AI Pro / Ultra ("Login with Google") accounts. Gemini CLI keeps working only with Code Assist
  Standard/Enterprise licences or an API key.
- **Models (docs/models, 2026-09):** Gemini 3.8 / 3.7 / 3.6 Flash, Gemini 3.1 Pro (all plans); Claude Sonnet 4.6
  (thinking), Claude Opus 4.6 (thinking), GPT-OSS-120B (Individual/Pro/Ultra only, not Enterprise).
  `agy models` lists slugs; observed slugs look like `gemini-3.8-flash-high|medium|low` (effort baked in) plus
  `--effort low|medium|high`. Image generation inside the *platform* uses **Nano Banana 2** independently of the
  chosen reasoning model (docs/models) - see section 3 for the CLI caveat.
- **Plans / quotas (docs/plans, blog 2026-05-19):**
  - Individual (free, personal Google account): all Gemini models + third-party models, "meaningful quota,
    refreshed weekly", weekly hard cap. Unlimited tab completions. CLI, Scheduled Tasks etc. included.
  - Google AI Pro ($20/mo): "high, generous quota, refreshed every five hours until weekly limit reached".
  - Google AI Ultra ($100/mo = 5x Pro quota; $200/mo = 20x Pro quota).
  - Gemini Flash and Pro share one combined rate limit (allocated by API-price ratio). AI credits are overage only.
  - Google publishes no numeric quotas; community measurements (e.g. ~250 units / 5 h, ~2800 / week on Pro) vary
    and have changed several times. Check with `/usage` or headless `agy -p "/usage" --output-format json`.
  - All CLI sessions draw from the same account allowance as the IDE.
- **Auth:** OAuth with a personal Google account (browser; keyring cached - Windows Credential Manager),
  remote/SSH code flow, or `GEMINI_API_KEY` with `"modelProvider": "gemini"` in
  `~/.gemini/antigravity-cli/settings.json` (docs/cli/install). API-key mode bills the Gemini API and bypasses the
  subscription quota; it is the documented route "for headless and CI runs where no browser is available".

## 2. Non-interactive / headless mode (docs/cli/headless, verified)

| Purpose | Gemini CLI | **Antigravity CLI `agy`** |
|---|---|---|
| single prompt, exit | `gemini -p "..."` | `agy -p "..."` (`--print`, also `--prompt`) |
| auto-approve everything | `--yolo` / `--approval-mode yolo` | `--dangerously-skip-permissions` |
| approval preset | `--approval-mode auto_edit` | `--mode accept-edits` / `--mode plan` (from `--help`, v1.1.5) or `toolPermission` setting (`request-review` default, `proceed-in-sandbox`, `strict`, `always-proceed`) |
| output format | `--output-format text\|json\|stream-json` | `--output-format text\|json\|stream-json` (default text) |
| structured output | - | `--json-schema <inline JSON \| file \| primitive>` -> `structured_output` in envelope |
| stdin multi-turn | stdin text | `--input-format stream-json` (must pair with `--output-format stream-json`); plain `-p` ignores stdin prompt |
| working dir | process cwd + `--include-directories` | process cwd = workspace; `--add-dir <path>` (repeatable). `--cwd <path>` appears in official best-practices example `agy -p "..." --cwd $(pwd)` but not in the `--help` transcript **(unverified)** |
| model | `-m` | `--model <slug>` (unknown slug -> exit 1), `--effort low\|medium\|high`, `--agent <name>` |
| timeout | - | `--print-timeout 5m` (default 5m; raise for real tasks) |
| resume | `--resume` | `-c/--continue`, `--conversation <id>` |
| sandbox | `-s` | `--sandbox` |
| instructions file | `GEMINI.md` | **`AGENTS.md` and `GEMINI.md` at workspace root, both read unchanged** (gcli-migration, best-practices); `GEMINI.md` has priority over `AGENTS.md`; global `~/.gemini/GEMINI.md`; workspace rules dir `.agents/rules/` (legacy `.agent/rules/`); skills `.agents/skills/`. `agy inspect` shows what was loaded. |
| MCP | `~/.gemini/settings.json` mcpServers | global `~/.gemini/config/mcp_config.json` (shared with IDE/desktop) + project `.agents/mcp_config.json`; stdio (`command`/`args`), Streamable HTTP and SSE via `serverUrl` (`url`/`httpUrl` rejected). Unconfigured MCP tools are Ask -> soft-denied headless unless `mcp(server/tool)` / `mcp(*)` allow rule. |

**Streams:** stdout = model response only; stderr = diagnostics, permission notices, auth errors.

**JSON envelope** (`--output-format json`):
`{conversation_id, status: SUCCESS|ERROR|CANCELED|INTERRUPTED|INVALID|WAITING|RUNNING, response, error?, duration_seconds, num_turns, structured_output?, json_schema?, usage{input_tokens,output_tokens,thinking_tokens,cache_read_tokens,total_tokens}, denied_actions (since 1.1.27)}`.
`stream-json` = NDJSON events `init` (cwd, tools, permission_mode, model), `step_update` (text_delta, tool_info{name,parameters,output,error}), `result`.

**Exit codes:** 0 success (also on soft-denied tools!), 1 generic error (bad model, malformed input, schema
violation, not authenticated), 2 streaming-protocol violation. Benign tool errors no longer cause non-zero exit
(1.1.20). => always check `exit==0 && .status=="SUCCESS" && .denied_actions==[]`.

**Headless permission behaviour ("soft-deny"):** file read/write inside the active workspace is auto-allowed;
shell commands, web, MCP default to Ask and in headless are *skipped* with a stderr notice naming the rule to add
(e.g. `command(npm run test)`), run continues, exit 0. Allow rules live in `~/.gemini/antigravity-cli/settings.json`
under `permissions.allow` (`command(prefix)`, `write_file(path)`, `read_file(path)`, `read_url(domain)`,
`mcp(server/tool)`, `unsandboxed(prefix)`); deny > ask > allow. `allowNonWorkspaceAccess` default off.
`--dangerously-skip-permissions` approves everything including shell.

**Non-TTY:** no auth prompt - unauthenticated run exits with "authentication required" on stderr; credentials must
be cached from a prior interactive login (keyring) or `GEMINI_API_KEY` set. Workspace trust ("Yes, I trust this
folder") is stored in settings.json; first run in a new directory should be done interactively once, or the trust
entry pre-seeded (behaviour in headless for untrusted dirs not documented - test).

## 3. Image generation (verdict: **not available from the CLI without an API key**)

- The Antigravity IDE/desktop has built-in Nano Banana 2 image generation (docs/models: "For image generation
  tasks ... the system uses Nano Banana 2"). The **CLI does not expose a built-in image-generation tool**: none of
  the CLI docs, changelog (1.0.2-1.1.27) or codelab mention it; GitHub issue **#734 (2026-08-03, open)** reports
  `agy --model gemini-3.1-flash-image` -> "model ... is not recognized as a known model"; community authors built
  MCP/skill wrappers precisely because "Antigravity lacks native image generation" (dev.to/gde, medium
  "Nano Banana 2 Lite with MCP, and Antigravity CLI").
- Working route: an MCP server or skill that calls the Gemini API image models (`gemini-3.1-flash-lite-image` /
  Nano Banana 2 Lite, Nano Banana 2, Nano Banana Pro) and writes PNG/JPG into a directory the agent chooses
  (e.g. `nb2lite-skill-agy`, `generate-nanobanana`). These require a **Gemini API key and pay-per-image billing**;
  the Google AI Pro/Ultra Antigravity quota does **not** cover them. Files land in the cwd or an
  `IMAGE_OUTPUT_DIR` with names like `gen_<ts>_<uuid>.png`.
- Conclusion for the council: treat `agy` as text/code only; if images are required, run a separate MCP/skill with
  `GEMINI_API_KEY`, or use another executor.

## 4. Sandbox / permission model and subprocess notes

- **Sandbox:** Linux = kernel namespaces (nsjail), macOS = `sandbox-exec` Seatbelt. Writable: workspace +
  `write_file` paths; read-only: `read_file` paths + system dirs; `~/.ssh`, `.env` blocked; network off except
  `read_url` domains. Enable via `--sandbox` or `"enableTerminalSandbox": true`.
  **Windows: not supported** ("sandboxing is not supported on Windows", Google AI forum threads 2026-05..08, no
  official fix); do not pass `--sandbox` on Windows. Known issues: `--sandbox` + `--dangerously-skip-permissions`
  lets the model auto-approve `bypassSandbox` (issue #36, open); Windows permission engine mis-tokenises
  `C:\Program Files\...` and rejects `*` globs in `write_file()` (issue #614, open) - write directory rules
  without wildcard, or use `command(*)`.
- **Permission scope for an executor confined to one directory:** run with cwd = task dir; workspace file I/O is
  auto-allowed, everything outside is denied unless `allowNonWorkspaceAccess` or explicit rules. Do NOT use
  `--dangerously-skip-permissions` if shell containment matters; instead pre-seed `permissions.allow` with the
  exact `command(...)` prefixes needed (or accept soft-deny of shell = pure edit task).
- **Subprocess driving:** pass prompt as argv (`-p "..."`); or, for multi-turn, `--input-format stream-json`.
  Redirect stdin from NUL/`/dev/null` for single-shot runs (issue fixed 1.1.23: subcommands hanging on inherited
  stdin). Set `--print-timeout` >= your wall-clock budget and wrap with an OS-level kill (SIGTERM then kill) to
  avoid half-written files. Parse stdout JSON; ignore/log stderr. Treat as failure when exit != 0 OR
  `status != SUCCESS` OR `denied_actions` non-empty.
- Config paths: `~/.gemini/antigravity-cli/settings.json` (Windows `%USERPROFILE%\.gemini\antigravity-cli\`),
  plugins `~/.gemini/antigravity-cli/plugins/`, skills `~/.gemini/antigravity-cli/skills/`, MCP
  `~/.gemini/config/mcp_config.json`. No project-level `settings.json` documented (only `.agents/` for
  rules/skills/mcp).

## 5. Comparison as a "TASK.md -> edit in dir -> REPORT.md -> exit" executor

| Criterion | Antigravity CLI `agy` 1.1.27 | Gemini CLI 0.58.0 (2026-09-03) | Codex CLI (`codex exec`) |
|---|---|---|---|
| Consumer Google account works | yes (free/Pro/Ultra) | **no** since 2026-06-18 (API key or Code Assist Std/Ent only) | n/a (ChatGPT/OpenAI) |
| Headless one-shot | `agy -p` | `gemini -p` (non-TTY also headless) | `codex exec "..."` or stdin `-` |
| Auto-approve | `--dangerously-skip-permissions`; finer: `--mode accept-edits`, `toolPermission`, `permissions.allow` | `--yolo`, `--approval-mode default\|auto_edit\|plan\|yolo`, `--allowed-tools` | `-a never` + `-s workspace-write` (`--full-auto` deprecated), `--yolo` bypass |
| Confine to directory | cwd = workspace, outside denied by default; `--add-dir`; sandbox Linux/macOS only | cwd + `--include-directories`; `-s` sandbox (Docker/Seatbelt) | `-C <dir>` + `-s workspace-write` (OS sandbox on all platforms incl. Windows) |
| JSON result | `--output-format json` (+ `--json-schema`, `denied_actions`) | `--output-format json\|stream-json` | `--json` NDJSON, `-o last-message.txt`, `--output-schema` |
| Exit codes | 0/1/2; 0 even on soft-deny | 0, 1, 42 input, 53 turn limit | 0/non-zero |
| Instructions file | `AGENTS.md` + `GEMINI.md`, `.agents/rules/` | `GEMINI.md` (configurable) | `AGENTS.md` |
| MCP | yes (`mcp_config.json`) | yes | yes |
| Image generation | no built-in (MCP + API key) | no built-in (extension/MCP + API key) | no built-in |
| Windows | works, but no sandbox; permission-engine path bugs (#614) | works (sandbox via Docker) | works |
| Risk for this use-case | soft-deny silently skipping shell steps; quota shared with IDE | account no longer served -> API-key cost | n/a here |

## Recommendation for a council adapter

Use `agy` only for edit/write tasks (no images). Prefer the permission-scoped variant; fall back to
`--dangerously-skip-permissions` only on trusted, disposable directories.

```text
cwd  = <task_dir>                       # workspace = cwd; TASK.md / REPORT.md live here
argv = agy -p "Read TASK.md in the current directory. Do exactly what it asks, editing files only inside this directory. When finished write REPORT.md summarising changes, then stop."
       --output-format json
       --print-timeout 30m
       --model gemini-3.8-flash-high    # or gemini-3.1-pro / claude-opus-4.6 slug from `agy models`
       --effort high
       --mode accept-edits              # verify in `agy --help`; else rely on default workspace auto-allow
       [--dangerously-skip-permissions] # only if the task needs shell (build/test) and dir is disposable
stdin  = NUL / /dev/null
env    = inherited (keyring OAuth) or GEMINI_API_KEY + modelProvider=gemini for CI
success = exit 0 AND .status == "SUCCESS" AND (.denied_actions // []) == [] AND REPORT.md exists
```

Pre-seed `~/.gemini/antigravity-cli/settings.json` once (interactive first run to trust the folder), e.g.
`"permissions": {"allow": ["command(npm run (build|lint|test))", "command(pytest)"]}` - without `*` globs on Windows.
Do not pass `--sandbox` on Windows. Put standing instructions in `AGENTS.md` inside the task dir
(agy reads it; GEMINI.md overrides). Re-check `agy --help` after `agy update` - flags changed several times
between 1.0.x and 1.1.27.

---

## Addendum — live verification on this machine (2026-09-05, agy 1.1.27, personal Google login)

The web verdict above ("image generation: no") is **contradicted by a live test**. `agy -p "Generate a
256x256 PNG icon of a red five-point star ... save it as star.png in the current working directory"
--dangerously-skip-permissions --output-format text` returned exit 0 and reported using a
`generate_image` tool; a valid 256×256 RGBA PNG (19 850 bytes) was produced. It was written to
`~/.gemini/antigravity-cli/scratch/star.png`, **not** to the cwd — the same default-location trap as
Codex. The council adapter therefore prefixes every prompt with the absolute workdir and the `assets`
prompt demands a copy + size check.

Other live observations: `agy -p` one-shot answered in 4 s; a file-write task (hello.txt + REPORT.md
with front-matter) completed in 34 s with correct output in the cwd; `agy models` lists Gemini
3.8/3.7/3.6 Flash (high/medium/low), Gemini 3.1 Pro, Claude Sonnet 4.6, Claude Opus 4.6 (thinking),
GPT-OSS 120B; `agy agents` is empty; the binary is `%LOCALAPPDATA%\agy\bin\agy.exe`; state and
settings live in `~/.gemini/antigravity-cli/` (`trustedWorkspaces` already contains the user's home,
so no per-folder trust prompt occurred).
