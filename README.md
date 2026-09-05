# super-claude-code · `council`

You have several AI subscriptions and one repo. `council` is a Claude Code plugin plus a small MCP
server that lets Claude Code plan, delegate, review and merge while other providers' models (Ollama,
Gemini CLI, Codex CLI, Grok, a cheap Claude) execute disjoint tasks in parallel git worktrees.

**Status: Phase 0 (skeleton).** What works today: from Claude Code you can list configured models and
ask any of them a one-shot question, optionally with repo files attached. Dispatching tasks to
worktrees (Phase 1+) is not implemented yet. See [DESIGN.md](DESIGN.md) — the single source of truth.

## Requirements

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/) on PATH
- Claude Code
- At least one executor: an Ollama server (local or remote), and/or `gemini`, `codex`, `claude` CLIs

## Quick start

```bash
git clone <this repo> && cd super-claude-code
uv sync
cp templates/council.json .council/council.json   # edit models / URLs
export COUNCIL_OLLAMA_URL=http://localhost:11434  # or set it in .mcp.json env
```

Open the repo in Claude Code; `.mcp.json` starts `council-mcp` over stdio. Tools exposed:

| Tool | Purpose |
|---|---|
| `council_models` | configured models, availability (probed at start), roles, privacy |
| `council_ask(model, prompt, files?)` | one-shot question; files are inlined, `never_share` globs refused |
| `council_probe` | re-run the availability probe, rewrite `.council/capabilities.json` |

Example in Claude Code: *"Ask `local` for a second opinion on `council_mcp/config.py`."*

## Configuration

`.council/council.json` (schema: `council_mcp/config.py`, example: `templates/council.json`).
No secrets in the file — use `${ENV_VAR}` placeholders. Models that fail the probe (CLI missing,
Ollama down, model not pulled) are disabled automatically and drop out of routing.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff format --check . && uv run ruff check .
uv run mypy
```

Tests use recorded/mocked responses (`respx`); nothing hits a live model.

## Security model (short)

Executors never see files matching `never_share`, never commit, and communicate only through a
`REPORT.md` contract. Privacy levels (`public` / `internal` / `local-only`) route tasks to models
allowed to see them; `local-only` never leaves your Ollama. Details: DESIGN.md §6.

## License

MIT. Company-specific profiles and examples live outside the core (`profiles/`, `examples/`).
