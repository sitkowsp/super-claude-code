"""council-mcp server (mcp 2.x MCPServer, stdio).

Phase 0 tools: council_models, council_ask, council_probe.

Run from the target repo root: `uv run council-mcp` (wired via `.mcp.json`).
Set COUNCIL_REPO_ROOT to point elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from council_mcp import __version__, probe
from council_mcp.adapters import make
from council_mcp.config import CouncilConfig, load
from council_mcp.log import configure, get

log = get(__name__)
mcp = MCPServer(
    "council",
    version=__version__,
    instructions=(
        "Council: ask other providers' models one-shot questions (second opinion, review, "
        "analysis). Model names come from council_models. Never send files matching never_share."
    ),
)

_state: dict[str, Any] = {"cfg": None, "caps": None, "root": None}


def _root() -> Path:
    if _state["root"] is None:
        _state["root"] = Path(os.environ.get("COUNCIL_REPO_ROOT", os.getcwd())).resolve()
    return _state["root"]  # type: ignore[no-any-return]


def _cfg() -> CouncilConfig:
    if _state["cfg"] is None:
        _state["cfg"] = load(_root())
    return _state["cfg"]  # type: ignore[no-any-return]


async def _ensure_probed() -> probe.CapabilitiesFile:
    if _state["caps"] is None:
        caps = await probe.probe_all(_cfg())
        probe.write(caps, _root())
        _state["caps"] = caps
        log.info("probed", models={k: v.enabled for k, v in caps.models.items()})
    return _state["caps"]  # type: ignore[no-any-return]


@mcp.tool()
async def council_models() -> dict[str, Any]:
    """List configured models with adapter, availability, roles and privacy levels."""
    cfg = _cfg()
    caps = await _ensure_probed()
    return {
        "version": __version__,
        "repo_root": str(_root()),
        "probed_at": caps.probed_at,
        "models": {
            name: {
                "adapter": m.adapter,
                "enabled": m.enabled,
                "roles": m.roles,
                "privacy": m.privacy,
                "backend": m.model or m.cmd,
                "error": caps.models[name].error if name in caps.models else None,
            }
            for name, m in cfg.models.items()
        },
    }


@mcp.tool()
async def council_ask(model: str, prompt: str, files: list[str] | None = None) -> dict[str, Any]:
    """Ask one configured model a one-shot question (no worktree, no tools).

    `files` are repo-relative paths inlined into the prompt (max 40k chars each).
    Paths matching `never_share` are refused.
    """
    cfg = _cfg()
    await _ensure_probed()
    if model not in cfg.models:
        raise ToolError(f"unknown model '{model}'; known: {sorted(cfg.models)}")
    if not cfg.models[model].enabled:
        raise ToolError(f"model '{model}' is disabled (see council_models for the reason)")
    paths = [Path(f) for f in files or []]
    for p in paths:
        if any(p.match(g) or p.as_posix().startswith(g.rstrip("/*")) for g in cfg.never_share):
            raise ToolError(f"'{p}' matches never_share - refusing to send it")
    prev = Path.cwd()
    os.chdir(_root())
    try:
        res = await make(model, cfg.models[model]).ask(prompt, paths)
    finally:
        os.chdir(prev)
    return res.model_dump()


@mcp.tool()
async def council_probe() -> dict[str, Any]:
    """Re-run the availability probe and rewrite .council/capabilities.json."""
    _state["cfg"] = None
    _state["caps"] = None
    caps = await _ensure_probed()
    return caps.model_dump()


def main() -> None:
    configure(os.environ.get("COUNCIL_LOG_LEVEL", "INFO"))
    log.info("council-mcp starting", version=__version__, root=str(_root()))
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
