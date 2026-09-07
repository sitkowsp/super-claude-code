from __future__ import annotations

import json
from pathlib import Path

import pytest

from council_mcp import cli, render, setup
from council_mcp.adapters.cli import CliAdapter, executor_env
from council_mcp.config import CouncilConfig, ModelConfig
from council_mcp.store import Task


def test_template_has_chair_defaults_and_disabled_fable(template_cfg: CouncilConfig) -> None:
    assert template_cfg.chair.coder == "executors"
    assert template_cfg.chair.plan_assist is None and template_cfg.chair.review_assist is None
    f = template_cfg.models["fable"]
    assert f.adapter == "claude-sub" and not f.enabled and f.effort == "medium"
    # default routing unchanged: codex first for implement, fable absent (disabled)
    for m in template_cfg.models.values():
        m.enabled = True
    template_cfg.models["fable"].enabled = False
    assert template_cfg.candidates("implement", "public")[0] == "codex"
    assert "fable" not in template_cfg.candidates("implement", "public")


def test_coder_fable_goes_first_only_for_code_roles(template_cfg: CouncilConfig) -> None:
    for m in template_cfg.models.values():
        m.enabled = True
    template_cfg.chair.coder = "fable"
    assert template_cfg.candidates("implement", "public")[0] == "fable"
    assert template_cfg.candidates("refactor", "internal")[0] == "fable"
    assert template_cfg.candidates("assets", "public")[0] == "codex"
    assert template_cfg.candidates("docs", "public")[0] == "copilot"


def test_chair_refs_validated(template_cfg: CouncilConfig) -> None:
    data = template_cfg.model_dump()
    data["chair"]["coder"] = "nope"
    with pytest.raises(ValueError):
        CouncilConfig.model_validate(data)
    data["chair"]["coder"] = "executors"
    data["chair"]["plan_assist"] = "ghost"
    with pytest.raises(ValueError):
        CouncilConfig.model_validate(data)


def test_claude_sub_effort_flag_and_executor_env() -> None:
    a = CliAdapter(
        "fable",
        ModelConfig(adapter="claude-sub", cmd="claude", model="claude-fable-5-1", effort="medium"),
    )
    assert a._model_args() == ["--model", "claude-fable-5-1", "--effort", "medium"]
    assert executor_env()["COUNCIL_EXECUTOR"] == "1"


def test_hooks_silent_inside_executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COUNCIL_EXECUTOR", "1")
    assert cli.session_start(tmp_path, Path.cwd()) == ""
    assert cli.events(tmp_path) == ""
    assert not (tmp_path / ".council").exists()


def test_set_chair_edits_config_and_enables_coder(tmp_path: Path) -> None:
    cli.init(tmp_path, Path.cwd())
    changed = setup.set_chair(tmp_path, coder="fable", plan_assist="codex")
    assert set(changed) == {"coder", "plan_assist"}
    data = json.loads((tmp_path / ".council" / "council.json").read_text(encoding="utf-8"))
    assert data["chair"] == {"plan_assist": "codex", "review_assist": None, "coder": "fable"}
    assert data["models"]["fable"]["enabled"] is True
    assert setup.set_chair(tmp_path, plan_assist="off") == ["plan_assist"]
    assert setup.set_chair(tmp_path, coder="executors") == ["coder"]
    data = json.loads((tmp_path / ".council" / "council.json").read_text(encoding="utf-8"))
    assert data["models"]["fable"]["enabled"] is False  # Claude coder switched off again
    setup.set_chair(tmp_path, coder="fable")
    with pytest.raises(ValueError):
        setup.set_chair(tmp_path, coder="ghost")
    line = setup.chair_line(
        CouncilConfig.model_validate(
            json.loads((tmp_path / ".council" / "council.json").read_text(encoding="utf-8"))
        )
    )
    assert "coder: fable (claude-fable-5-1, effort medium)" in line and "plan_assist: off" in line


def test_extract_json_array_ignores_prose() -> None:
    from council_mcp.server import _extract_json_array

    cards = '[{"title": "a", "scope": ["x/"]}, {"title": "b"}]'
    text = f"Sure! Here are [not json] the cards:\n{cards}\nbye"
    assert [c["title"] for c in _extract_json_array(text)] == ["a", "b"]


def test_prompts_render() -> None:
    t = Task(
        id="T-001",
        title="x",
        role="implement",
        privacy="public",
        goal="g",
        scope=["a/"],
        assigned_to="codex",
    )
    p = render.review_assist(t, "diff --git a b", gates_ok=True)
    assert "T-001" in p and "OK" in p and "diff --git" in p
    d = render.plan_draft(
        goal="build it",
        analysis="langs: py",
        playbook={"name": "feature", "description": "d", "waves": [], "claude_keeps": ["merge"]},
        models={"codex": {"roles": ["implement"], "privacy": ["public"]}},
        never_share=[".env"],
        memory="",
        notes=[],
        existing=[],
    )
    assert "build it" in d and ".env" in d and "JSON" in d
