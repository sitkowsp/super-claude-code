"""Delegation policy (DESIGN.md §22): when should Claude do it itself, delegate, or ask?

Goal: save the user's Claude tokens. Deterministic rules the orchestrator consults before doing
work by hand; `council_should_delegate` exposes them as a tool, the SessionStart hook injects a
compact reminder, and `/council:offload` hands the rest of a session to executors when Claude's
usage window is about to run out.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["auto", "ask", "off"]
Verdict = Literal["delegate", "self", "ask"]

# Roles where delegation is almost always cheaper than Claude doing it inline.
ALWAYS_DELEGATE = ("docs", "assets", "3d", "chores", "review", "data")


class DelegationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode = "auto"  # auto: delegate without asking when rules say so; ask: always confirm
    min_lines: int = 40  # estimated changed lines above which implement work is delegated
    min_files: int = 2  # or number of files to touch
    always_delegate_roles: list[str] = Field(default_factory=lambda: list(ALWAYS_DELEGATE))
    keep_for_claude: list[str] = Field(
        default_factory=lambda: ["contracts", "integration", "merge", "security", "small hotfix"]
    )
    ask_when_unsure: bool = True
    session_budget_minutes: int = 300  # Claude's rolling usage window (5 h)
    warn_after_minutes: int = 210  # suggest offloading after this much continuous session time


class Recommendation(BaseModel):
    verdict: Verdict
    reason: str
    role: str
    suggested_model: str | None = None


def decide(
    policy: DelegationPolicy,
    role: str,
    est_lines: int,
    est_files: int,
    touches_seams: bool,
    privacy: str,
    candidates: list[str],
) -> Recommendation:
    """Pure function: same inputs → same recommendation."""
    if policy.mode == "off":
        return Recommendation(verdict="self", reason="delegation disabled in policy", role=role)
    if not candidates:
        return Recommendation(
            verdict="self", reason=f"no executor for role={role} privacy={privacy}", role=role
        )
    model = candidates[0]
    if touches_seams:
        return Recommendation(
            verdict="self",
            role=role,
            reason="touches interfaces/integration — Claude keeps the seams",
        )
    if role in policy.always_delegate_roles:
        v: Verdict = "ask" if policy.mode == "ask" else "delegate"
        return Recommendation(
            verdict=v,
            role=role,
            suggested_model=model,
            reason=f"role '{role}' is always cheaper on an executor",
        )
    big = est_lines >= policy.min_lines or est_files >= policy.min_files
    if big:
        v = "ask" if policy.mode == "ask" else "delegate"
        return Recommendation(
            verdict=v,
            role=role,
            suggested_model=model,
            reason=f"~{est_lines} lines / {est_files} files ≥ threshold "
            f"({policy.min_lines}/{policy.min_files})",
        )
    if est_lines < policy.min_lines // 2 and est_files <= 1:
        return Recommendation(
            verdict="self",
            role=role,
            reason="small, single-file change — faster inline than a task round-trip",
        )
    return Recommendation(
        verdict="ask" if policy.ask_when_unsure else "self",
        role=role,
        suggested_model=model,
        reason="borderline size — unsure",
    )


# ---- session clock ----------------------------------------------------------------
SESSION_FILE = Path(".council") / ".session_started"


def session_started(root: Path) -> datetime:
    p = root / SESSION_FILE
    if p.exists():
        try:
            return datetime.fromisoformat(p.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    now = datetime.now(UTC)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")
    return now


def reset_session(root: Path) -> None:
    p = root / SESSION_FILE
    if p.exists():
        p.unlink()


def session_minutes(root: Path) -> int:
    return max(0, int((datetime.now(UTC) - session_started(root)).total_seconds() // 60))


def budget_hint(policy: DelegationPolicy, minutes: int) -> str | None:
    """A one-line warning when the Claude usage window is likely running out."""
    if minutes >= policy.warn_after_minutes:
        left = max(0, policy.session_budget_minutes - minutes)
        return (
            f"[council] this session has run ~{minutes} min; Claude's usage window may end in "
            f"~{left} min — offload remaining implement/docs work to executors "
            f"(/council:offload) and keep only review/merge for Claude"
        )
    return None


def reminder(policy: DelegationPolicy, ready: list[str]) -> str:
    """Compact policy reminder for the SessionStart hook (goes into Claude's context)."""
    if policy.mode == "off" or not ready:
        return ""
    return (
        "[council] token policy: delegate docs/assets/chores/review/data and any change ≥"
        f"{policy.min_lines} lines or ≥{policy.min_files} files to executors ({', '.join(ready)}); "
        "Claude keeps contracts, integration, merge. Use council_should_delegate when unsure; "
        + (
            "ask the user only for borderline cases."
            if policy.mode == "auto"
            else "confirm before delegating."
        )
    )
