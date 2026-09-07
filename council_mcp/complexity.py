"""Deterministic task-complexity assessment (no model calls, same input → same answer).

Drives two knobs at dispatch time (delegation.auto_effort, default on):
- model tier: a `simple` task may go to a cheaper candidate (ModelConfig.tier "low"), a `complex`
  one prefers a "high"-tier candidate; `standard` keeps the routing order untouched;
- effort: codex gets `-c model_reasoning_effort=…`, claude-sub gets `--effort …`
  (simple→low, standard→medium, complex→high). Other adapters have no such knob and ignore it.
The assessment and its reasons land in the `dispatched` event, so `council_why` explains it.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from council_mcp.store import Task

Level = str  # "simple" | "standard" | "complex"

EFFORT = {"simple": "low", "standard": "medium", "complex": "high"}

_COMPLEX_RE = re.compile(
    r"refactor|architect|migrat|concurren|race|deadlock|parser|protoc|crypto|security|"
    r"optimi|performance|wydajno|algorithm|solver|scheduler|transaction|współbie|integracj",
    re.I,
)
_SIMPLE_RE = re.compile(
    r"typo|literówk|rename|zmien nazw|comment|komentarz|readme|changelog|bump|format|lint|"
    r"one[- ]lin|jedna linia|whitespace|copy[- ]?paste",
    re.I,
)
_ROLE_WEIGHT = {"implement": 3, "refactor": 4, "3d": 2, "assets": 1, "data": 1}


class Assessment(BaseModel):
    level: Level
    score: int
    effort: str
    reasons: list[str]


def assess(task: Task) -> Assessment:
    score = 0
    reasons: list[str] = []
    text = f"{task.title} {task.goal}"

    w = _ROLE_WEIGHT.get(task.role, 0)
    if w:
        score += w
        reasons.append(f"role {task.role} +{w}")
    extra_scope = max(0, len(task.scope) - 1) * 2
    if extra_scope:
        score += min(extra_scope, 6)
        reasons.append(f"{len(task.scope)} scope globs +{min(extra_scope, 6)}")
    if any("**" in s for s in task.scope):
        score += 3
        reasons.append("recursive scope (**) +3")
    elif any(s.endswith("/") for s in task.scope):
        score += 2
        reasons.append("whole-directory scope +2")
    words = len(task.goal.split())
    if words > 60:
        score += 3
        reasons.append("long goal +3")
    elif words > 25:
        score += 2
        reasons.append("detailed goal +2")
    acc = max(0, len(task.acceptance) - 1)
    if acc:
        score += min(acc, 4)
        reasons.append(f"{len(task.acceptance)} acceptance criteria +{min(acc, 4)}")
    if len(task.context_files) > 2:
        score += 1
        reasons.append("many context files +1")
    if task.depends_on:
        score += min(len(task.depends_on), 2)
        reasons.append(f"depends_on +{min(len(task.depends_on), 2)}")
    hits = min(len(set(_COMPLEX_RE.findall(text.lower()))), 2) * 3
    if hits:
        score += hits
        reasons.append(f"complexity keywords +{hits}")
    simp = min(len(set(_SIMPLE_RE.findall(text.lower()))), 2) * 3
    if simp:
        score -= simp
        reasons.append(f"simplicity keywords -{simp}")
    if task.attempt > 1:
        bump = 2 * (task.attempt - 1)
        score += bump
        reasons.append(f"attempt {task.attempt} +{bump}")

    level = "simple" if score <= 2 else ("standard" if score <= 7 else "complex")
    return Assessment(level=level, score=score, effort=EFFORT[level], reasons=reasons)
