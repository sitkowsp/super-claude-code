from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx

from council_mcp import probe
from council_mcp.adapters.base import inline_files
from council_mcp.adapters.cli import CliAdapter
from council_mcp.config import CouncilConfig, ModelConfig


async def test_cli_probe_missing_binary() -> None:
    a = CliAdapter("x", ModelConfig(adapter="gemini", cmd="definitely-not-a-real-cli-xyz"))
    caps = await a.probe()
    assert not caps.enabled and "not on PATH" in (caps.error or "")


async def test_cli_probe_detects_flags_from_help() -> None:
    # `python` is always present; its --help lists long flags. Adapter only needs `cmd` to exist.
    import sys

    a = CliAdapter("py", ModelConfig(adapter="gemini", cmd=sys.executable))
    caps = await a.probe()
    assert caps.enabled and caps.version and caps.version.startswith("Python")
    assert "--version" in caps.flags or "--help" in caps.flags


def test_inline_files_refuses_escape(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    out = inline_files("q", [Path("a.txt")], root=tmp_path)
    assert "### a.txt" in out and "\nA\n" in out
    with pytest.raises(ValueError):
        inline_files("q", [Path("../secret")], root=tmp_path)


@respx.mock
async def test_probe_all_disables_unavailable_and_writes_file(
    template_cfg: CouncilConfig, tmp_path: Path
) -> None:
    respx.get("http://ollama.test:11434/api/tags").respond(
        json={"models": [{"name": "qwen3-coder:30b"}]}
    )
    respx.get("http://ollama.test:11434/api/version").respond(json={"version": "x"})
    for m in ("gemini", "codex", "copilot", "grok", "cheap"):
        template_cfg.models[m].cmd = "definitely-not-a-real-cli-xyz"
    caps = await probe.probe_all(template_cfg)
    assert caps.models["local"].enabled
    assert not caps.models["gemini"].enabled
    assert template_cfg.models["gemini"].enabled is False
    assert template_cfg.candidates("implement", "public") == ["local"]
    path = probe.write(caps, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["models"]) == set(template_cfg.models)
