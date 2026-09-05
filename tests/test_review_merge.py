from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from council_mcp import gates
from council_mcp.config import CouncilConfig
from council_mcp.scheduler import Scheduler
from council_mcp.store import Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo, MergeConflict


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\n")
    (tmp_path / "src" / "b.py").write_text("b = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


async def test_gates_run_and_write(tmp_path: Path) -> None:
    rep = await gates.run(
        ["python -c \"print('hi')\"", 'python -c "import sys; sys.exit(3)"'],
        tmp_path,
        "before_review",
    )
    assert not rep.ok and rep.results[0].ok and rep.results[1].exit_code == 3
    assert "hi" in rep.results[0].output
    path = gates.write(rep, tmp_path / "reports" / "T-001")
    assert path.name == "gates-before_review.json"
    assert (await gates.run([], tmp_path, "x")).ok


async def test_merge_no_ff_and_cleanup(repo: Path) -> None:
    g = GitRepo(repo)
    wt, wd = await g.create("T-001", [])
    (wd / "src" / "a.py").write_text("a = 2\n")
    await g.sync_and_snapshot("T-001", ["src/a.py"], "council: T-001 done 100%")
    # main moves on independently in another file → rebase succeeds
    (repo / "src" / "b.py").write_text("b = 2\n")
    _git(repo, "commit", "-q", "-am", "main moves")
    commit = await g.merge("T-001")
    log = _git(repo, "log", "--oneline", "-3")
    assert log.startswith(commit) and "council: merge T-001" in log
    assert (repo / "src" / "a.py").read_text() == "a = 2\n"
    assert (repo / "src" / "b.py").read_text() == "b = 2\n"
    await g.remove("T-001")
    assert not wt.exists() and "council/T-001" in _git(repo, "branch")


async def test_merge_conflict_aborts_cleanly(repo: Path) -> None:
    g = GitRepo(repo)
    _, wd = await g.create("T-001", [])
    (wd / "src" / "a.py").write_text("a = 2\n")
    await g.sync_and_snapshot("T-001", ["src/a.py"], "snap")
    (repo / "src" / "a.py").write_text("a = 3\n")
    _git(repo, "commit", "-q", "-am", "conflicting change on main")
    with pytest.raises(MergeConflict) as ei:
        await g.merge("T-001")
    assert ei.value.files == ["src/a.py"]
    assert "rebase" not in _git(repo, "status")  # aborted
    assert (repo / "src" / "a.py").read_text() == "a = 3\n"


async def test_merge_discards_gate_noise_in_task_worktree(repo: Path) -> None:
    """Gates run in the task worktree may modify tracked files (e.g. `uv run` refreshing a stale
    uv.lock). That is not the executor's work and must not make `rebase` refuse; before rc10 it was
    reported as a conflict with no files and burned an attempt."""
    g = GitRepo(repo)
    wt, wd = await g.create("T-001", [])
    (wd / "src" / "a.py").write_text("a = 2\n")
    await g.sync_and_snapshot("T-001", ["src/a.py"], "snap")
    (repo / "src" / "b.py").write_text("b = 2\n")
    _git(repo, "commit", "-q", "-am", "main moves")
    (wt / "src" / "b.py").write_text("gate noise\n")  # unstaged change in the worktree
    commit = await g.merge("T-001")
    assert "council: merge T-001" in _git(repo, "log", "--oneline", "-1")
    assert commit and (repo / "src" / "a.py").read_text() == "a = 2\n"
    assert (repo / "src" / "b.py").read_text() == "b = 2\n"  # noise discarded, not merged


async def test_merge_refuses_dirty_main(repo: Path) -> None:
    g = GitRepo(repo)
    _, wd = await g.create("T-001", [])
    (wd / "src" / "a.py").write_text("a = 2\n")
    await g.sync_and_snapshot("T-001", ["src/a.py"], "snap")
    (repo / "src" / "b.py").write_text("dirty\n")
    with pytest.raises(Exception, match="uncommitted"):
        await g.merge("T-001")


class DoneAdapter:
    name = "codex"

    def __init__(self) -> None:
        self.repo_root = Path()
        self.runs = 0

    async def probe(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def ask(self, prompt, files=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def run(self, task, workdir, budget, resume):  # type: ignore[no-untyped-def]
        from council_mcp.adapters.base import RunHandle

        self.runs += 1
        self.saw_answer = (
            (workdir / "ANSWER.md").read_text() if (workdir / "ANSWER.md").exists() else None
        )
        h = RunHandle(task_id=task.id, model="codex")

        async def go() -> None:
            await asyncio.sleep(0.05)
            (workdir / "src" / "a.py").write_text(f"a = {self.runs + 1}\n")
            (workdir / "REPORT.md").write_text(
                f"---\ntask: {task.id}\nstatus: done\npercent: 100\n---\nok"
            )
            h.finish(0)

        asyncio.ensure_future(go())
        return h


async def test_reject_redispatches_then_fails_after_max(
    repo: Path, template_cfg: CouncilConfig
) -> None:
    template_cfg.models["local"].enabled = False
    store = TaskStore(repo)
    git = GitRepo(repo)
    w = Watcher(store, git, interval_s=0.05)
    w.start()
    s = Scheduler(template_cfg, store, git, w, repo)
    ad = DoneAdapter()
    s.adapters["codex"] = ad  # type: ignore[assignment]
    store.save(
        Task(
            id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/a.py"]
        )
    )
    s.dispatch(["T-001"])
    await asyncio.wait_for(s.jobs["T-001"], 10)
    assert store.get("T-001").state == "review"
    assert await s.reject("T-001", "tests missing") == "running"
    await asyncio.wait_for(s.jobs["T-001"], 10)
    t = store.get("T-001")
    assert t.state == "review" and t.attempt == 2 and "tests missing" in (ad.saw_answer or "")
    assert await s.reject("T-001", "still missing") == "running"
    await asyncio.wait_for(s.jobs["T-001"], 10)
    assert store.get("T-001").attempt == 3
    assert await s.reject("T-001", "nope") == "failed"
    assert store.get("T-001").state == "failed"
    types = [e.type for e in store.events()]
    assert types.count("review_reject") == 2 and types[-1] == "failed"
    w.stop()


def test_gates_redact_home() -> None:
    from council_mcp import gates

    raw = (
        "VIRTUAL_ENV=C:\\Users\\<user>\\.venv x C:/Users/<user>/y "
        "/Users/<user>/z /home/<user>/w plain"
    )
    out = gates.redact(raw)
    assert "<user>" not in out and out.endswith("plain") and out.count("~") == 4
