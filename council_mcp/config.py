"""Pydantic model of `.council/council.json` (v1 subset — DESIGN.md §3.1).

Secrets never live here; `${ENV_VAR}` placeholders in string fields are expanded at load time.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    # claude-sub: `--effort low|medium|high|xhigh|max` (Claude Code CLI)
    effort: Reasoning | None = None
    # claude-sub: which Claude account this executor runs under — a key of `claude_profiles`.
    # None = the default Claude Code login. `config_dir` is derived (CLAUDE_CONFIG_DIR).
    profile: str | None = None
    config_dir: str | None = None
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
    # Per-model chains tried before `model`, e.g. {"fable": ["fable-alt", "codex"]} — a Claude
    # executor out of quota moves to the same executor on the other account first.
    by_model: dict[str, list[str]] = Field(default_factory=dict)

    def targets(self, model: str) -> list[str]:
        out: list[str] = []
        for t in [*self.by_model.get(model, []), *([self.model] if self.model else [])]:
            if t and t != model and t not in out:
                out.append(t)
        return out


class Routing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    by_privacy: dict[Privacy, list[str]] = Field(default_factory=dict)
    by_role: dict[Role, list[str]] = Field(default_factory=dict)
    second_opinion: list[str] = Field(default_factory=list)


class Chair(BaseModel):
    """Who helps the chair (Claude Code) and who codes. Defaults keep the original setup: Claude
    plans and reviews alone, executors code. `plan_assist`/`review_assist` name a model that drafts
    task cards / summarises a diff for Claude (decisions stay with Claude). `coder` is
    "executors" or a model name (e.g. `fable` = Claude via `claude -p --effort medium`) that is
    put first for `implement`/`refactor`."""

    model_config = ConfigDict(extra="forbid")
    plan_assist: str | None = None
    review_assist: str | None = None
    coder: str = "executors"


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
    chair: Chair = Field(default_factory=Chair)
    # Claude accounts for `claude-sub` executors: name -> CLAUDE_CONFIG_DIR (None = default login).
    # Each extra profile is logged in once by the user (`claude auth login` with that dir).
    claude_profiles: dict[str, str | None] = Field(
        default_factory=lambda: {"default": None}  # type: ignore[arg-type]
    )

    @model_validator(mode="after")
    def _profiles(self) -> CouncilConfig:
        import os

        for name, m in self.models.items():
            if m.profile is None:
                continue
            if m.profile not in self.claude_profiles:
                raise ValueError(f"model '{name}': profile '{m.profile}' not in claude_profiles")
            d = self.claude_profiles[m.profile]
            m.config_dir = str(Path(os.path.expanduser(d))) if d else None
        for name, chain in self.fallback.by_model.items():
            for t in chain:
                if t not in self.models:
                    raise ValueError(f"fallback.by_model['{name}'] names unknown model '{t}'")
        return self

    @model_validator(mode="after")
    def _chair_refs(self) -> CouncilConfig:
        for field in ("plan_assist", "review_assist"):
            v = getattr(self.chair, field)
            if v is not None and v not in self.models:
                raise ValueError(f"chair.{field}='{v}' is not a configured model")
        if self.chair.coder != "executors" and self.chair.coder not in self.models:
            raise ValueError(f"chair.coder='{self.chair.coder}' is not a configured model")
        return self

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
        order = list(self.routing.by_role.get(role, []))
        coder = self.chair.coder
        if coder != "executors" and role in ("implement", "refactor"):
            order = [coder] + [m for m in order if m != coder]
        return [m for m in order if m in allowed and m in self.models and self.models[m].enabled]


CONFIG_PATH = Path(".council") / "council.json"


def load(repo_root: Path | None = None) -> CouncilConfig:
    root = repo_root or Path.cwd()
    path = root / CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `council init` or copy templates/council.json"
        )
    return CouncilConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
