from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from council_mcp.adapters.base import RunHandle
from council_mcp.adapters.ollama import OllamaAdapter
from council_mcp.config import Budget, CouncilConfig
from council_mcp.scheduler import Scheduler
from council_mcp.store import Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo

BASE = "http://ollama.test:11434"


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


def _tool_call(name: str, **args: object) -> dict[str, object]:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": args}}],
        }
    }


@respx.mock
async def test_ollama_loop_writes_file_and_report(repo: Path, template_cfg: CouncilConfig) -> None:
    route = respx.post(f"{BASE}/api/chat")
    route.side_effect = [
        httpx.Response(200, json=_tool_call("list_files", glob="src/*")),
        httpx.Response(200, json=_tool_call("write_file", path="src/a.py", content="a = 2\n")),
        httpx.Response(200, json=_tool_call("run", cmd="rm -rf /")),  # refused by whitelist
        httpx.Response(
            200,
            json=_tool_call(
                "write_report",
                status="done",
                percent=100,
                touched=["src/a.py"],
                verify=["pytest"],
                body="ok",
            ),
        ),
    ]
    wd = repo / ".council" / "work" / "T-001"
    wd.mkdir(parents=True)
    (wd / "src").mkdir()
    (wd / "src" / "a.py").write_text("a = 1\n")
    (wd / "TASK.md").write_text("# T-001")
    a = OllamaAdapter("local", template_cfg.models["local"], timeout_s=5)
    a.repo_root = repo
    t = Task(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/"])
    h = await a.run(t, wd, Budget(max_turns=10), resume=False)
    await asyncio.wait_for(h.done.wait(), 5)
    assert h.exit_code == 0 and route.call_count == 4
    assert (wd / "src" / "a.py").read_text() == "a = 2\n"
    rep = (wd / "REPORT.md").read_text()
    assert rep.startswith('---\ntask: "T-001"\nstatus: "done"') and "ok" in rep
    # the refused command result went back to the model
    sent = json.loads(route.calls[3].request.content)
    assert any(m.get("role") == "tool" and "refused" in m["content"] for m in sent["messages"])


@respx.mock
async def test_ollama_loop_path_escape_refused(repo: Path, template_cfg: CouncilConfig) -> None:
    wd = repo / ".council" / "work" / "T-002"
    wd.mkdir(parents=True)
    a = OllamaAdapter("local", template_cfg.models["local"], timeout_s=5)
    out = await a._tool(wd, "read_file", {"path": "../../.council/council.json"})
    assert out.startswith("error: path escapes")


class FakeAdapter:
    """Executor stand-in: writes a REPORT.md and exits."""

    name = "fake"

    def __init__(self, report: str, change: tuple[str, str] | None = None) -> None:
        self.report = report
        self.change = change
        self.repo_root = Path()

    async def probe(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def ask(self, prompt, files=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def run(self, task: Task, workdir: Path, budget: Budget, resume: bool) -> RunHandle:
        h = RunHandle(task_id=task.id, model="codex")

        async def go() -> None:
            await asyncio.sleep(0.05)
            if self.change:
                (workdir / self.change[0]).write_text(self.change[1])
            (workdir / "REPORT.md").write_text(self.report.format(id=task.id))
            h.finish(0)

        asyncio.ensure_future(go())
        return h


async def _sched(
    repo: Path, cfg: CouncilConfig, adapter: FakeAdapter
) -> tuple[Scheduler, TaskStore]:
    store = TaskStore(repo)
    git = GitRepo(repo)
    watcher = Watcher(store, git, interval_s=0.05)
    watcher.start()
    s = Scheduler(cfg, store, git, watcher, repo)
    s.adapters["codex"] = adapter  # type: ignore[assignment]
    return s, store


async def test_scheduler_full_cycle_done(repo: Path, template_cfg: CouncilConfig) -> None:
    template_cfg.models["local"].enabled = False
    s, store = await _sched(
        repo,
        template_cfg,
        FakeAdapter(
            "---\ntask: {id}\nstatus: done\npercent: 100\ntouched: [src/a.py]\n---\nok",
            ("src/a.py", "a = 9\n"),
        ),
    )
    t = Task(
        id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/a.py"]
    )
    store.save(t)
    assert s.dispatch(["T-001"]) == ["T-001"]
    assert store.get("T-001").assigned_to == "codex"
    await asyncio.wait_for(s.jobs["T-001"], 10)
    t = store.get("T-001")
    assert t.state == "review" and t.last_report and t.last_report.percent == 100
    types = [e.type for e in store.events()]
    assert types[:2] == ["dispatched", "report"] and types[-1] == "done"
    diff = await s.git.diff_stat("T-001")
    assert "src/a.py" in diff
    assert (repo / ".council" / "work" / "T-001" / "TASK.md").exists()
    s.watcher.stop()


async def test_scheduler_no_final_report_fails(repo: Path, template_cfg: CouncilConfig) -> None:
    template_cfg.models["local"].enabled = False
    s, store = await _sched(
        repo, template_cfg, FakeAdapter("---\ntask: {id}\nstatus: progress\npercent: 50\n---\nhalf")
    )
    store.save(
        Task(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/"])
    )
    s.dispatch(["T-001"])
    await asyncio.wait_for(s.jobs["T-001"], 10)
    t = store.get("T-001")
    assert t.state == "failed" and t.reason == "no_final_report"
    s.watcher.stop()


async def test_scheduler_blocked_then_answer_resumes(
    repo: Path, template_cfg: CouncilConfig
) -> None:
    template_cfg.models["local"].enabled = False
    fake = FakeAdapter("---\ntask: {id}\nstatus: blocked\nneeds: [which db?]\n---\nq")
    s, store = await _sched(repo, template_cfg, fake)
    store.save(
        Task(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/"])
    )
    s.dispatch(["T-001"])
    await asyncio.wait_for(s.jobs["T-001"], 10)
    assert store.get("T-001").state == "blocked"
    fake.report = "---\ntask: {id}\nstatus: done\npercent: 100\n---\nfinished"
    await s.answer("T-001", "use sqlite")
    await asyncio.wait_for(s.jobs["T-001"], 10)
    t = store.get("T-001")
    assert t.state == "review" and t.attempt == 2
    assert (repo / ".council" / "work" / "T-001" / "ANSWER.md").read_text() == "use sqlite"
    s.watcher.stop()


async def test_scheduler_privacy_routing_rejects(repo: Path, template_cfg: CouncilConfig) -> None:
    s, store = await _sched(repo, template_cfg, FakeAdapter(""))
    t = Task(
        id="T-001",
        title="t",
        role="implement",
        privacy="local-only",
        goal="g",
        scope=["src/"],
        assigned_to="codex",
    )
    with pytest.raises(ValueError):
        s.pick_model(t)
    t.assigned_to = None
    assert s.pick_model(t) == "local"
    s.watcher.stop()
