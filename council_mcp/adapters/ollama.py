"""Ollama adapter (DESIGN.md §5.2). Phase 0: probe + ask over /api/chat.

Retry rule: on 5xx/timeout retry once with num_ctx halved.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from council_mcp.adapters.base import AskResult, Capabilities, inline_files
from council_mcp.config import ModelConfig
from council_mcp.log import get

log = get(__name__)


class OllamaAdapter:
    def __init__(self, name: str, cfg: ModelConfig, timeout_s: float = 600.0) -> None:
        if not cfg.url or not cfg.model:
            raise ValueError(f"model '{name}': ollama adapter needs `url` and `model`")
        self.name = name
        self.cfg = cfg
        self.url = cfg.url.rstrip("/")
        self.model = cfg.model
        self.timeout_s = timeout_s

    async def probe(self) -> Capabilities:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.url}/api/tags")
                r.raise_for_status()
                models = [str(m["name"]) for m in r.json().get("models", [])]
                ver: str | None = None
                try:
                    ver = (await c.get(f"{self.url}/api/version")).json().get("version")
                except Exception:  # noqa: BLE001 - version endpoint is optional
                    pass
        except Exception as e:  # noqa: BLE001
            return Capabilities(name=self.name, adapter="ollama", enabled=False, error=str(e))
        has_model = any(m == self.model or m.split(":")[0] == self.model for m in models)
        return Capabilities(
            name=self.name,
            adapter="ollama",
            enabled=has_model,
            version=ver,
            path=self.url,
            models=models,
            error=None if has_model else f"model '{self.model}' not pulled",
        )

    async def ask(
        self, prompt: str, files: list[Path] | None = None, system: str | None = None
    ) -> AskResult:
        content = inline_files(prompt, files)
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content}
        ]
        num_ctx = self.cfg.num_ctx
        for attempt in (1, 2):
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "keep_alive": "10m",
                "options": {"num_ctx": num_ctx, "num_predict": self.cfg.num_predict},
            }
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                    r = await c.post(f"{self.url}/api/chat", json=payload)
                    r.raise_for_status()
                data = r.json()
                return AskResult(
                    model=self.name,
                    text=data["message"]["content"],
                    duration_s=round(time.monotonic() - t0, 2),
                    tokens_in=data.get("prompt_eval_count"),
                    tokens_out=data.get("eval_count"),
                )
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                retryable = isinstance(e, httpx.TimeoutException) or (
                    isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                )
                if attempt == 2 or not retryable:
                    raise
                num_ctx //= 2
                log.warning("ollama_retry", model=self.name, num_ctx=num_ctx, error=str(e))
        raise RuntimeError("unreachable")
