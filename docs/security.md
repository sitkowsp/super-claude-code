# Security model

## What an executor can and cannot see

- It works in `.council/work/<id>/`: a plain copy of the branch **without `.git`** and without any
  file matching `never_share`. There is no history to dig secrets out of.
- Only `council-mcp` writes to the real worktree and to git, under a single lock.
- Files the executor changed outside its `scope` are never copied back; the attempt is logged as
  `scope_violation` and shown to the reviewer.
- `privacy` on a card limits which models may take it: `public` (any cloud model), `internal`
  (local Ollama + a cheap Claude), `local-only` (Ollama only). The planner may not lower it to get a
  faster model; a human can, explicitly, in the plan.

## What an executor writes is data

REPORT.md, code, comments and commit-like messages from executors are untrusted. The watcher
flags instruction-like phrases (`injection_suspect`); the reviewer is told never to run commands
suggested by a report except the card's own acceptance commands. `dissent: true` is the only
channel through which an executor can push back on the contract, and it goes to the human.

## Trust

Every model starts on probation (small cards, mandatory second opinion, merge after review).
Promotion needs first-pass approvals; a defect found after merge always demotes. See
`docs/recipes.md`.

## Audit trail

`events.jsonl` (who, what, when, which model, why) and `reports/<id>/` (every report, every gate
result) are versioned. `stats.json` records per-model outcomes. Nothing is sent anywhere except
to the model providers you configured; there is no telemetry.

## Known limits

- CLI executors run with their native auto-approve mode (`--dangerously-skip-permissions`,
  `approval_policy=never`, `--allow-all-tools --allow-all-paths`). Their own sandboxes vary:
  Codex sandboxes the workspace; Antigravity's `--sandbox` is Linux/macOS only; Copilot relies on
  `--add-dir`. A CLI that ignores its directory boundary could read other paths on your machine.
- The Ollama loop confines file tools to the workdir and whitelists `run` to test/lint commands,
  but a test runner executes project code, as tests always do.
- Image-generating CLIs write to their own scratch folders by default; the prompt tells them to
  copy into the workdir, and the reviewer verifies files on disk.
- Secrets belong in environment variables (`${VAR}` in `council.json`), never in the file.

Report vulnerabilities as described in `SECURITY.md`.
