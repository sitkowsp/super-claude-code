# Security

## Model

- Executors (other providers' CLIs and models) never see the repository's `.git` or any file
  matching `never_share`. They work in `.council/work/<id>/`, a plain copy.
- Only `council-mcp` writes to git, under a single lock. Files outside a task's `scope` are never
  copied back; the attempt is logged as `scope_violation`.
- Everything an executor produces (REPORT.md, code, comments) is treated as data. Instruction-like
  phrases in reports are flagged as `injection_suspect`.
- `privacy: local-only` tasks are routed only to models in `by_privacy["local-only"]` (your Ollama).
- No secrets in `council.json`; use `${ENV_VAR}` placeholders. No telemetry.

## Known limits (v1)

- CLI executors run with their own native sandbox and auto-approve mode inside the workdir. A CLI
  that ignores its `-C`/`--add-dir` boundary could read other paths on your machine. Review the
  approval flags in `council_mcp/adapters/cli.py` before enabling a new CLI.
- The Ollama agent loop confines file tools to the workdir and whitelists `run` commands, but a
  whitelisted test runner can execute arbitrary project code (as tests always can).

## Reporting

Please report vulnerabilities privately to the maintainer (see `pyproject.toml` / GitHub profile)
rather than in a public issue. You will get an acknowledgement within 7 days.
