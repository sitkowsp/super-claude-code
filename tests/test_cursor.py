"""Cursor CLI as an optional executor (adapter `cursor`, binary `cursor-agent`)."""

from __future__ import annotations

import sys

import pytest

from council_mcp import setup
from council_mcp.adapters.cli import (
    _APPROVAL,
    _ASK_ARGV,
    _READS_CHARTER_FILE,
    _RUN_ARGV,
    CliAdapter,
    parse_model_list,
)
from council_mcp.config import CouncilConfig, ModelConfig


def _mc(**kw: object) -> ModelConfig:
    return ModelConfig(adapter="cursor", cmd="cursor-agent", **kw)  # type: ignore[arg-type]


def test_cursor_argv_tables() -> None:
    assert _ASK_ARGV["cursor"] == ["-p", "{prompt}", "--output-format", "text"]
    assert _RUN_ARGV["cursor"] == ["-p", "{prompt}", "--output-format", "text"]
    assert _APPROVAL["cursor"][0] == ["--force"]
    assert "cursor" in _READS_CHARTER_FILE  # reads AGENTS.md/CLAUDE.md natively


def test_cursor_model_and_approval_args() -> None:
    a = CliAdapter("cursor", _mc(model="composer-2.5"))
    # --model is passed explicitly (like antigravity), independent of probed flags
    assert a._model_args() == ["--model", "composer-2.5"]
    assert a._approval_args() == ["--force"]  # unprobed flags → first candidate
    a.flags = ["--force", "--print", "--yolo"]
    assert a._approval_args() == ["--force"]


async def test_cursor_probe_silent_discovery_no_efforts() -> None:
    # `python` stands in for cursor-agent: `python models` exits non-zero → discovery stays
    # silent, config stays authoritative; cursor has no effort knob (power comes via --model).
    a = CliAdapter("cursor", ModelConfig(adapter="cursor", cmd=sys.executable))
    caps = await a.probe()
    assert caps.enabled and caps.models == [] and caps.efforts == []


def test_cursor_models_list_parses() -> None:
    text = (
        "Available models:\n"
        "  composer-2.5\n"
        "  gpt-5.6\n"
        "  opus-5\n"
        "  gemini-3.1-pro\n"
        "  grok-4.6\n"
        "auto\n"
    )
    assert parse_model_list(text) == [
        "composer-2.5",
        "gpt-5.6",
        "opus-5",
        "gemini-3.1-pro",
        "grok-4.6",
    ]


def test_template_ships_cursor_disabled(template_cfg: CouncilConfig) -> None:
    m = template_cfg.models["cursor"]
    assert m.adapter == "cursor" and m.enabled is False and m.cmd == "cursor-agent"
    assert "cursor" not in template_cfg.candidates("implement", "public")  # off by default
    m.enabled = True
    cands = template_cfg.candidates("implement", "public")
    assert "cursor" in cands and cands.index("cursor") > cands.index("codex")


async def test_doctor_detects_missing_cursor(
    template_cfg: CouncilConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup, "_which", lambda cmd: None)
    checks = {c.model: c for c in await setup.check_all(template_cfg)}
    c = checks["cursor"]
    assert not c.installed and not c.enabled
    assert "install: curl https://cursor.com/install" in c.action


async def test_doctor_cursor_installed_api_key(
    template_cfg: CouncilConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        setup, "_which", lambda cmd: "C:/bin/cursor-agent.exe" if "cursor" in cmd else None
    )
    monkeypatch.setenv("CURSOR_API_KEY", "x")
    checks = {c.model: c for c in await setup.check_all(template_cfg)}
    c = checks["cursor"]
    assert c.installed and c.logged_in is True and c.action == ""
