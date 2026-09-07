"""Per-model statistics and `trust` (DESIGN.md §16.1, §19.8), persisted in `.council/stats.json`.

trust: probation → standard → trusted. Promotion after N first-pass review_ok; demotion after two
consecutive review_reject. Quality signal that peer agreement cannot fake: `defects_after_merge`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

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
    lines_merged: int = 0  # changed lines in merged tasks (git diff --stat)
    tokens_saved_est: int = 0  # heuristic, see SAVINGS


class Stats(BaseModel):
    models: dict[str, ModelStats] = Field(default_factory=dict)
    counted_tasks: list[str] = Field(default_factory=list)  # merged tasks already in the estimate
    plan_drafts: int = 0  # chair.plan_assist uses
    review_assists: int = 0  # chair.review_assist uses
    assist_tokens_saved_est: int = 0

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


# Rough estimate of the Claude tokens the chair did NOT spend because an executor did the work.
# Per merged task: base (reading the card's context, running tests, iterating) + per changed line
# (writing the code plus re-reading the surrounding file). Assets/3D: images cannot be produced by
# Claude at all, so a fixed value stands for the round-trips they would have cost. Assistants:
# a plan draft replaces the chair's repo read; a review summary replaces reading most of the diff.
# These are deliberately conservative and documented, not measured (CLIs report no token counts).
SAVINGS: dict[str, tuple[int, int]] = {  # role -> (base_tokens, tokens_per_changed_line)
    "implement": (1500, 60),
    "refactor": (1500, 60),
    "docs": (800, 40),
    "assets": (2500, 20),
    "3d": (2500, 20),
    "review": (600, 20),
    "chores": (600, 20),
    "data": (800, 30),
    "contract": (0, 0),
    "adversary": (600, 20),
}
ASSIST_SAVINGS = {"plan_draft": 3000, "review_assist": 800}


def estimate_saved(role: str, lines: int) -> int:
    base, per_line = SAVINGS.get(role, (1000, 40))
    return base + per_line * max(0, lines)


def on_merge(stats: Stats, task_id: str, model: str, role: str, lines: int, initial: Trust) -> int:
    """Count a merged task once. Returns the tokens added to the estimate (0 if already counted)."""
    if task_id in stats.counted_tasks:
        return 0
    m = stats.get(model, initial)
    saved = estimate_saved(role, lines)
    m.lines_merged += lines
    m.tokens_saved_est += saved
    stats.counted_tasks.append(task_id)
    return saved


def on_assist(stats: Stats, kind: str) -> int:
    saved = ASSIST_SAVINGS.get(kind, 0)
    if kind == "plan_draft":
        stats.plan_drafts += 1
    elif kind == "review_assist":
        stats.review_assists += 1
    stats.assist_tokens_saved_est += saved
    return saved


def savings_summary(stats: Stats) -> dict[str, Any]:
    per_model = {
        name: {"merged": m.merged, "lines": m.lines_merged, "tokens_saved_est": m.tokens_saved_est}
        for name, m in sorted(stats.models.items())
        if m.merged or m.tokens_saved_est
    }
    exec_tokens = sum(m.tokens_saved_est for m in stats.models.values())
    total = exec_tokens + stats.assist_tokens_saved_est
    return {
        "tokens_saved_est": total,
        "executor_tokens_saved_est": exec_tokens,
        "assist_tokens_saved_est": stats.assist_tokens_saved_est,
        "tasks_counted": len(stats.counted_tasks),
        "lines_merged": sum(m.lines_merged for m in stats.models.values()),
        "plan_drafts": stats.plan_drafts,
        "review_assists": stats.review_assists,
        "per_model": per_model,
        "method": (
            "heuristic, not measured: per merged task base + per changed line by role "
            f"({', '.join(f'{r} {b}+{p}/line' for r, (b, p) in SAVINGS.items() if b)}); "
            f"plan draft {ASSIST_SAVINGS['plan_draft']}, review summary "
            f"{ASSIST_SAVINGS['review_assist']}. Claude's own review/merge tokens are not "
            "subtracted."
        ),
    }


def savings_md(stats: Stats) -> str:
    s = savings_summary(stats)
    rows = [
        f"**≈ {int(s['tokens_saved_est']):,} Claude tokens saved** — {s['tasks_counted']} merged "
        f"tasks, {s['lines_merged']} changed lines, {s['plan_drafts']} plan drafts, "
        f"{s['review_assists']} review summaries.",
        "",
        "| model | merged | lines | tokens saved (est.) |",
        "|---|---|---|---|",
    ]
    for name, m in s["per_model"].items():
        rows.append(f"| {name} | {m['merged']} | {m['lines']} | {m['tokens_saved_est']:,} |")
    if s["assist_tokens_saved_est"]:
        rows.append(f"| assistants | – | – | {int(s['assist_tokens_saved_est']):,} |")
    rows += ["", f"_Method: {s['method']}_"]
    return "\n".join(rows)


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
