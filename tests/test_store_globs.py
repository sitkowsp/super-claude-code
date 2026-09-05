from __future__ import annotations

from pathlib import Path

import pytest

from council_mcp import globs
from council_mcp.store import Report, Task, TaskStore


def test_glob_forms() -> None:
    assert globs.matches("src/api/x.py", ["src/api/"])
    assert globs.matches("src/api/x.py", ["src/api/x.py"])
    assert globs.matches("deep/dir/dump.sql", ["*.sql"])
    assert globs.matches("secrets/a/b.txt", ["secrets/**"])
    assert globs.matches(".env.local", [".env.*"])
    assert not globs.matches("src/apix/x.py", ["src/api/"])
    assert not globs.matches("src/x.py", ["*.sql"])


def test_overlap_detects_dir_vs_file_and_glob() -> None:
    assert globs.overlap(["src/api/"], ["src/api/users.py"])
    assert globs.overlap(["src/api/users.py"], ["src/api/"])
    assert globs.overlap(["*.sql"], ["db/schema.sql"])
    assert not globs.overlap(["src/api/"], ["src/web/"])
    assert not globs.overlap(["docs/"], ["*.py"])


def test_report_parse_and_lists() -> None:
    rep = Report.parse(
        "---\ntask: T-001\nstatus: blocked\npercent: 40\nneeds: why?\n---\nbody here"
    )
    assert rep.status == "blocked" and rep.needs == ["why?"] and rep.body == "body here"
    with pytest.raises(ValueError):
        Report.parse("no front matter")
    with pytest.raises(ValueError):
        Report.parse("---\ntask: T-001\nstatus: weird\n---\n")


def test_store_roundtrip_transitions_events(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    assert store.next_id() == "T-001"
    t = Task(
        id=store.next_id(), title="x", role="implement", privacy="public", goal="g", scope=["a/"]
    )
    store.save(t)
    assert t.branch == "council/T-001" and store.next_id() == "T-002"
    store.transition(t, "running")
    assert t.started
    with pytest.raises(ValueError):
        store.transition(t, "merged")
    store.transition(t, "review")
    store.event(t.id, "done", model="codex", reason="ok", touched=["a/x.py"])
    evs = store.new_events()
    assert [e.type for e in evs] == ["done"] and evs[0].data["touched"] == ["a/x.py"]
    assert store.new_events() == []  # marked as seen
    board = store.render_tasks_md()
    assert "| T-001 | review | implement | - |" in board
    assert (tmp_path / ".council" / "TASKS.md").exists()
