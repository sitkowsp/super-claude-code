from __future__ import annotations

import pytest
from pydantic import ValidationError

from council_mcp.config import CouncilConfig


def test_template_loads_and_expands_env(template_cfg: CouncilConfig) -> None:
    assert template_cfg.models["local"].url == "http://ollama.test:11434"
    assert template_cfg.models["local"].adapter == "ollama"
    assert template_cfg.models["cheap"].adapter == "claude-sub"


def test_routing_is_privacy_intersect_role(template_cfg: CouncilConfig) -> None:
    assert template_cfg.candidates("implement", "public") == [
        "codex",
        "antigravity",
        "copilot",
        "local",
    ]
    assert template_cfg.candidates("implement", "local-only") == ["local"]
    assert template_cfg.candidates("refactor", "internal") == []  # no intersection = error later


def test_disabled_model_leaves_routing(template_cfg: CouncilConfig) -> None:
    template_cfg.models["codex"].enabled = False
    assert template_cfg.candidates("implement", "public") == ["antigravity", "copilot", "local", "grok"]


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        CouncilConfig.model_validate({"models": {}, "api_key": "nope"})


def test_bad_model_name_rejected() -> None:
    with pytest.raises(ValidationError):
        CouncilConfig.model_validate({"models": {"Local": {"adapter": "ollama"}}})
