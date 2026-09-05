"""Executor adapters. One file per model provider (DESIGN.md §5)."""

from __future__ import annotations

from council_mcp.adapters.base import Adapter, AskResult, Capabilities
from council_mcp.adapters.cli import CliAdapter
from council_mcp.adapters.ollama import OllamaAdapter
from council_mcp.config import ModelConfig


def make(name: str, cfg: ModelConfig) -> Adapter:
    if cfg.adapter == "ollama":
        return OllamaAdapter(name, cfg)
    return CliAdapter(name, cfg)


__all__ = ["Adapter", "AskResult", "Capabilities", "CliAdapter", "OllamaAdapter", "make"]
