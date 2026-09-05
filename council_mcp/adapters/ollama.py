"""Ollama adapter (DESIGN.md §5.2) — the only adapter with its own agent loop.

Tools exposed to the model (all confined to the workdir): read_file, write_file, list_files,
run (whitelisted commands, 120 s), write_report. The loop ends when write_report is called with
status done|blocked|failed or max_turns is reached. Retry rule: on 5xx/timeout retry once with
num_ctx halved.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import time
from pathlib import Path
from typing import Any

import httpx

from council_mcp import render
from council_mcp.adapters.base import AskResult, Capabilities, RunHandle, inline_files
from council_mcp.config import Budget, ModelConfig
from council_mcp.log import get
from council_mcp.store import Task

log = get(__name__)

RUN_WHITELIST = re.compile(r"^(pytest|ruff|python -m|uv run|npm test|npx vitest|dotnet test)\b")
MAX_READ = 60_000
FINAL = {"done", "blocked", "failed"}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file (relative path).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a text file (relative path).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files matching a glob (default '**/*').",
            "parameters": {"type": "object", "properties": {"glob": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Run a test/lint command (pytest, ruff, python "
            "-m, uv run, npm test, dotnet test). 120 s limit.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_report",
            "description": "Overwrite REPORT.md. status: "
            "plan|progress|blocked|done|failed. done/blocked/failed END the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["plan", "progress", "blocked", "done", "failed"],
                    },
                    "percent": {"type": "integer"},
                    "touched": {"type": "array", "items": {"type": "string"}},
                    "needs": {"type": "array", "items": {"type": "string"}},
                    "verify": {"type": "array", "items": {"type": "string"}},
                    "body": {"type": "string"},
                },
                "required": ["status", "body"],
            },
        },
    },
]


class OllamaAdapter:
    def __init__(self, name: str, cfg: ModelConfig, timeout_s: float = 600.0) -> None:
        if not cfg.url or not cfg.model:
            raise ValueError(f"model '{name}': ollama adapter needs `url` and `model`")
        self.name = name
        self.cfg = cfg
        self.url = cfg.url.rstrip("/")
        self.model = cfg.model
        self.timeout_s = timeout_s
        self.repo_root = Path.cwd()
        self.memory_file = ".council/MEMORY.md"

    # ---- probe / ask ---------------------------------------------------------
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

    async def _chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        num_ctx = self.cfg.num_ctx
        for attempt in (1, 2):
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "keep_alive": "10m",
                "options": {"num_ctx": num_ctx, "num_predict": self.cfg.num_predict},
            }
            if tools:
                payload["tools"] = tools
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                    r = await c.post(f"{self.url}/api/chat", json=payload)
                    r.raise_for_status()
                return r.json()  # type: ignore[no-any-return]
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                retryable = isinstance(e, httpx.TimeoutException) or (
                    isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                )
                if attempt == 2 or not retryable:
                    raise
                num_ctx //= 2
                log.warning("ollama_retry", model=self.name, num_ctx=num_ctx, error=str(e))
        raise RuntimeError("unreachable")

    async def ask(
        self, prompt: str, files: list[Path] | None = None, system: str | None = None
    ) -> AskResult:
        content = inline_files(prompt, files)
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": content}
        ]
        t0 = time.monotonic()
        data = await self._chat(messages)
        return AskResult(
            model=self.name,
            text=data["message"]["content"],
            duration_s=round(time.monotonic() - t0, 2),
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
        )

    # ---- agent loop ----------------------------------------------------------
    def _safe(self, workdir: Path, rel: str) -> Path:
        p = (workdir / rel).resolve()
        if not p.is_relative_to(workdir.resolve()):
            raise ValueError(f"path escapes workdir: {rel}")
        return p

    async def _tool(self, workdir: Path, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "read_file":
                return self._safe(workdir, args["path"]).read_text(
                    encoding="utf-8", errors="replace"
                )[:MAX_READ]
            if name == "write_file":
                p = self._safe(workdir, args["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args["content"], encoding="utf-8")
                return f"wrote {args['path']}"
            if name == "list_files":
                pat = args.get("glob") or "**/*"
                files = [
                    q.relative_to(workdir).as_posix()
                    for q in workdir.glob(pat)
                    if q.is_file() and ".git" not in q.parts
                ]
                return "\n".join(sorted(files)[:500]) or "(none)"
            if name == "run":
                cmd = args["cmd"].strip()
                if cmd.startswith("git ") or not RUN_WHITELIST.match(cmd):
                    return "refused: command not in whitelist"
                proc = await asyncio.create_subprocess_exec(
                    *shlex.split(cmd),
                    cwd=str(workdir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
                except TimeoutError:
                    proc.kill()
                    return "timeout after 120 s"
                return f"exit {proc.returncode}\n" + out.decode(errors="replace")[-8000:]
            if name == "write_report":
                fm = {
                    k: args.get(k, [] if k in ("touched", "needs", "verify") else 0)
                    for k in ("task", "status", "percent", "touched", "needs", "verify")
                }
                text = (
                    "---\n"
                    + "\n".join(f"{k}: {json.dumps(v)}" for k, v in fm.items())
                    + "\n---\n"
                    + str(args.get("body", ""))
                )
                (workdir / "REPORT.md").write_text(text, encoding="utf-8")
                return f"report written ({args['status']})"
            return f"unknown tool {name}"
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"

    async def run(self, task: Task, workdir: Path, budget: Budget, resume: bool) -> RunHandle:
        handle = RunHandle(task_id=task.id, model=self.name)
        system = render.system_prompt(self.repo_root, self.memory_file)
        user = (
            render.cli_prompt(task, resume, None)
            + "\n\nTASK.md:\n"
            + (workdir / "TASK.md").read_text(encoding="utf-8")
        )
        if resume:
            for name in ("PREVIOUS_REPORT.md", "ANSWER.md"):
                p = workdir / name
                if p.exists():
                    user += f"\n\n{name}:\n" + p.read_text(encoding="utf-8")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        async def _loop() -> None:
            deadline = time.monotonic() + budget.hard_minutes * 60
            try:
                for _turn in range(budget.max_turns):
                    if handle.cancelled or time.monotonic() > deadline:
                        handle.finish(-1, "cancelled" if handle.cancelled else "budget exceeded")
                        return
                    data = await self._chat(messages, TOOLS)
                    msg = data["message"]
                    messages.append(msg)
                    calls = msg.get("tool_calls") or []
                    if not calls:
                        messages.append(
                            {
                                "role": "user",
                                "content": "Użyj narzędzi. Gdy skończysz, wywołaj write_report "
                                "ze statusem done/blocked/failed.",
                            }
                        )
                        continue
                    for call in calls:
                        fn = call["function"]
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        if fn["name"] == "write_report":
                            args["task"] = task.id
                        result = await self._tool(workdir, fn["name"], args)
                        messages.append(
                            {"role": "tool", "content": result, "tool_name": fn["name"]}
                        )
                        if (
                            fn["name"] == "write_report"
                            and args.get("status") in FINAL
                            and not result.startswith("error")
                        ):
                            handle.finish(0)
                            return
                handle.finish(0, "max_turns reached")
            except Exception as e:  # noqa: BLE001
                log.error("ollama_run_error", task=task.id, error=str(e))
                handle.finish(-1, str(e))

        asyncio.ensure_future(_loop())
        return handle
