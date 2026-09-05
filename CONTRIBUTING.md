# Contributing

Thanks for helping. `DESIGN.md` is the source of truth; §0 lists closed decisions and §19.9 is the
current plan. A change that alters a contract (REPORT.md, TASK.md, council.json, tool signatures)
updates DESIGN.md in the same commit.

## Setup

```bash
uv sync
uv run pytest -q
uv run ruff format . && uv run ruff check .
uv run mypy
```

CI runs the same four gates on Ubuntu and Windows.

## Adding a model adapter

One file in `council_mcp/adapters/`, or an entry in `cli.py` if the model has a CLI that takes a
prompt flag. Rules: never hardcode approval flags — declare candidates in `_APPROVAL` and let the
probe pick what the installed version supports; never read `REPORT.md` (the watcher does);
tests use recorded output or `respx`, never a live model. Add the adapter name to `AdapterName`
in `config.py`, to `templates/council.json`, and to the README table.

## Adding a playbook (Phase 2+)

One JSON file in `playbooks/`. See DESIGN.md §15.

## Company-specific content

The core knows nothing about any company. Profiles go to `profiles/<name>.json`, examples to
`examples/<name>/`. A PR that puts a company path, hostname or product name in `council_mcp/` is
rejected.

## Commits

`feat|fix|docs|chore|test(scope): summary`. One logical change per commit.
