# Adapters

An adapter starts one executor on one task inside the task's workdir and reports the exit code.
It never reads REPORT.md (the watcher does) and never touches git (only council-mcp does).

| Adapter | Binary | Auth | Headless invocation | Reads charter from | Images |
|---|---|---|---|---|---|
| `codex` | `codex` (npm `@openai/codex`) | ChatGPT login | `codex exec -s workspace-write -c approval_policy=never -C <workdir> <prompt>` | `AGENTS.md` | yes (built-in, saves to `~/.codex/generated_images` unless told otherwise) |
| `antigravity` | `agy` (antigravity.google) | Google login | `agy -p <prompt> --dangerously-skip-permissions --output-format text --print-timeout 25m --add-dir <workdir> --model <slug>` | `AGENTS.md` | yes (`generate_image`, saves to `~/.gemini/antigravity-cli/scratch` unless told otherwise) |
| `copilot` | `copilot` (npm `@github/copilot`) | `gh auth login` | `copilot -p <prompt> --silent -C <workdir> --add-dir <workdir> --allow-all-tools --allow-all-paths` | `AGENTS.md` | no |
| `gemini` | `gemini` (npm `@google/gemini-cli`) | API key only (individual Google login removed 2026-06) | `gemini -p <prompt> --approval-mode yolo` | `GEMINI.md` | extension + paid key |
| `claude-sub` | `claude` | Claude Code login | `claude -p <prompt> --permission-mode acceptEdits --allowedTools ... --model haiku` | inline in prompt | no |
| `ollama` | HTTP `/api/chat` | none | own agent loop: `read_file`, `write_file`, `list_files`, `run` (whitelist), `write_report` | system prompt | no |

Approval flags are not hardcoded blindly: `probe()` scans `--help` and the first candidate whose
flags all exist is used, so a CLI update that renames a flag disables the model instead of
breaking it.

Because both image-capable CLIs default to their own scratch folders, every run prompt starts
with the absolute workdir and `assets` tasks are told to copy the file into scope and verify its
size. The watcher's `done_without_changes` flag catches a model that only claims to have written.

## Adding an adapter

1. If the model has a CLI with a prompt flag: add entries to `_ASK_ARGV`, `_RUN_ARGV`, `_APPROVAL`
   and (if it reads an instructions file) `_READS_CHARTER_FILE` in `council_mcp/adapters/cli.py`;
   add the name to `AdapterName` in `config.py` and to `render.write_all`'s charter-file map.
2. Otherwise write `council_mcp/adapters/<name>.py` implementing `probe`, `ask`, `run`
   (see `ollama.py`) and register it in `adapters/__init__.py::make`.
3. Add the model to `templates/council.json` with roles and privacy, and a row to this table.
4. Tests: mock the subprocess/HTTP; never call a live model in the suite.

## Ollama notes

Small local models (≤ 9B) are good at `review`, `data` and `chores`, weak at `implement`: they
report `done` without changes. Keep them first in `review`/`second_opinion` (free tokens) and
last in `implement`. `num_ctx` 16k fits an 8B model on a laptop GPU; the adapter retries once with
half the context on 5xx/timeouts.
