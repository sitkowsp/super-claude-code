"""Executor catalog + environment checks: what is installed, what is logged in, what to do.

Used by `council doctor` (report), `council setup` (install missing npm CLIs on request) and the
SessionStart hook (one-line summary). Nothing here logs in for the user — logins open browsers and
must be done by a human; we print the exact command.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
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


_NOT_CHAT = ("bge", "embed", "ocr", "vl", "vision", "whisper", "rerank", "clip")
_PREFER = ("qwen3-coder", "coder", "qwen3", "qwen2.5", "qwen", "llama", "mistral", "gemma")


def pick_ollama_model(available: list[str], wanted: str | None = None) -> str | None:
    """Choose a pulled chat/tool model deterministically: the configured one if present, else by
    family preference (coder > qwen3 > ...), skipping embedding / vision / OCR models."""
    if wanted and wanted in available:
        return wanted
    chat = [m for m in available if not any(x in m.lower() for x in _NOT_CHAT)]
    for pref in _PREFER:
        hit = sorted((m for m in chat if pref in m.lower()), key=lambda m: ("/" in m, m))
        if hit:
            return hit[0]
    return chat[0] if chat else None


def list_ollama_models(url: str, timeout: float = 2.0) -> list[str]:
    """Names of pulled models at an Ollama URL; [] when unreachable (never raises)."""
    try:
        r = httpx.get(url.rstrip("/") + "/api/tags", timeout=timeout)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


_UE_CMD = (
    "Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
    "Engine/Binaries/Linux/UnrealEditor-Cmd",
    "Engine/Binaries/Mac/UnrealEditor-Cmd",
)


def _ue_editor(engine_root: Path) -> Path | None:
    for rel in _UE_CMD:
        if (engine_root / rel).exists():
            return engine_root / rel
    return None


def _ue_version_key(path: Path) -> tuple[int, ...]:
    m = re.search(r"UE_(\d+)(?:\.(\d+))?", str(path))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def _drive_roots() -> list[Path]:
    """Fixed local disks only. Network / removable / optical drives are skipped: a glob over a
    mapped share can block for minutes (this hung the test suite once)."""
    if os.name == "nt":
        try:
            import ctypes

            fixed = 3  # DRIVE_FIXED
            return [
                Path(f"{d}:/")
                for d in "CDEFGHIJKLMNOPQRSTUVWXYZ"
                if ctypes.windll.kernel32.GetDriveTypeW(f"{d}:\\") == fixed
            ]
        except Exception:  # noqa: BLE001
            return [Path("C:/")]
    return [Path.home(), Path("/opt")]


def _ue_registry() -> list[Path]:
    """`HKLM\\SOFTWARE\\EpicGames\\Unreal Engine\\<ver>\\InstalledDirectory` (Windows only)."""
    if os.name != "nt":
        return []
    out: list[Path] = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine") as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                with winreg.OpenKey(k, sub) as sk:
                    try:
                        out.append(Path(winreg.QueryValueEx(sk, "InstalledDirectory")[0]))
                    except OSError:
                        pass
    except Exception:  # noqa: BLE001
        pass
    return out


def unreal_candidates() -> list[Path]:
    """Engine roots, most authoritative first: `UE_ROOT`, Epic Launcher's install list, the Windows
    registry, then a shallow scan of every drive for `UE_*` folders (≤3 levels, e.g.
    `D:/GAMES/Unreal/UE_5.8`). Never raises."""
    found: list[Path] = []
    if os.environ.get("UE_ROOT"):
        found.append(Path(os.environ["UE_ROOT"]))
    try:  # Epic Launcher: %ProgramData%/Epic/UnrealEngineLauncher/LauncherInstalled.dat
        dat = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / (
            "Epic/UnrealEngineLauncher/LauncherInstalled.dat"
        )
        if dat.exists():
            for item in json.loads(dat.read_text(encoding="utf-8")).get("InstallationList", []):
                if str(item.get("AppName", "")).startswith("UE_") and item.get("InstallLocation"):
                    found.append(Path(item["InstallLocation"]))
    except Exception:  # noqa: BLE001
        pass
    found += _ue_registry()
    scanned: list[Path] = []
    for drive in _drive_roots():
        for pat in ("UE_*", "*/UE_*", "*/*/UE_*", "Epic Games/UE_*"):
            try:
                scanned += [d for d in drive.glob(pat) if d.is_dir()]
            except Exception:  # noqa: BLE001
                continue
    found += sorted(set(scanned), key=_ue_version_key, reverse=True)
    seen: set[str] = set()
    out: list[Path] = []
    for f in found:
        if str(f) not in seen:
            seen.add(str(f))
            out.append(f)
    return out


_TOOLS_CACHE: dict[str, str | None] | None = None


def detect_tools(refresh: bool = False) -> dict[str, str | None]:
    """Local creative tooling an executor may call headlessly. Values are absolute paths or None.
    Blender: `BLENDER_EXE`, PATH, or `Program Files/Blender Foundation/Blender*`. Unreal: see
    `unreal_candidates()` → first root that has `UnrealEditor-Cmd`. The drive scan costs a few
    seconds, so the result is cached per process (`refresh=True` rescans). Never raises."""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None and not refresh:
        return dict(_TOOLS_CACHE)
    out: dict[str, str | None] = {"blender": None, "unreal": None}
    try:
        b = os.environ.get("BLENDER_EXE") or shutil.which("blender")
        if not b:
            for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), "/Applications"):
                cands = sorted(Path(base).glob("Blender Foundation/Blender*/blender.exe")) + sorted(
                    Path(base).glob("Blender*.app/Contents/MacOS/Blender")
                )
                if cands:
                    b = str(cands[-1])
                    break
        out["blender"] = b if b and Path(b).exists() else None
        for r in unreal_candidates():
            ed = _ue_editor(r)
            if ed:
                out["unreal"] = str(ed)
                break
    except Exception:  # noqa: BLE001 - detection must never break a dispatch
        pass
    _TOOLS_CACHE = dict(out)
    return out


def apply_probe(
    checks: list[Check],
    errors: dict[str, str | None],
    available: dict[str, list[str]] | None = None,
) -> list[Check]:
    """Merge probe errors into the doctor table: an executor that is installed and logged in but
    failed the availability probe (e.g. Ollama model not pulled) must not read as `ready`."""
    for c in checks:
        err = errors.get(c.model)
        if err and c.enabled and not c.action:
            hint = ""
            if c.adapter == "ollama" and "not pulled" in err:
                pick = pick_ollama_model((available or {}).get(c.model, []))
                hint = (
                    f" (set models.{c.model}.model to a pulled one, e.g. {pick})"
                    if pick
                    else " (ollama pull <model>)"
                )
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
