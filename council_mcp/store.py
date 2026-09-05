"""TaskStore: `.council/tasks/*.json`, `events.jsonl`, `reports/`, `TASKS.md` (DESIGN.md §3).

State machine: queued → running → review → merged; running → blocked → running;
running|review → failed; review → running (reject, attempt+1, max 3).
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from council_mcp.config import Privacy, Role

State = Literal["queued", "running", "blocked", "review", "merged", "failed"]
ReportStatus = Literal["plan", "progress", "blocked", "done", "failed"]
EventType = Literal[
    "planned",
    "dispatched",
    "report",
    "report_invalid",
    "scope_violation",
    "blocked",
    "answered",
    "done",
    "failed",
    "review_ok",
    "review_reject",
    "merged",
    "cancelled",
    "injection_suspect",
    "dissent",
    "trust_promoted",
    "trust_demoted",
    "defect",
    "compare",
    "fallback",
    "cooldown",
]
Actor = Literal["claude", "system", "model"]

_TRANSITIONS: dict[State, set[State]] = {
    "queued": {"running", "failed"},
    "running": {"blocked", "review", "failed", "queued"},
    "blocked": {"running", "failed"},
    "review": {"merged", "running", "failed"},
    "merged": set(),
    "failed": {"queued"},
}
MAX_ATTEMPTS = 3


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lenient(fm: str) -> dict[str, Any]:
    """Fallback for front-matter that is not strict YAML (e.g. `needs: [why?]`)."""
    out: dict[str, Any] = {}
    current: str | None = None  # key whose block list (`  - item`) we are collecting
    for line in fm.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current is not None:
            lst = out.setdefault(current, [])
            if isinstance(lst, list):
                lst.append(stripped[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if not k or " " in k:
            continue
        if v == "":
            out[k] = []
            current = k
            continue
        current = None
        if v.startswith("[") and v.endswith("]"):
            out[k] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        elif v.isdigit():
            out[k] = int(v)
        else:
            out[k] = v.strip("\"'")
    return out


class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: str = ""
    status: ReportStatus
    percent: int = 0
    touched: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    dissent: bool = False
    body: str = ""

    @classmethod
    def parse(cls, text: str) -> Report:
        m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?(.*)", text, re.S)
        if not m:
            raise ValueError("REPORT.md has no YAML front-matter")
        try:
            data = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            data = _lenient(m.group(1))
        if not isinstance(data, dict):
            raise ValueError("front-matter is not a mapping")
        data["body"] = m.group(2).strip()
        for k in ("touched", "needs", "verify"):
            v = data.get(k)
            if isinstance(v, str):
                data[k] = [v]
            elif isinstance(v, list):
                # YAML turns `- text: more text` into {"text": "more text"} — flatten to a string
                data[k] = [
                    ": ".join(f"{a}: {b}" if b not in (None, "") else str(a) for a, b in x.items())
                    if isinstance(x, dict)
                    else str(x)
                    for x in v
                ]
            elif v is None:
                data[k] = []
        if isinstance(data.get("dissent"), str):
            data["dissent"] = data["dissent"].strip().lower() in ("true", "yes", "1")
        return cls.model_validate(data)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    role: Role
    privacy: Privacy
    goal: str
    scope: list[str]
    context_files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    assigned_to: str | None = None
    state: State = "queued"
    attempt: int = 1
    branch: str = ""
    worktree: str = ""
    workdir: str = ""
    created: str = Field(default_factory=now)
    started: str | None = None
    finished: str | None = None
    last_report: Report | None = None
    reports: int = 0
    violations: list[str] = Field(default_factory=list)
    reason: str | None = None  # why it is in its current state (§16.9)
    fallbacks: int = 0  # how many times this task was moved to the fallback model

    def model_post_init(self, _ctx: Any) -> None:
        self.branch = self.branch or f"council/{self.id}"
        self.worktree = self.worktree or f".council/worktrees/{self.id}"
        self.workdir = self.workdir or f".council/work/{self.id}"


class Event(BaseModel):
    ts: str = Field(default_factory=now)
    task: str
    type: EventType
    model: str | None = None
    actor: Actor = "system"
    reason: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TaskStore:
    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root
        self.dir = repo_root / ".council"
        self.tasks_dir = self.dir / "tasks"
        self.reports_dir = self.dir / "reports"
        self.events_path = self.dir / "events.jsonl"
        self.last_seen_path = self.dir / ".last_seen"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ---- tasks -------------------------------------------------------------
    def next_id(self) -> str:
        nums = [int(p.stem[2:]) for p in self.tasks_dir.glob("T-*.json") if p.stem[2:].isdigit()]
        return f"T-{(max(nums) + 1 if nums else 1):03d}"

    def save(self, task: Task) -> None:
        path = self.tasks_dir / f"{task.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(task.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)
        self.render_tasks_md()

    def get(self, task_id: str) -> Task:
        path = self.tasks_dir / f"{task_id}.json"
        if not path.exists():
            raise KeyError(f"unknown task {task_id}")
        return Task.model_validate_json(path.read_text(encoding="utf-8"))

    def all(self) -> list[Task]:
        return sorted(
            (
                Task.model_validate_json(p.read_text(encoding="utf-8"))
                for p in self.tasks_dir.glob("T-*.json")
            ),
            key=lambda t: t.id,
        )

    def transition(self, task: Task, to: State, reason: str | None = None) -> Task:
        if to not in _TRANSITIONS[task.state]:
            raise ValueError(f"{task.id}: illegal transition {task.state} → {to}")
        task.state = to
        task.reason = reason
        if to == "running" and not task.started:
            task.started = now()
        if to in ("review", "merged", "failed"):
            task.finished = now()
        self.save(task)
        return task

    # ---- events ------------------------------------------------------------
    def event(
        self,
        task: str,
        type_: EventType,
        *,
        model: str | None = None,
        actor: Actor = "system",
        reason: str | None = None,
        **data: Any,
    ) -> Event:
        ev = Event(task=task, type=type_, model=model, actor=actor, reason=reason, data=data)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(ev.model_dump_json(exclude_none=True) + "\n")
        return ev

    def events(self, since: str | None = None) -> list[Event]:
        if not self.events_path.exists():
            return []
        out = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ev = Event.model_validate_json(line)
                if since is None or ev.ts > since:
                    out.append(ev)
        return out

    def new_events(self, mark: bool = True) -> list[Event]:
        since = self.last_seen_path.read_text().strip() if self.last_seen_path.exists() else None
        evs = self.events(since)
        if mark and evs:
            self.last_seen_path.write_text(evs[-1].ts)
        return evs

    # ---- reports -----------------------------------------------------------
    def store_report(self, task: Task, raw: str, status: str) -> Path:
        d = self.reports_dir / task.id
        d.mkdir(parents=True, exist_ok=True)
        task.reports += 1
        path = d / f"{task.reports:03d}-{status}.md"
        path.write_text(raw, encoding="utf-8")
        return path

    def report_text(self, task_id: str, n: int | None = None) -> str | None:
        d = self.reports_dir / task_id
        files = sorted(d.glob("*.md")) if d.exists() else []
        if not files:
            return None
        return (files[n - 1] if n else files[-1]).read_text(encoding="utf-8")

    # ---- board -------------------------------------------------------------
    def render_tasks_md(self) -> str:
        rows = [
            "# Council tasks",
            "",
            "_Generated from `.council/tasks/*.json` — do not edit._",
            "",
            "| id | state | role | model | attempt | % | title | reason |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for t in self.all():
            pct = t.last_report.percent if t.last_report else 0
            rows.append(
                f"| {t.id} | {t.state} | {t.role} | {t.assigned_to or '-'} | {t.attempt} | {pct} | "
                f"{t.title} | {t.reason or ''} |"
            )
        text = "\n".join(rows) + "\n"
        (self.dir / "TASKS.md").write_text(text, encoding="utf-8")
        return text
