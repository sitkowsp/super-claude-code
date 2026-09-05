"""Logging setup. stdout belongs to MCP (stdio transport) — everything goes to stderr."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure(level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stderr, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.KeyValueRenderer(key_order=["event"]),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def get(name: str) -> Any:
    return structlog.get_logger(name)
