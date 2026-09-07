from __future__ import annotations

from council_mcp import complexity
from council_mcp.adapters.cli import CliAdapter
from council_mcp.config import CouncilConfig, ModelConfig
from council_mcp.store import Task


def _task(**kw) -> Task:  # type: ignore[no-untyped-def]
    base = dict(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["a.py"])
    base.update(kw)
    return Task(**base)  # type: ignore[arg-type]


def test_assess_levels_are_deterministic_and_explained() -> None:
    simple = _task(role="docs", title="fix typo in README", goal="fix a typo", scope=["README.md"])
    a = complexity.assess(simple)
    assert a.level == "simple" and a.effort == "low" and any("simplicity" in r for r in a.reasons)
    assert complexity.assess(simple) == a  # deterministic

    std = _task(goal="Add subtract(a, b) returning a - b, keep add() unchanged.")
    assert complexity.assess(std).level == "standard"

    hard = _task(
        role="refactor",
        title="Refactor the scheduler for concurrency",
        goal=" ".join(["migrate the solver pipeline to a new architecture"] * 8),
        scope=["src/**", "tests/**"],
        acceptance=["a", "b", "c", "d"],
        depends_on=[],
    )
    h = complexity.assess(hard)
    assert h.level == "complex" and h.effort == "high" and h.score > 7

    retry = _task(attempt=3)
    assert any("attempt 3" in r for r in complexity.assess(retry).reasons)


def test_tier_preference_in_pick_model(template_cfg: CouncilConfig, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from council_mcp.scheduler import Scheduler
    from council_mcp.store import TaskStore
    from council_mcp.watcher import Watcher
    from council_mcp.worktree import GitRepo

    for m in template_cfg.models.values():
        m.enabled = True
    template_cfg.routing.by_role["docs"] = ["copilot", "cheap", "codex"]
    store = TaskStore(tmp_path)
    git = GitRepo(tmp_path)
    s = Scheduler(template_cfg, store, git, Watcher(store, git), tmp_path)
    t = _task(role="docs", privacy="public")
    t.complexity = "simple"
    assert s.pick_model(t) == "cheap"  # first low-tier candidate wins
    t.complexity = "complex"
    assert s.pick_model(t) == "codex"  # first high-tier candidate wins
    t.complexity = "standard"
    assert s.pick_model(t) == "copilot"  # routing order untouched
    t.assigned_to = "copilot"
    t.complexity = "complex"
    assert s.pick_model(t) == "copilot"  # explicit assignment still wins


def test_effort_override_reaches_argv() -> None:
    codex = CliAdapter(
        "codex", ModelConfig(adapter="codex", cmd="codex", model="gpt-6-astra", reasoning="medium")
    )
    assert "-c" in codex._model_args(
        "high"
    ) and 'model_reasoning_effort="high"' in codex._model_args("high")
    assert 'model_reasoning_effort="medium"' in codex._model_args(None)
    fable = CliAdapter(
        "fable",
        ModelConfig(adapter="claude-sub", cmd="claude", model="claude-fable-5-1", effort="medium"),
    )
    assert fable._model_args("low") == ["--model", "claude-fable-5-1", "--effort", "low"]
    assert fable._model_args(None) == ["--model", "claude-fable-5-1", "--effort", "medium"]
