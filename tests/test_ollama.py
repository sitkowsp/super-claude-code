from __future__ import annotations

import json

import httpx
import pytest
import respx

from council_mcp.adapters.ollama import OllamaAdapter
from council_mcp.config import CouncilConfig

BASE = "http://ollama.test:11434"


@pytest.fixture
def adapter(template_cfg: CouncilConfig) -> OllamaAdapter:
    return OllamaAdapter("local", template_cfg.models["local"], timeout_s=5)


@respx.mock
async def test_probe_enabled_when_model_pulled(adapter: OllamaAdapter) -> None:
    respx.get(f"{BASE}/api/tags").respond(json={"models": [{"name": "qwen3-coder:30b"}]})
    respx.get(f"{BASE}/api/version").respond(json={"version": "0.9.0"})
    caps = await adapter.probe()
    assert caps.enabled and caps.version == "0.9.0" and caps.models == ["qwen3-coder:30b"]


@respx.mock
async def test_probe_disabled_when_model_missing(adapter: OllamaAdapter) -> None:
    respx.get(f"{BASE}/api/tags").respond(json={"models": [{"name": "llama3:8b"}]})
    respx.get(f"{BASE}/api/version").respond(json={})
    caps = await adapter.probe()
    assert not caps.enabled and "not pulled" in (caps.error or "")


@respx.mock
async def test_probe_disabled_when_down(adapter: OllamaAdapter) -> None:
    respx.get(f"{BASE}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    caps = await adapter.probe()
    assert not caps.enabled and caps.error


@respx.mock
async def test_ask_returns_text_and_usage(adapter: OllamaAdapter) -> None:
    route = respx.post(f"{BASE}/api/chat").respond(
        json={"message": {"content": "hi"}, "prompt_eval_count": 10, "eval_count": 2}
    )
    res = await adapter.ask("hello")
    assert res.text == "hi" and res.tokens_in == 10 and res.tokens_out == 2
    body = json.loads(route.calls.last.request.content)
    assert body["stream"] is False and body["options"]["num_ctx"] == 32768


@respx.mock
async def test_ask_retries_once_with_half_ctx_on_5xx(adapter: OllamaAdapter) -> None:
    route = respx.post(f"{BASE}/api/chat")
    route.side_effect = [
        httpx.Response(500, text="oom"),
        httpx.Response(200, json={"message": {"content": "ok"}}),
    ]
    res = await adapter.ask("hello")
    assert res.text == "ok" and route.call_count == 2
    assert json.loads(route.calls.last.request.content)["options"]["num_ctx"] == 16384


@respx.mock
async def test_ask_does_not_retry_4xx(adapter: OllamaAdapter) -> None:
    respx.post(f"{BASE}/api/chat").respond(404, text="no model")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.ask("hello")
