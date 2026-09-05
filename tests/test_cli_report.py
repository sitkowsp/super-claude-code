from __future__ import annotations

from pathlib import Path

import pytest

from council_mcp import cli, stats
from council_mcp.store import Task, TaskStore


def test_report_and_events_brief(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    t = Task(
        id="T-001",
        title="x",
        role="implement",
        privacy="public",
        goal="g",
        scope=["a/"],
        assigned_to="codex",
    )
    store.save(t)
    store.event("T-001", "dispatched", model="codex", actor="claude")
    store.transition(t, "running")
    store.event("T-001", "blocked", model="codex", actor="model", needs=["which db?"])
    st = stats.Stats()
    st.get("codex").tasks = 1
    stats.save(tmp_path, st)
    text = cli.report(tmp_path)
    assert (
        "Tasks: 1" in text
        and "| codex | probation | 1 |" in text
        and "| T-001 | x | codex |" in text
    )
    brief = cli.events(tmp_path)
    assert "T-001 blocked: which db?" in brief
    assert cli.events(tmp_path) == ""  # marker advanced


def test_init_is_idempotent(tmp_path: Path) -> None:
    done = cli.init(tmp_path, Path.cwd())
    assert ".council/MEMORY.md" in done and ".mcp.json" in done
    assert cli.init(tmp_path, Path.cwd()) == []
    assert (tmp_path / ".council" / "council.json").exists()


def test_init_from_plugin_cache_skips_project_mcp_json(tmp_path: Path) -> None:
    fake_cache = tmp_path / ".claude" / "plugins" / "cache" / "super-claude-code" / "council"
    fake_cache.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    done = cli.init(repo, fake_cache)
    assert ".mcp.json" not in done and not (repo / ".mcp.json").exists()
    assert (repo / ".council" / "council.json").exists()


def test_resolve_root_ignores_unexpanded_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from council_mcp import server

    monkeypatch.setenv("COUNCIL_REPO_ROOT", "${CLAUDE_PROJECT_DIR}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert server._resolve_root() == tmp_path.resolve()
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    monkeypatch.chdir(tmp_path)
    assert server._resolve_root() == tmp_path.resolve()
