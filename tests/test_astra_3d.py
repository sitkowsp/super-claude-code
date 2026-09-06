from __future__ import annotations

from pathlib import Path

import pytest

from council_mcp import playbooks, policy, render, setup
from council_mcp.adapters.cli import CliAdapter
from council_mcp.config import CouncilConfig, ModelConfig
from council_mcp.store import Task


def _task(role: str = "3d") -> Task:
    return Task(
        id="T-001",
        title="textures",
        role=role,  # type: ignore[arg-type]
        privacy="public",
        goal="g",
        scope=["assets/tex/"],
        assigned_to="codex",
    )


def test_template_defaults_to_astra_medium_256k(template_cfg: CouncilConfig) -> None:
    c = template_cfg.models["codex"]
    assert c.model == "gpt-6-astra" and c.reasoning == "medium" and c.context_window == 256000
    assert "3d" in c.roles and template_cfg.routing.by_role["3d"][0] == "codex"
    assert "3d" in policy.ALWAYS_DELEGATE


def test_codex_model_args_carry_reasoning_and_context() -> None:
    cfg = ModelConfig(
        adapter="codex", cmd="codex", model="gpt-6-astra", reasoning="medium", context_window=256000
    )
    a = CliAdapter("codex", cfg)
    assert a._model_args() == [
        "-m",
        "gpt-6-astra",
        "-c",
        'model_reasoning_effort="medium"',
        "-c",
        "model_context_window=256000",
    ]
    assert CliAdapter("codex", ModelConfig(adapter="codex", cmd="codex"))._model_args() == []


def test_reasoning_is_validated() -> None:
    with pytest.raises(ValueError):
        ModelConfig(adapter="codex", cmd="codex", reasoning="turbo")  # type: ignore[arg-type]


def test_detect_tools_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ue = tmp_path / "UE" / "Engine" / "Binaries" / "Win64"
    ue.mkdir(parents=True)
    (ue / "UnrealEditor-Cmd.exe").write_text("")
    bl = tmp_path / "blender.exe"
    bl.write_text("")
    monkeypatch.setenv("UE_ROOT", str(tmp_path / "UE"))
    monkeypatch.setenv("BLENDER_EXE", str(bl))
    t = setup.detect_tools()
    assert t["unreal"] == str(ue / "UnrealEditor-Cmd.exe") and t["blender"] == str(bl)
    monkeypatch.setenv("BLENDER_EXE", str(tmp_path / "missing.exe"))
    monkeypatch.setenv("UE_ROOT", str(tmp_path / "nope"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(setup.shutil, "which", lambda _n: None)
    assert setup.detect_tools() == {"blender": None, "unreal": None}


def test_cli_prompt_3d_mentions_tools_or_fallback() -> None:
    p = render.cli_prompt(
        _task(), False, None, tools={"blender": "C:/b/blender.exe", "unreal": None}
    )
    assert "C:/b/blender.exe" in p and "-b --python" in p and "NIE jest zainstalowany" in p
    p2 = render.cli_prompt(_task("implement"), False, None, tools={"blender": None, "unreal": None})
    assert "Blender" not in p2


def test_game_assets_playbook_selected(tmp_path: Path) -> None:
    pb, reason = playbooks.select(
        "generate seamless textures for the Unreal level", playbooks.load_all(tmp_path)
    )
    assert pb.name == "game-assets" and "unreal" in reason
