"""Playbooks (DESIGN.md §15): how Claude splits work when it decides. A playbook is a pattern,
not an order — the planner adapts assignments to `capabilities.json` and `stats`.

Shipped playbooks live in `playbooks/`; user playbooks in `.council/playbooks/` take precedence.
Selection is deterministic keyword matching on `trigger` (§15.4); no match → `feature`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SHIPPED = Path(__file__).resolve().parent.parent / "playbooks"
DEFAULT = "feature"


class PlaybookTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    assign: str  # "claude" or a routing hint: model name or "by_role"
    slice: str
    privacy: str = "public"


class Wave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int
    parallel: bool = False
    tasks: list[PlaybookTask]


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    trigger: list[str] = Field(default_factory=list)
    claude_keeps: list[str] = Field(default_factory=list)
    waves: list[Wave]
    notes: list[str] = Field(default_factory=list)
    source: str = "shipped"


def load_all(repo_root: Path) -> dict[str, Playbook]:
    out: dict[str, Playbook] = {}
    for src, d in (("shipped", SHIPPED), ("user", repo_root / ".council" / "playbooks")):
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            pb = Playbook.model_validate(json.loads(p.read_text(encoding="utf-8")))
            pb.source = src
            out[pb.name] = pb  # user overrides shipped with the same name
    return out


def select(
    goal: str, books: dict[str, Playbook], forced: str | None = None
) -> tuple[Playbook, str]:
    """Returns (playbook, reason). Score = number of distinct trigger phrases found in the goal."""
    if forced:
        if forced not in books:
            raise KeyError(f"unknown playbook '{forced}'; known: {sorted(books)}")
        return books[forced], "forced by user"
    text = goal.lower()
    best: tuple[int, str] | None = None
    for name, pb in books.items():
        hits = [t for t in pb.trigger if re.search(r"\b" + re.escape(t.lower()) + r"\b", text)]
        if hits and (
            best is None or len(hits) > best[0] or (len(hits) == best[0] and name < best[1])
        ):
            best = (len(hits), name)
            best_hits = hits
    if best:
        return books[best[1]], f"trigger match: {best_hits}"
    if DEFAULT in books:
        return books[DEFAULT], "no trigger matched → default"
    raise KeyError("no playbooks available")
