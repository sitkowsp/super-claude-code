"""Scheduler (DESIGN.md §2, §14.7): asyncio semaphores — global max_parallel and per-model —
plus `depends_on` waves. Owns the per-task lifecycle: create worktree/workdir → render →
adapter.run → wait → finalize.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from council_mcp import render, stats
from council_mcp.adapters import make
from council_mcp.adapters.base import Adapter, RunHandle
from council_mcp.config import CouncilConfig
from council_mcp.log import get
from council_mcp.store import MAX_ATTEMPTS, Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo

log = get(__name__)
BLOCKED_GRACE_S = 120  # §19.3: after `blocked` wait for the executor to exit on its own
QUOTA_RE = re.compile(
    r"429|rate.?limit|quota|usage limit|insufficient.credits|out of credits|too many requests|"
    r"exceeded your|billing|403.*(credit|subscription|plan)|plan limit|capacity",
    re.I,
)
UNAVAILABLE_RE = re.compile(
    r"not on PATH|ENOTFOUND|ECONNREFUSED|connection refused|could not connect|"
    r"503|502|service unavailable|not logged in|login required|unauthori[sz]ed|401",
    re.I,
)


def classify_failure(exit_code: int | None, error: str | None, log_tail: str) -> str | None:
    """quota | no_response | unavailable | None (a real task failure: keep it failed)."""
    text = f"{error or ''}\n{log_tail}"
    if QUOTA_RE.search(text):
        return "quota"
    if UNAVAILABLE_RE.search(text):
        return "unavailable"
    if error in ("budget exceeded", "cancelled"):
        return None
    if exit_code not in (0, None) and not log_tail.strip():
        return "no_response"
    if error and "timeout" in error.lower():
        return "no_response"
    return None


class Scheduler:
    def __init__(
        self, cfg: CouncilConfig, store: TaskStore, git: GitRepo, watcher: Watcher, repo_root: Path
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.git = git
        self.watcher = watcher
        self.root = repo_root
        self.global_sem = asyncio.Semaphore(cfg.max_parallel)
        self.model_sems = {n: asyncio.Semaphore(m.max_parallel) for n, m in cfg.models.items()}
        self.handles: dict[str, RunHandle] = {}
        self.jobs: dict[str, asyncio.Task[None]] = {}
        self.adapters: dict[str, Adapter] = {}

    def adapter(self, name: str) -> Adapter:
        if name not in self.adapters:
            a = make(name, self.cfg.models[name])
            a.repo_root = self.root  # type: ignore[attr-defined]
            if hasattr(a, "memory_file"):
                a.memory_file = self.cfg.memory_file
            self.adapters[name] = a
        return self.adapters[name]

    def pick_model(self, task: Task) -> str:
        if task.assigned_to:
            m = self.cfg.models.get(task.assigned_to)
            if not m or not m.enabled:
                raise ValueError(f"{task.id}: assigned model '{task.assigned_to}' unavailable")
            if task.privacy not in m.privacy:
                raise ValueError(
                    f"{task.id}: model '{task.assigned_to}' not allowed for privacy {task.privacy}"
                )
            return task.assigned_to
        cands = self.cfg.candidates(task.role, task.privacy)
        st = stats.load(self.root)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        cands = [c for c in cands if not stats.in_cooldown(st.get(c), now)] or cands
        if not cands:
            raise ValueError(f"{task.id}: no model for role={task.role} privacy={task.privacy}")
        return cands[0]

    def dispatch(self, ids: list[str]) -> list[str]:
        started = []
        for tid in ids:
            task = self.store.get(tid)
            if task.state not in ("queued", "blocked", "review"):
                continue
            if tid in self.jobs and not self.jobs[tid].done():
                continue
            model = self.pick_model(task)
            task.assigned_to = model
            self.store.save(task)
            if task.state == "queued":
                st = stats.load(self.root)
                st.get(model, self.cfg.trust.initial).tasks += 1
                stats.save(self.root, st)
            self.jobs[tid] = asyncio.ensure_future(self._job(tid, model))
            started.append(tid)
        return started

    def cancel(self, tid: str) -> bool:
        h = self.handles.get(tid)
        if h:
            h.cancel()
        job = self.jobs.get(tid)
        if job and not job.done():
            job.cancel()
        task = self.store.get(tid)
        if task.state in ("queued", "running", "blocked"):
            self.store.transition(task, "failed", reason="cancelled")
            self.store.event(tid, "cancelled", model=task.assigned_to, actor="claude")
            return True
        return False

    async def _deps_ready(self, task: Task) -> None:
        while True:
            states = {d: self.store.get(d).state for d in task.depends_on}
            if all(s == "merged" for s in states.values()):
                return
            if any(s == "failed" for s in states.values()):
                raise RuntimeError(f"dependency failed: {states}")
            await asyncio.sleep(5)

    async def _job(self, tid: str, model: str) -> None:
        task = self.store.get(tid)
        try:
            await self._deps_ready(task)
            async with self.global_sem, self.model_sems[model]:
                task = self.store.get(tid)
                resume = task.state in ("blocked", "review")
                wt, wd = await self.git.create(tid, self.cfg.never_share)
                if resume:  # keep executor's previous REPORT.md/ANSWER.md next to fresh sources
                    for src, dst in (
                        ("REPORT.md", "PREVIOUS_REPORT.md"),
                        ("ANSWER.md", "ANSWER.md"),
                    ):
                        p = self.root / ".council" / "reports" / tid / src
                        if p.exists():
                            (wd / dst).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                render.write_all(
                    self.root,
                    wd,
                    task,
                    self.cfg.budget,
                    self.cfg.models[model].adapter,
                    self.cfg.memory_file,
                )
                self.store.transition(task, "running", reason=None)
                self.store.event(
                    tid,
                    "dispatched",
                    model=model,
                    actor="claude",
                    reason=f"role={task.role} privacy={task.privacy} attempt={task.attempt}",
                    workdir=str(wd),
                    branch=task.branch,
                    resume=resume,
                )
                handle = await self.adapter(model).run(task, wd, self.cfg.budget, resume)
                self.handles[tid] = handle
                await handle.done.wait()
                await self._finalize(tid, handle)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("job_error", task=tid, error=str(e))
            task = self.store.get(tid)
            if task.state in ("queued", "running", "blocked"):
                self.store.transition(task, "failed", reason=str(e)[:300])
                self.store.event(tid, "failed", model=model, reason=str(e)[:300])
        finally:
            self.handles.pop(tid, None)

    async def _finalize(self, tid: str, handle: RunHandle) -> None:
        # give the watcher one last look at REPORT.md before judging
        task = self.store.get(tid)
        report = self.root / task.workdir / "REPORT.md"
        if task.state == "running" and report.exists():
            self.watcher._mtimes.pop(tid, None)
            await self.watcher.poll()
            task = self.store.get(tid)
        if task.state == "running":
            reason = handle.error or "no_final_report"
            self.store.transition(task, "failed", reason=reason)
            self.store.event(
                tid, "failed", model=handle.model, reason=reason, exit_code=handle.exit_code
            )
            await self._maybe_fallback(task, handle)
        elif task.state == "blocked":
            # persist the executor's last REPORT/ANSWER for the resume prompt
            d = self.root / ".council" / "reports" / tid
            d.mkdir(parents=True, exist_ok=True)
            if report.exists():
                (d / "REPORT.md").write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("job_finished", task=tid, state=self.store.get(tid).state, exit=handle.exit_code)

    def _log_tail(self, handle: RunHandle) -> str:
        if handle.log_path and handle.log_path.exists():
            try:
                return handle.log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                return ""
        return ""

    async def _maybe_fallback(self, task: Task, handle: RunHandle) -> bool:
        """Quota / no response / unavailable → cooldown + re-queue on the fallback model."""
        fb = self.cfg.fallback
        kind = classify_failure(handle.exit_code, handle.error, self._log_tail(handle))
        if kind is None or kind not in fb.on:
            return False
        st = stats.load(self.root)
        m = st.get(handle.model, self.cfg.trust.initial)
        until = datetime.now(UTC) + timedelta(minutes=fb.cooldown_minutes)
        m.cooldown_until = until.isoformat(timespec="seconds")
        m.fallbacks += 1
        stats.save(self.root, st)
        self.store.event(
            task.id,
            "cooldown",
            model=handle.model,
            actor="system",
            reason=f"{kind}: cooldown {fb.cooldown_minutes} min",
            until=m.cooldown_until,
        )
        target = fb.model
        if (
            not target
            or target == handle.model
            or target not in self.cfg.models
            or not self.cfg.models[target].enabled
            or task.privacy not in self.cfg.models[target].privacy
            or task.fallbacks >= fb.max_fallbacks
        ):
            self.store.event(
                task.id,
                "fallback",
                model=handle.model,
                actor="system",
                reason=f"{kind} but no fallback possible (target={target}); "
                "Claude (orchestrator) should take this task",
            )
            return False
        task = self.store.get(task.id)
        task.fallbacks += 1
        task.assigned_to = target
        self.store.transition(task, "queued", reason=f"fallback from {handle.model}: {kind}")
        self.store.event(
            task.id,
            "fallback",
            model=target,
            actor="system",
            reason=f"{handle.model} {kind} → {target}",
            from_model=handle.model,
        )
        self.jobs.pop(task.id, None)  # the current job is ending; let dispatch start a new one
        self.dispatch([task.id])
        return True

    async def reject(self, tid: str, reason: str) -> str:
        """Review rejected: attempt+1 (max 3), reason becomes ANSWER.md, re-dispatch."""
        task = self.store.get(tid)
        if task.state != "review":
            raise ValueError(f"{tid} is {task.state}, not review")
        if task.attempt >= MAX_ATTEMPTS:
            why = f"rejected {task.attempt}x: {reason[:200]}"
            self.store.transition(task, "failed", reason=why)
            self.store.event(
                tid,
                "failed",
                model=task.assigned_to,
                actor="claude",
                reason=f"max attempts; last rejection: {reason[:200]}",
            )
            return "failed"
        d = self.root / ".council" / "reports" / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "ANSWER.md").write_text("# Review rejected\n\n" + reason, encoding="utf-8")
        wd_report = self.root / task.workdir / "REPORT.md"
        if wd_report.exists():
            (d / "REPORT.md").write_text(wd_report.read_text(encoding="utf-8"), encoding="utf-8")
        task.attempt += 1
        self.store.save(task)
        self.store.event(
            tid,
            "review_reject",
            model=task.assigned_to,
            actor="claude",
            reason=reason[:300],
            attempt=task.attempt,
        )
        self.dispatch([tid])
        return "running"

    async def answer(self, tid: str, text: str) -> None:
        task = self.store.get(tid)
        if task.state != "blocked":
            raise ValueError(f"{tid} is {task.state}, not blocked")
        d = self.root / ".council" / "reports" / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "ANSWER.md").write_text(text, encoding="utf-8")
        task.attempt += 1
        self.store.save(task)
        self.store.event(tid, "answered", actor="claude", attempt=task.attempt, answer=text[:300])
        self.dispatch([tid])
