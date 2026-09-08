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


def load(repo_root: Path) -> CapabilitiesFile | None:
    path = repo_root / CAPABILITIES_PATH
    if not path.exists():
        return None
    try:
        return CapabilitiesFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a corrupt cache is simply re-probed, never fatal
        return None


def age_hours(caps: CapabilitiesFile) -> float:
    try:
        t = datetime.fromisoformat(caps.probed_at)
    except ValueError:
        return float("inf")
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - t).total_seconds() / 3600)


def is_fresh(caps: CapabilitiesFile, ttl_hours: int) -> bool:
    """ttl_hours <= 0 disables the daily refresh: anything probed stays fresh forever."""
    return ttl_hours <= 0 or age_hours(caps) < ttl_hours


async def ensure_fresh(
    cfg: CouncilConfig, repo_root: Path, current: CapabilitiesFile | None
) -> tuple[CapabilitiesFile, bool]:
    """The daily availability check: keep `current` while younger than `probe_ttl_hours`; with no
    in-memory copy, a fresh-enough capabilities.json from disk is trusted (another process may have
    probed already — its `enabled` verdicts are applied to cfg). Otherwise re-probe every provider
    and rewrite the file; each model's `enabled` is first restored from council.json so a provider
    that recovered since the last probe can come back. Returns (caps, reprobed)."""
    ttl = cfg.probe_ttl_hours
    if current is not None and is_fresh(current, ttl):
        return current, False
    if current is None:
        cached = load(repo_root)
        if cached is not None and is_fresh(cached, ttl):
            for n, c in cached.models.items():
                if n in cfg.models:
                    cfg.models[n].enabled = cfg.models[n].enabled and c.enabled
            return cached, False
    try:
        from council_mcp.config import load as _load_cfg

        persisted = _load_cfg(repo_root)
        for n, m in cfg.models.items():
            if n in persisted.models:
                m.enabled = persisted.models[n].enabled
    except Exception:  # noqa: BLE001 - keep the current flags if council.json is unreadable
        pass
    caps = await probe_all(cfg)
    write(caps, repo_root)
    return caps, True
