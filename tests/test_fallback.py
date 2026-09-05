from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from council_mcp import stats
from council_mcp.adapters.base import RunHandle
from council_mcp.config import CouncilConfig
from council_mcp.scheduler import Scheduler, classify_failure
from council_mcp.store import Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo


def test_classify_failure() -> None:
    assert classify_failure(1, None, "HTTP 429 Too Many Requests") == "quota"
    assert classify_failure(1, None, "You have exceeded your usage limit for this plan") == "quota"
    assert classify_failure(1, "codex not on PATH", "") == "unavailable"
    assert classify_failure(1, None, "Error: You are not logged in") == "unavailable"
    assert classify_failure(1, None, "") == "no_response"
    assert classify_failure(-1, "timeout after 25m", "some output") == "no_response"
    assert classify_failure(0, None, "normal output") is None
    assert classify_failure(1, None, "Traceback: AssertionError in tests") is None
    assert classify_failure(-1, "budget exceeded", "x") is None


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


class QuotaAdapter:
    """Dies immediately with a 429 in its log."""

    def __init__(self, name: str, root: Path) -> None:
        self.name = name
        self.repo_root = root

    async def probe(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def ask(self, prompt, files=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def run(self, task: Task, workdir: Path, budget, resume: bool) -> RunHandle:  # type: ignore[no-untyped-def]
        log = self.repo_root / ".council" / "logs"
        log.mkdir(parents=True, exist_ok=True)
        lp = log / f"{task.id}-{self.name}.log"
        lp.write_text("HTTP 429 rate limit exceeded\n")
        h = RunHandle(task_id=task.id, model=self.name, log_path=lp)
        asyncio.get_event_loop().call_later(0.05, h.finish, 1)
        return h


class DoneAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.repo_root = Path()

    async def probe(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def ask(self, prompt, files=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def run(self, task: Task, workdir: Path, budget, resume: bool) -> RunHandle:  # type: ignore[no-untyped-def]
        h = RunHandle(task_id=task.id, model=self.name)

        async def go() -> None:
            await asyncio.sleep(0.05)
            (workdir / "src" / "a.py").write_text("a = 2\n")
            (workdir / "REPORT.md").write_text(
                f"---\ntask: {task.id}\nstatus: done\npercent: 100\n---\nok"
            )
            h.finish(0)

        asyncio.ensure_future(go())
        return h


async def test_quota_failure_falls_back_to_cheap_and_cools_down(
    repo: Path, template_cfg: CouncilConfig
) -> None:
    template_cfg.models["local"].enabled = False
    store = TaskStore(repo)
    git = GitRepo(repo)
    w = Watcher(store, git, interval_s=0.05)
    w.start()
    s = Scheduler(template_cfg, store, git, w, repo)
    s.adapters["codex"] = QuotaAdapter("codex", repo)  # type: ignore[assignment]
    s.adapters["cheap"] = DoneAdapter("cheap")  # type: ignore[assignment]
    store.save(
        Task(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/"])
    )
    s.dispatch(["T-001"])
    await asyncio.wait_for(s.jobs["T-001"], 10)  # codex job (fails, re-queues on cheap)
    for _ in range(100):
        if store.get("T-001").state == "review":
            break
        await asyncio.sleep(0.1)
    t = store.get("T-001")
    assert t.state == "review" and t.assigned_to == "cheap" and t.fallbacks == 1
    types = [e.type for e in store.events()]
    assert (
        "cooldown" in types
        and "fallback" in types
        and types.index("fallback") < types.index("done")
    )
    st = stats.load(repo)
    assert st.models["codex"].cooldown_until and st.models["codex"].fallbacks == 1
    # cooled model is skipped by routing while another candidate exists
    t2 = Task(id="T-002", title="t", role="implement", privacy="public", goal="g", scope=["b/"])
    assert s.pick_model(t2) != "codex"
    w.stop()
