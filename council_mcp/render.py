"""Render executor-facing files from a task card (DESIGN.md §4.1–4.2).

  TASK.md    always
  AGENTS.md  codex / copilot   (Charter + pointer to TASK.md)
  GEMINI.md  gemini
  system     ollama / claude-sub (Charter as system prompt)
The Charter is `.council/CHARTER.md` if the target repo has one, else the packaged template.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from council_mcp import stats
from council_mcp.config import Budget
from council_mcp.store import Task

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,
)


def charter(repo_root: Path) -> str:
    local = repo_root / ".council" / "CHARTER.md"
    return (local if local.exists() else TEMPLATES / "CHARTER.md").read_text(encoding="utf-8")


def memory(repo_root: Path, memory_file: str) -> str:
    p = repo_root / memory_file
    return p.read_text(encoding="utf-8") if p.exists() else ""


def task_md(task: Task, budget: Budget, lessons: list[str] | None = None) -> str:
    return _env.get_template("TASK.md.j2").render(task=task, budget=budget, lessons=lessons or [])


def agents_md(repo_root: Path) -> str:
    return _env.get_template("AGENTS.md.j2").render(charter=charter(repo_root))


def system_prompt(repo_root: Path, memory_file: str) -> str:
    return _env.get_template("system.j2").render(
        charter=charter(repo_root), memory=memory(repo_root, memory_file)
    )


def cli_prompt(task: Task, resume: bool, inline_charter: str | None = None) -> str:
    return _env.get_template("prompt_cli.j2").render(
        task=task, resume=resume, charter=inline_charter
    )


def write_all(
    repo_root: Path, workdir: Path, task: Task, budget: Budget, adapter: str, memory_file: str
) -> dict[str, Path]:
    """Write TASK.md (+ AGENTS.md/GEMINI.md/MEMORY.md) into the executor workdir."""
    out: dict[str, Path] = {}
    lessons = (
        stats.lessons_for(repo_root, task.assigned_to or "", task.role) if task.assigned_to else []
    )
    (workdir / "TASK.md").write_text(task_md(task, budget, lessons), encoding="utf-8")
    out["task"] = workdir / "TASK.md"
    mem = memory(repo_root, memory_file)
    if mem:
        (workdir / "MEMORY.md").write_text(mem, encoding="utf-8")
    name = {
        "codex": "AGENTS.md",
        "copilot": "AGENTS.md",
        "gemini": "GEMINI.md",
        "antigravity": "AGENTS.md",
    }.get(adapter)
    if name:
        (workdir / name).write_text(agents_md(repo_root), encoding="utf-8")
        out["charter"] = workdir / name
    return out
