# Research: official xAI Grok coding CLI ("Grok Build") — checked 2026-09-05

## Verdict
Yes. xAI ships an official terminal coding agent, **Grok Build**, comparable to Codex CLI / Gemini CLI. Binary `grok`. Works with a **grok.com / X account login (OAuth)** *or* `XAI_API_KEY`. Announced 2026-05-25 (early beta); source open-sourced later (Apache-2.0, `xai-org/grok-build`). As of 2026-08-25 it is available on every consumer plan including Free (paid tiers = higher limits).

## Official product (xAI)
| Item | Value |
|---|---|
| Name | Grok Build |
| Install (mac/Linux/Git Bash) | `curl -fsSL https://x.ai/cli/install.sh \| bash` |
| Install (Windows PowerShell) | `irm https://x.ai/cli/install.ps1 \| iex` |
| Install (npm) | `npm i -g @xai-official/grok` (latest 1.0.13, bin `grok`, license "Proprietary" wrapper around platform binaries, maintainer xai-security; Node >= 20) |
| Binary | `grok` (Rust artifact is `xai-grok-pager`, shipped renamed as `grok`) |
| Source | https://github.com/xai-org/grok-build (Apache-2.0 first-party code) |
| Docs | https://docs.x.ai/build/overview |

### Authentication
- `grok login` — browser OAuth at auth.x.ai (grok.com / X account; SuperGrok / X Premium+ / Free with lower limits). Credentials cached in `~/.grok/auth.json`.
- `grok login --device-auth` — device-code flow (no browser, e.g. SSH).
- `XAI_API_KEY=xai-...` env var — bills xAI API credits instead of the subscription entitlement; recommended for CI. Flag `--oauth` forces OAuth path.
- Subscription entitlement and API credits are separate billing surfaces.

### Headless / non-interactive flags (docs.x.ai/build/cli/headless-scripting + user-guide/14-headless-mode.md)
- Single prompt + exit: `-p, --single <PROMPT>` (also `--prompt-file <PATH>`, `--prompt-json <JSON>`, `--verbatim`)
- Auto-approve: `--yolo` (alias `--always-approve`); `--permission-mode bypassPermissions`; fine-grained `--allow "Bash(npm*)"` / `--deny "Bash(rm*)"`; `--tools`, `--disallowed-tools`; `--sandbox <PROFILE>`
- Output: `--output-format plain|json|streaming-json|streaming-messages-json` (json includes `text`, `stopReason`, `sessionId`, `usage`, `total_cost_usd`)
- Working dir: `--cwd <PATH>`
- Sessions: `-s/--session-id`, `-r/--resume <ID>`, `-c/--continue`, `--fork-session`
- Model/effort: `-m/--model`, `--effort none..max`; `--max-turns <N>`; `--rules <TEXT>`; `--system-prompt-override`
- CI hygiene: `--no-auto-update` (or `GROK_DISABLE_AUTOUPDATER=1`), `--no-alt-screen`; `GROK_HOME` overrides `~/.grok`
- Exit codes: 0 ok, 1 error (auth/network/runtime), 130 SIGINT, 143 SIGTERM
- ACP/IDE embedding: `grok agent stdio`
- Example: `grok -p "Review for bugs" --cwd . --yolo --output-format json | jq -r .text`

### AGENTS.md
Yes. Reads `AGENTS.md`, `Agents.md`, `AGENT.md`, `CLAUDE.md`, `Claude.md`, `CLAUDE.local.md`, plus `*.md` in `.grok/rules/` (and `.claude/rules/`, `.cursor/rules/`), from `~/.grok/` then repo root down to cwd; deeper files win; gitignored files skipped; nested AGENTS.md scopes to its subtree. (docs.x.ai/build/features/project-rules)

Also: xAI publishes a Claude Code plugin delegating to Grok Build — https://github.com/xai-org/grok-build-plugin-cc

## Community tools (NOT official — API key only)
- `superagent-ai/grok-cli` — npm `@vibe-kit/grok-cli` (also published as `grok-dev`); needs `GROK_API_KEY`/`XAI_API_KEY`; headless via `--prompt`. No subscription login.
- `@webdevtoday/grok-cli`, `whitesmith/grok-cli`, `maxgoff/super-agent-grok-cli` — forks/wrappers, API key only.
- `xai-org/grok-1` is the 2024 model-weights release, unrelated to the CLI.

## Sources (all checked 2026-09-05)
- https://docs.x.ai/build/overview
- https://docs.x.ai/build/cli/headless-scripting
- https://docs.x.ai/build/cli/reference
- https://docs.x.ai/build/features/project-rules
- https://x.ai/news/grok-build-cli (2026-05-25)
- https://github.com/xai-org/grok-build (README) and .../crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md
- https://registry.npmjs.org/@xai-official/grok
- https://github.com/xai-org/grok-build-plugin-cc
- https://github.com/superagent-ai/grok-cli ; https://www.npmjs.com/package/@vibe-kit/grok-cli
- Plan availability (secondary): https://www.codeagentswarm.com/en/guides/grok-build-pricing
