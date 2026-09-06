"""Pydantic model of `.council/council.json` (v1 subset — DESIGN.md §3.1).

Secrets never live here; `${ENV_VAR}` placeholders in string fields are expanded at load time.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from council_mcp.obsidian import ObsidianConfig
from council_mcp.policy import DelegationPolicy
from council_mcp.stats import TrustPolicy

Role = Literal[
    "implement",
    "refactor",
    "docs",
    "assets",
    "3d",
    "review",
    "chores",
    "data",
    "contract",
    "adversary",
]
Reasoning = Literal["low", "medium", "high", "xhigh", "max"]
Privacy = Literal["public", "internal", "local-only"]
AdapterName = Literal["ollama", "gemini", "antigravity", "codex", "copilot", "grok", "claude-sub"]

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def expand_env(value: str) -> str:
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    soft_minutes: int = 20
    hard_minutes: int = 25
    max_turns: int = 30


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter: AdapterName
    enabled: bool = True
    max_parallel: int = 1
    roles: list[Role] = Field(default_factory=list)
    privacy: list[Privacy] = Field(default_factory=lambda: ["public"])  # type: ignore[arg-type,unused-ignore]
    # ollama
    url: str | None = None
    model: str | None = None
    num_ctx: int = 32768
    num_predict: int = 4096
    # CLI adapters
    cmd: str | None = None
    # codex: `-c model_reasoning_effort=…` / `-c model_context_window=…` (GPT-6 Astra: low…max)
    reasoning: Reasoning | None = None
    context_window: int | None = None
    # grok: only the CLI adapter exists (DESIGN.md 19.5 cut `pull`)
    mode: Literal["cli"] | None = None

    @field_validator("url", "cmd", "model", mode="before")
    @classmethod
    def _expand(cls, v: object) -> object:
        return expand_env(v) if isinstance(v, str) else v


class Fallback(BaseModel):
    """When an executor is out of quota, not responding or unavailable, re-queue the task on
    `model` (default: the cheap Claude) and put the failing model on cooldown."""

    model_config = ConfigDict(extra="forbid")
    model: str | None = "cheap"
    on: list[Literal["quota", "no_response", "unavailable"]] = Field(
        default_factory=lambda: ["quota", "no_response", "unavailable"]  # type: ignore[arg-type,unused-ignore]
    )
    cooldown_minutes: int = 60
    max_fallbacks: int = 1  # per task


class Routing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    by_privacy: dict[Privacy, list[str]] = Field(default_factory=dict)
    by_role: dict[Role, list[str]] = Field(default_factory=dict)
    second_opinion: list[str] = Field(default_factory=list)


class CouncilConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    max_parallel: Annotated[int, Field(ge=1)] = 3
    budget: Budget = Field(default_factory=Budget)
    models: dict[str, ModelConfig]
    routing: Routing = Field(default_factory=Routing)
    never_share: list[str] = Field(default_factory=list)
    memory_file: str = ".council/MEMORY.md"
    # gates: commands run in the task worktree before review ("before_review") and on main
    # after merge ("after_merge"). Keys are free-form stages; DESIGN.md §14.5.
    gates: dict[str, list[str]] = Field(default_factory=dict)
    trust: TrustPolicy = Field(default_factory=TrustPolicy)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    fallback: Fallback = Field(default_factory=Fallback)
    delegation: DelegationPolicy = Field(default_factory=DelegationPolicy)

    @field_validator("models")
    @classmethod
    def _model_names(cls, v: dict[str, ModelConfig]) -> dict[str, ModelConfig]:
        bad = [k for k in v if not re.fullmatch(r"[a-z][a-z0-9-]*", k)]
        if bad:
            raise ValueError(f"model names must be lowercase slugs: {bad}")
        return v

    def candidates(self, role: Role, privacy: Privacy) -> list[str]:
        """Routing rule (§3.1): ordered by_role list filtered by by_privacy, enabled only."""
        allowed = set(self.routing.by_privacy.get(privacy, []))
        return [
            m
            for m in self.routing.by_role.get(role, [])
            if m in allowed and m in self.models and self.models[m].enabled
        ]


CONFIG_PATH = Path(".council") / "council.json"


def load(repo_root: Path | None = None) -> CouncilConfig:
    root = repo_root or Path.cwd()
    path = root / CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `council init` or copy templates/council.json"
        )
    return CouncilConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
