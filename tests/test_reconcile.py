from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from council_mcp.config import CouncilConfig
from council_mcp.scheduler import Scheduler
from council_mcp.store import Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=u@example.com", "-c", "user.name=u", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.md").write_text("v1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


async def _setup(repo: Path, template_cfg: CouncilConfig) -> tuple[Scheduler, TaskStore, GitRepo]:
    store = TaskStore(repo)
    git = GitRepo(repo)
    return Scheduler(template_cfg, store, git, Watcher(store, git), repo), store, git


async def test_reconcile_closes_hand_merged_and_skips_divergent(
    repo: Path, template_cfg: CouncilConfig
) -> None:
    sched, store, git = await _setup(repo, template_cfg)
    for tid, content in (("T-001", "reviewed\n"), ("T-002", "branch-only\n")):
        store.save(
            Task(
                id=tid,
                title=tid,
                role="docs",
                privacy="public",
                goal="g",
                scope=["a.md"],
                assigned_to="copilot",
                state="queued",
            )
        )
        _git(repo, "branch", f"council/{tid}")
        _git(repo, "checkout", "-q", f"council/{tid}")
        (repo / "a.md").write_text(content)
        _git(repo, "commit", "-qam", f"{tid} work")
        _git(repo, "checkout", "-q", "main")
        t = store.get(tid)
        store.transition(t, "running")
        store.transition(t, "review")
    # the chair copies T-001's content to main by hand (byte-identical); T-002 stays divergent
    (repo / "a.md").write_text("reviewed\n")
    _git(repo, "commit", "-qam", "hand merge of T-001")
    res = await sched.reconcile(None)
    assert [r["task"] for r in res["reconciled"]] == ["T-001"]
    assert store.get("T-001").state == "merged"
    assert [r["task"] for r in res["skipped"]] == ["T-002"]
    assert "differs" in res["skipped"][0]["reason"]
    assert store.get("T-002").state == "review"
    ev = [e for e in store.events() if e.type == "merged" and e.task == "T-001"][0]
    assert ev.data.get("reconciled") is True
    assert ev.data.get("lines") == 2 and ev.data.get("tokens_saved_est") == 880  # docs 800+40*2
    from council_mcp import stats

    st = stats.load(repo)
    assert st.models["copilot"].merged == 1 and st.models["copilot"].tokens_saved_est == 880
    assert "T-001" in st.counted_tasks
    # idempotent: nothing left to reconcile for T-001
    res2 = await sched.reconcile(["T-001"])
    assert res2["reconciled"] == [] and "state merged" in res2["skipped"][0]["reason"]
