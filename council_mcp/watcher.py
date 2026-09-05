"""Watcher (DESIGN.md §3.3, §16.6, §19.1): polls REPORT.md in each running task's workdir.

On change: parse front-matter (invalid → `report_invalid`; 2 in a row → failed), archive the
report
under reports/<id>/NNN-<status>.md, sync workdir → worktree enforcing scope (rejected files →
`scope_violation`), snapshot-commit, update state (done → review, blocked → blocked,
failed → failed).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path

from council_mcp.log import get
from council_mcp.store import Report, Task, TaskStore
from council_mcp.worktree import GitRepo

log = get(__name__)
INJECTION_RE = re.compile(
    r"ignore (all )?previous instructions|disregard .* instructions|you are now", re.I
)


class Watcher:
    def __init__(self, store: TaskStore, git: GitRepo, interval_s: float = 2.0) -> None:
        self.store = store
        self.git = git
        self.interval = interval_s
        self._mtimes: dict[str, float] = {}
        self.on_blocked: Callable[[Task, Report], None] | None = None
        self._invalid: dict[str, int] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll()
            except Exception as e:  # noqa: BLE001
                log.error("watcher_error", error=str(e))
            await asyncio.sleep(self.interval)

    async def poll(self) -> list[str]:
        """Check every running/blocked task once. Returns ids whose report changed."""
        changed = []
        for task in self.store.all():
            if task.state not in ("running",):
                continue
            report = self.store.root / task.workdir / "REPORT.md"
            if not report.exists():
                continue
            mtime = report.stat().st_mtime
            if self._mtimes.get(task.id) == mtime:
                continue
            self._mtimes[task.id] = mtime
            await self.handle_report(task, report)
            changed.append(task.id)
        return changed

    async def handle_report(self, task: Task, report_path: Path) -> Report | None:
        raw = report_path.read_text(encoding="utf-8", errors="replace")
        try:
            rep = Report.parse(raw)
        except Exception as e:  # noqa: BLE001
            n = self._invalid.get(task.id, 0) + 1
            self._invalid[task.id] = n
            self.store.event(
                task.id,
                "report_invalid",
                model=task.assigned_to,
                actor="model",
                reason=str(e)[:200],
                count=n,
            )
            if n >= 2:
                self.store.transition(task, "failed", reason="report_invalid x2")
                self.store.event(
                    task.id, "failed", model=task.assigned_to, reason="report_invalid x2"
                )
            return None
        self._invalid[task.id] = 0
        if INJECTION_RE.search(rep.body):
            self.store.event(
                task.id,
                "injection_suspect",
                model=task.assigned_to,
                actor="model",
                snippet=rep.body[:200],
            )
        if rep.dissent:
            self.store.event(
                task.id, "dissent", model=task.assigned_to, actor="model", reason=rep.body[:300]
            )
        self.store.store_report(task, raw, rep.status)
        task.last_report = rep
        sync = await self.git.sync_and_snapshot(
            task.id, task.scope, f"council: {task.id} {rep.status} {rep.percent}%"
        )
        if sync.rejected:
            task.violations = sorted(set(task.violations) | set(sync.rejected))
            self.store.event(
                task.id,
                "scope_violation",
                model=task.assigned_to,
                actor="model",
                files=sync.rejected,
            )
        self.store.event(
            task.id,
            "report",
            model=task.assigned_to,
            actor="model",
            status=rep.status,
            percent=rep.percent,
            touched=rep.touched,
            needs=rep.needs,
            summary=rep.body[:300],
        )
        if rep.status == "done":
            flags = []
            if task.violations:
                flags.append("scope_violation: " + ", ".join(task.violations))
            if not (await self.git.diff_stat(task.id)).strip():
                flags.append("done_without_changes")
            reason = "; ".join(flags) or None
            self.store.transition(task, "review", reason=reason)
            self.store.event(
                task.id,
                "done",
                model=task.assigned_to,
                reason=reason,
                verify=rep.verify,
                touched=rep.touched,
            )
        elif rep.status == "blocked":
            self.store.transition(task, "blocked", reason="; ".join(rep.needs)[:300])
            self.store.event(
                task.id, "blocked", model=task.assigned_to, actor="model", needs=rep.needs
            )
            if self.on_blocked:
                try:
                    self.on_blocked(task, rep)
                except Exception as e:  # noqa: BLE001
                    log.warning("on_blocked_failed", task=task.id, error=str(e))
        elif rep.status == "failed":
            self.store.transition(task, "failed", reason=rep.body[:300])
            self.store.event(
                task.id, "failed", model=task.assigned_to, actor="model", reason=rep.body[:300]
            )
        else:
            self.store.save(task)
        return rep
