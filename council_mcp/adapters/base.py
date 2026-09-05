"""Adapter protocol (DESIGN.md §5.1).

`probe`/`ask`: availability and one-shot questions.
`run`: start the executor on a task inside its workdir and return a RunHandle; the adapter enforces
the time budget (soft: terminate + 60 s grace, hard: kill) and reports the exit code. Adapters never
read REPORT.md — the Watcher does.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from council_mcp.config import Budget
from council_mcp.store import Task


class Capabilities(BaseModel):
    name: str
    adapter: str
    enabled: bool
    version: str | None = None
    path: str | None = None
    flags: list[str] = Field(default_factory=list)  # detected from --help
    models: list[str] = Field(default_factory=list)  # ollama: /api/tags
    error: str | None = None


class AskResult(BaseModel):
    model: str
    text: str
    duration_s: float
    tokens_in: int | None = None
    tokens_out: int | None = None


@dataclass
class RunHandle:
    task_id: str
    model: str
    done: asyncio.Event = field(default_factory=asyncio.Event)
    exit_code: int | None = None
    error: str | None = None
    log_path: Path | None = None
    _cancel: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def finish(self, exit_code: int, error: str | None = None) -> None:
        self.exit_code = exit_code
        self.error = error
        self.done.set()


class Adapter(Protocol):
    name: str

    async def probe(self) -> Capabilities: ...

    async def ask(self, prompt: str, files: list[Path] | None = None) -> AskResult:
        """One-shot question, no worktree, no tools. Files (if any) are inlined into the prompt."""
        ...

    async def run(self, task: Task, workdir: Path, budget: Budget, resume: bool) -> RunHandle:
        """Start the executor in `workdir` (files already rendered). Returns immediately."""
        ...


MAX_FILE_CHARS = 40_000


def inline_files(prompt: str, files: list[Path] | None, root: Path | None = None) -> str:
    """Append file contents to the prompt as fenced blocks. Refuses to leave `root` (cwd)."""
    if not files:
        return prompt
    base = (root or Path.cwd()).resolve()
    parts = [prompt, "", "## Files"]
    for f in files:
        p = (base / f).resolve()
        if not p.is_relative_to(base):
            raise ValueError(f"refusing to read outside repo: {f}")
        body = p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        parts += [f"### {Path(f).as_posix()}", "```", body, "```"]
    return "\n".join(parts)


async def wait_with_budget(
    proc: asyncio.subprocess.Process, handle: RunHandle, budget: Budget
) -> int:
    """Wait for a subprocess honouring soft/hard budget and cancellation."""
    soft = budget.soft_minutes * 60
    hard = budget.hard_minutes * 60
    waiter = asyncio.ensure_future(proc.wait())
    canceller = asyncio.ensure_future(handle._cancel.wait())
    try:
        done, _ = await asyncio.wait(
            {waiter, canceller}, timeout=soft, return_when=asyncio.FIRST_COMPLETED
        )
        if waiter in done:
            return waiter.result()
        proc.terminate()
        try:
            return await asyncio.wait_for(proc.wait(), timeout=min(60, max(1, hard - soft)))
        except TimeoutError:
            proc.kill()
            return await proc.wait()
    finally:
        canceller.cancel()
        if not waiter.done():
            waiter.cancel()
