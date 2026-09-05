"""Generic CLI adapter for gemini / codex / grok / claude -p (DESIGN.md §5.3–5.6).

Phase 0: probe (which + --version + --help flag scan) and one-shot `ask`.
Flags are never hardcoded beyond the minimal prompt argv; anything else comes
from `capabilities.json` in Phase 1.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path

from council_mcp.adapters.base import AskResult, Capabilities, inline_files
from council_mcp.config import ModelConfig

_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")

# How each CLI takes a one-shot prompt (argv template; {prompt} substituted).
_ASK_ARGV: dict[str, list[str]] = {
    "gemini": ["-p", "{prompt}"],
    "codex": ["exec", "{prompt}"],
    "grok": ["-p", "{prompt}"],
    "claude-sub": ["-p", "{prompt}", "--output-format", "text"],
}


async def _run(argv: list[str], timeout_s: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


class CliAdapter:
    def __init__(self, name: str, cfg: ModelConfig, timeout_s: float = 600.0) -> None:
        if not cfg.cmd:
            raise ValueError(f"model '{name}': {cfg.adapter} adapter needs `cmd`")
        self.name = name
        self.cfg = cfg
        self.cmd = cfg.cmd
        self.timeout_s = timeout_s

    async def probe(self) -> Capabilities:
        path = shutil.which(self.cmd)
        if not path:
            return Capabilities(
                name=self.name,
                adapter=self.cfg.adapter,
                enabled=False,
                error=f"{self.cmd} not on PATH",
            )
        try:
            _, out, err = await _run([path, "--version"], 20)
            text = (out or err).strip()
            version = text.splitlines()[0] if text else None
            _, out, err = await _run([path, "--help"], 20)
            flags = sorted(set(_FLAG_RE.findall(out + err)))
        except Exception as e:  # noqa: BLE001
            return Capabilities(
                name=self.name, adapter=self.cfg.adapter, enabled=False, path=path, error=str(e)
            )
        return Capabilities(
            name=self.name,
            adapter=self.cfg.adapter,
            enabled=True,
            version=version,
            path=path,
            flags=flags,
        )

    async def ask(self, prompt: str, files: list[Path] | None = None) -> AskResult:
        path = shutil.which(self.cmd)
        if not path:
            raise FileNotFoundError(f"{self.cmd} not on PATH")
        content = inline_files(prompt, files)
        argv = [path] + [a.replace("{prompt}", content) for a in _ASK_ARGV[self.cfg.adapter]]
        if self.cfg.adapter == "claude-sub" and self.cfg.model:
            argv += ["--model", self.cfg.model]
        t0 = time.monotonic()
        code, out, err = await _run(argv, self.timeout_s)
        if code != 0:
            raise RuntimeError(f"{self.cmd} exited {code}: {err.strip()[:2000]}")
        return AskResult(
            model=self.name, text=out.strip(), duration_s=round(time.monotonic() - t0, 2)
        )
