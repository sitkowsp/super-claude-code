"""Per-model statistics and `trust` (DESIGN.md §16.1, §19.8), persisted in `.council/stats.json`.

trust: probation → standard → trusted. Promotion after N first-pass review_ok; demotion after two
consecutive review_reject. Quality signal that peer agreement cannot fake: `defects_after_merge`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Trust = Literal["probation", "standard", "trusted"]
_ORDER: list[Trust] = ["probation", "standard", "trusted"]


class TrustPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    promote_after: int = 3  # first-pass review_ok needed for the next level
    demote_after: int = 2  # consecutive review_reject
    probation_max_lines: int = 150  # changed lines allowed on probation
    initial: Trust = "probation"


class ModelStats(BaseModel):
    trust: Trust = "probation"
    tasks: int = 0
    review_ok: int = 0
    review_reject: int = 0
    first_pass_ok: int = 0  # review_ok on attempt 1, resets on promotion
    consecutive_rejects: int = 0
    defects_after_merge: int = 0
    merged: int = 0
    cooldown_until: str | None = None  # ISO time; model skipped by routing until then
    fallbacks: int = 0  # times work was moved away from this model


class Stats(BaseModel):
    models: dict[str, ModelStats] = Field(default_factory=dict)

    def get(self, model: str, initial: Trust = "probation") -> ModelStats:
        if model not in self.models:
            self.models[model] = ModelStats(trust=initial)
        return self.models[model]


STATS_PATH = Path(".council") / "stats.json"


def load(root: Path) -> Stats:
    p = root / STATS_PATH
    if not p.exists():
        return Stats()
    return Stats.model_validate_json(p.read_text(encoding="utf-8"))


def save(root: Path, stats: Stats) -> None:
    p = root / STATS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(stats.model_dump_json(indent=2), encoding="utf-8")


def on_verdict(
    stats: Stats, model: str, ok: bool, attempt: int, policy: TrustPolicy
) -> tuple[Trust, Trust, str | None]:
    """Update stats for a verdict. Returns (old_trust, new_trust, reason-or-None)."""
    m = stats.get(model, policy.initial)
    old = m.trust
    reason = None
    if ok:
        m.review_ok += 1
        m.consecutive_rejects = 0
        if attempt == 1:
            m.first_pass_ok += 1
        if m.first_pass_ok >= policy.promote_after and old != "trusted":
            m.trust = _ORDER[_ORDER.index(old) + 1]
            m.first_pass_ok = 0
            reason = f"{policy.promote_after} first-pass review_ok"
    else:
        m.review_reject += 1
        m.consecutive_rejects += 1
        m.first_pass_ok = 0
        if m.consecutive_rejects >= policy.demote_after and old != "probation":
            m.trust = _ORDER[_ORDER.index(old) - 1]
            m.consecutive_rejects = 0
            reason = f"{policy.demote_after} consecutive review_reject"
    return old, m.trust, reason


def on_defect(stats: Stats, model: str, policy: TrustPolicy) -> tuple[Trust, Trust]:
    """A defect found after merge: counts against the model and drops it one trust level."""
    m = stats.get(model, policy.initial)
    old = m.trust
    m.defects_after_merge += 1
    if old != "probation":
        m.trust = _ORDER[_ORDER.index(old) - 1]
    return old, m.trust


def in_cooldown(m: ModelStats, now: str) -> bool:
    return bool(m.cooldown_until and m.cooldown_until > now)


def diff_lines(diff_stat: str) -> int:
    """Changed lines from `git diff --stat` summary line."""
    total = 0
    for part in diff_stat.strip().splitlines()[-1:] if diff_stat.strip() else []:
        for token in part.split(","):
            token = token.strip()
            if token.endswith(("(+)", "(-)")):
                try:
                    total += int(token.split()[0])
                except ValueError:
                    pass
    return total


# ---- lessons (§16.12) ---------------------------------------------------------
LESSONS_PATH = Path(".council") / "LESSONS.md"


def add_lesson(root: Path, model: str, role: str, text: str) -> None:
    p = root / LESSONS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(
            "# Lessons\n\nOne line per review_reject / dissent / defect: "
            "`- [model/role] rule`.\n\n",
            encoding="utf-8",
        )
    with p.open("a", encoding="utf-8") as f:
        f.write(f"- [{model}/{role}] {text.strip()}\n")


def lessons_for(root: Path, model: str, role: str, limit: int = 10) -> list[str]:
    p = root / LESSONS_PATH
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"- [{model}/{role}]") or line.startswith(f"- [{model}/*]"):
            out.append(line[line.index("]") + 1 :].strip())
    return out[-limit:]


def summary(stats: Stats) -> str:
    rows = [
        "| model | trust | tasks | ok | reject | first-pass | defects | merged |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, m in sorted(stats.models.items()):
        rows.append(
            f"| {name} | {m.trust} | {m.tasks} | {m.review_ok} | {m.review_reject} | "
            f"{m.first_pass_ok} | {m.defects_after_merge} | {m.merged} |"
        )
    return "\n".join(rows)


def dump(stats: Stats) -> dict[str, object]:
    data: dict[str, object] = json.loads(stats.model_dump_json())
    return data
