"""Probe (DESIGN.md §5.7): at server start check every configured model and write
`.council/capabilities.json`. Unavailable models get `enabled: false` and drop out of routing."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from council_mcp.adapters import make
from council_mcp.adapters.base import Capabilities
from council_mcp.config import CouncilConfig

CAPABILITIES_PATH = Path(".council") / "capabilities.json"


class CapabilitiesFile(BaseModel):
    probed_at: str
    models: dict[str, Capabilities] = Field(default_factory=dict)


async def probe_all(cfg: CouncilConfig) -> CapabilitiesFile:
    names = list(cfg.models)

    async def _one(n: str) -> Capabilities:
        return await make(n, cfg.models[n]).probe()  # ValueError on bad config → handled below

    results = await asyncio.gather(*(_one(n) for n in names), return_exceptions=True)
    out: dict[str, Capabilities] = {}
    for name, res in zip(names, results, strict=True):
        if isinstance(res, BaseException):
            res = Capabilities(
                name=name, adapter=cfg.models[name].adapter, enabled=False, error=str(res)
            )
        out[name] = res
        cfg.models[name].enabled = cfg.models[name].enabled and res.enabled
    return CapabilitiesFile(probed_at=datetime.now(UTC).isoformat(timespec="seconds"), models=out)


def write(caps: CapabilitiesFile, repo_root: Path) -> Path:
    path = repo_root / CAPABILITIES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(caps.model_dump(), indent=2), encoding="utf-8")
    return path
