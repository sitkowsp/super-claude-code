"""Executor catalog + environment checks: what is installed, what is logged in, what to do.

Used by `council doctor` (report), `council setup` (install missing npm CLIs on request) and the
SessionStart hook (one-line summary). Nothing here logs in for the user — logins open browsers and
must be done by a human; we print the exact command.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from council_mcp.config import CouncilConfig


@dataclass(frozen=True)
class Executor:
    adapter: str
    label: str
    cmd: str | None  # binary on PATH
    install: str  # how to install (shell command or URL)
    login: str  # how to log in
    npm_package: str | None = None  # installable by `council setup --install`
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


CATALOG: dict[str, Executor] = {
    "codex": Executor(
        "codex",
        "OpenAI Codex CLI (ChatGPT Plus/Pro)",
        "codex",
        "npm i -g @openai/codex",
        "codex login",
        npm_package="@openai/codex",
        notes="generates PNG images too",
    ),
    "copilot": Executor(
        "copilot",
        "GitHub Copilot CLI",
        "copilot",
        "npm i -g @github/copilot",
        "gh auth login   (Copilot CLI uses the GitHub CLI login)",
        npm_package="@github/copilot",
    ),
    "antigravity": Executor(
        "antigravity",
        "Google Antigravity CLI (Google account)",
        "agy",
        "https://antigravity.google  (installer; adds `agy` to PATH)",
        "agy   (interactive once, choose Sign in with Google)",
        notes="generates PNG images too",
    ),
    "gemini": Executor(
        "gemini",
        "Gemini CLI (API key only)",
        "gemini",
        "npm i -g @google/gemini-cli",
        "export GEMINI_API_KEY=...   (individual Google login was removed in 2026-06)",
        npm_package="@google/gemini-cli",
    ),
    "grok": Executor(
        "grok",
        "xAI Grok Build CLI (grok.com / X account)",
        "grok",
        "npm i -g @xai-official/grok   (or irm https://x.ai/cli/install.ps1 | iex)",
        "grok login   (browser OAuth; --device-auth for headless)",
        npm_package="@xai-official/grok",
    ),
    "claude-sub": Executor(
        "claude-sub",
        "Claude Code as cheap executor",
        "claude",
        "already installed with Claude Code",
        "claude   (already logged in if you are reading this)",
    ),
    "ollama": Executor(
        "ollama",
        "Ollama (local models)",
        "ollama",
        "https://ollama.com/download",
        "no login; `ollama pull qwen3:8b` then set COUNCIL_OLLAMA_URL",
    ),
}


class Check(BaseModel):
    model: str
    adapter: str
    installed: bool
    logged_in: bool | None  # None = cannot tell
    enabled: bool
    action: str  # what the user should do, "" if nothing


async def _run(argv: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode or 0, out.decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def _which(cmd: str) -> str | None:
    p = shutil.which(cmd)
    if p and p.lower().endswith(".ps1"):
        p = shutil.which(cmd + ".cmd") or p
    return p


async def login_state(adapter: str, cmd_path: str | None) -> bool | None:
    """True/False when we can tell, None otherwise. Cheap checks only — no model calls."""
    home = Path.home()
    if adapter == "codex":
        code, out = await _run([cmd_path or "codex", "login", "status"])
        return code == 0 and "logged in" in out.lower()
    if adapter == "copilot":
        gh = shutil.which("gh")
        if not gh:
            return None
        code, _ = await _run([gh, "auth", "status"])
        return code == 0
    if adapter == "antigravity":
        return (home / ".gemini" / "google_accounts.json").exists()
    if adapter == "grok":
        return (home / ".grok" / "auth.json").exists()
    if adapter == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY")) or None
    if adapter == "claude-sub":
        return True if cmd_path else None
    return None


async def check_all(cfg: CouncilConfig) -> list[Check]:
    out: list[Check] = []
    for name, m in cfg.models.items():
        ex = CATALOG.get(m.adapter)
        if m.adapter == "ollama":
            out.append(
                Check(
                    model=name,
                    adapter=m.adapter,
                    installed=bool(m.url),
                    logged_in=None,
                    enabled=m.enabled,
                    action=""
                    if m.enabled
                    else "start Ollama and pull the model; set COUNCIL_OLLAMA_URL",
                )
            )
            continue
        cmd = m.cmd or (ex.cmd if ex else None)
        path = _which(cmd) if cmd else None
        logged = await login_state(m.adapter, path) if path else None
        action = ""
        if not path and ex:
            action = f"install: {ex.install}"
        elif logged is False and ex:
            action = f"log in: {ex.login}"
        out.append(
            Check(
                model=name,
                adapter=m.adapter,
                installed=bool(path),
                logged_in=logged,
                enabled=m.enabled and bool(path),
                action=action,
            )
        )
    return out


def apply_probe(checks: list[Check], errors: dict[str, str | None]) -> list[Check]:
    """Merge probe errors into the doctor table: an executor that is installed and logged in but
    failed the availability probe (e.g. Ollama model not pulled) must not read as `ready`."""
    for c in checks:
        err = errors.get(c.model)
        if err and c.enabled and not c.action:
            hint = ""
            if c.adapter == "ollama" and "not pulled" in err:
                hint = " (ollama pull <model>)"
            c.action = f"probe failed: {err}{hint}"
            c.enabled = False
    return checks


def render(checks: list[Check]) -> str:
    rows = ["| model | adapter | installed | logged in | action |", "|---|---|---|---|---|"]
    for c in checks:
        li = {True: "yes", False: "NO", None: "?"}[c.logged_in]
        rows.append(
            f"| {c.model} | {c.adapter} | {'yes' if c.installed else 'NO'} | {li} | "
            f"{c.action or ('disabled in config' if not c.enabled else 'ready')} |"
        )
    return "\n".join(rows)


def brief(checks: list[Check]) -> str:
    ready = [c.model for c in checks if c.installed and c.logged_in is not False and c.enabled]
    todo = [f"{c.model}: {c.action}" for c in checks if c.action]
    line = f"[council] executors ready: {', '.join(ready) or 'none'}"
    if todo:
        line += "\n[council] to enable more: " + "; ".join(todo[:3])
        line += "  — run `council doctor` for details"
    return line


async def install_missing(cfg: CouncilConfig, dry_run: bool = True) -> list[str]:
    """Install missing npm-based CLIs. Returns the commands run (or that would run)."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    done: list[str] = []
    for c in await check_all(cfg):
        ex = CATALOG.get(c.adapter)
        if c.installed or not ex or not ex.npm_package or not c.enabled and c.adapter == "gemini":
            continue
        if not npm:
            done.append(f"# npm not found — install Node.js, then: {ex.install}")
            continue
        cmd = [npm, "i", "-g", ex.npm_package]
        done.append(" ".join(cmd))
        if not dry_run:
            code, out = await _run(cmd, timeout=600)
            if code != 0:
                done.append(f"# failed ({code}): {out[-300:]}")
    return done


def to_json(checks: list[Check]) -> str:
    return json.dumps([c.model_dump() for c in checks], indent=2)


def python_ok() -> bool:
    return sys.version_info >= (3, 12)
