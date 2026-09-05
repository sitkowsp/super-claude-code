from __future__ import annotations

import json
from pathlib import Path

import pytest

from council_mcp.config import CouncilConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def template_cfg(monkeypatch: pytest.MonkeyPatch) -> CouncilConfig:
    monkeypatch.setenv("COUNCIL_OLLAMA_URL", "http://ollama.test:11434")
    data = json.loads((ROOT / "templates" / "council.json").read_text(encoding="utf-8"))
    return CouncilConfig.model_validate(data)
