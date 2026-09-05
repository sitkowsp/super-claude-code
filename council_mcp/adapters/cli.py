"""Generic CLI adapter for gemini / codex / copilot / grok / claude -p (DESIGN.md §5.3–5.6).

`probe`: which + --version + --help flag scan.  `ask`: one-shot prompt.
`run`: start the CLI non-interactively in the task workdir with its native auto-approve mode.
Approval flags are chosen from the flags detected by `probe` (never assumed).
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path

from council_mcp import render
from council_mcp.adapters.base import (
    AskResult,
    Capabilities,
    RunHandle,
    inline_files,
    wait_with_budget,
)
from council_mcp.config import Budget, ModelConfig
from council_mcp.log import get
from council_mcp.store import Task

log = get(__name__)
_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")

# One-shot ask: argv template, {prompt} substituted.
_ASK_ARGV: dict[str, list[str]] = {
    "gemini": ["-p", "{prompt}"],
    "antigravity": ["-p", "{prompt}", "--output-format", "text", "--print-timeout", "10m"],
    "codex": ["exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "{prompt}"],
    "copilot": ["-p", "{prompt}", "--silent"],
    "grok": ["-p", "{prompt}", "--output-format", "plain"],
    "claude-sub": ["-p", "{prompt}", "--output-format", "text"],
}

# Task run: argv template; {prompt} substituted; {workdir} substituted. Preferred approval flags
# listed in order — the first one present in detected `flags` is used (empty = none needed).
_RUN_ARGV: dict[str, list[str]] = {
    "gemini": ["-p", "{prompt}"],
    "antigravity": [
        "-p",
        "{prompt}",
        "--output-format",
        "text",
        "--print-timeout",
        "25m",
        "--add-dir",
        "{workdir}",
    ],
    "codex": [
        "exec",
        "--skip-git-repo-check",
        "-s",
        "workspace-write",
        "-C",
        "{workdir}",
        "{prompt}",
    ],
    "copilot": ["-p", "{prompt}", "--silent", "-C", "{workdir}", "--add-dir", "{workdir}"],
    "grok": ["-p", "{prompt}", "--cwd", "{workdir}", "--output-format", "plain"],
    "claude-sub": ["-p", "{prompt}", "--output-format", "text"],
}
_APPROVAL: dict[str, list[list[str]]] = {
    "gemini": [["--approval-mode", "yolo"], ["--yolo"]],
    "antigravity": [["--dangerously-skip-permissions"]],
    "codex": [["-c", "approval_policy=never"]],
    "copilot": [["--allow-all-tools", "--allow-all-paths"], ["--allow-all"]],
    "grok": [["--always-approve"], ["--permission-mode", "bypassPermissions"], ["--yolo"]],
    "claude-sub": [
        [
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Edit,Write,Glob,Grep,Bash(pytest*),Bash(ruff*),Bash(npm test*)",
        ]
    ],
}
# Adapters that read AGENTS.md/GEMINI.md themselves; others get the Charter inline in the prompt.
_READS_CHARTER_FILE = {"codex", "gemini", "antigravity", "copilot", "grok"}


_SHIM_RE = re.compile(r'"%dp0%\\([^"]+\.[cm]?js)"')


def shim_target(path: str) -> list[str]:
    """For an npm `.cmd` shim return ["node", "<abs script>"]; otherwise [path]."""
    if not path.lower().endswith(".cmd"):
        return [path]
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [path]
    m = _SHIM_RE.search(text)
    node = shutil.which("node")
    if not m or not node:
        return [path]
    return [node, str(Path(path).parent / m.group(1))]


async def _run(argv: list[str], timeout_s: float, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
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
        self.flags: list[str] = []
        self.repo_root = Path.cwd()

    def _path(self) -> str:
        # npm shims on Windows are .ps1/.cmd; prefer the .cmd so create_subprocess_exec works.
        p = shutil.which(self.cmd)
        if p and p.lower().endswith(".ps1"):
            alt = shutil.which(self.cmd + ".cmd")
            p = alt or p
        if not p:
            raise FileNotFoundError(f"{self.cmd} not on PATH")
        return p

    def _exe(self) -> list[str]:
        """argv prefix. A .cmd npm shim goes through cmd.exe, which truncates arguments at the
        first newline — every flag after a multi-line prompt would be lost. Bypass the shim and
        run `node <script>` directly."""
        return shim_target(self._path())

    async def probe(self) -> Capabilities:
        try:
            path = self._path()
        except FileNotFoundError as e:
            return Capabilities(
                name=self.name, adapter=self.cfg.adapter, enabled=False, error=str(e)
            )
        try:
            exe = self._exe()
            _, out, err = await _run([*exe, "--version"], 20)
            text = (out or err).strip()
            version = text.splitlines()[0] if text else None
            _, out, err = await _run([*exe, "--help"], 20)
            if self.cfg.adapter == "codex":
                _, o2, e2 = await _run([*exe, "exec", "--help"], 20)
                out += o2 + e2
            self.flags = sorted(set(_FLAG_RE.findall(out + err)))
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
            flags=self.flags,
        )

    def _model_args(self) -> list[str]:
        if self.cfg.model and self.cfg.adapter == "antigravity":
            return ["--model", self.cfg.model]
        if (
            self.cfg.model
            and "--model" in self.flags
            or self.cfg.model
            and self.cfg.adapter == "claude-sub"
        ):
            return ["--model", self.cfg.model]
        if self.cfg.model and self.cfg.adapter == "codex":
            return ["-m", self.cfg.model]
        return []

    def _approval_args(self) -> list[str]:
        for cand in _APPROVAL.get(self.cfg.adapter, []):
            if not self.flags or all(a in self.flags for a in cand if a.startswith("--")):
                return cand
        return []

    async def ask(self, prompt: str, files: list[Path] | None = None) -> AskResult:
        self._path()  # raises if missing
        content = inline_files(prompt, files)
        argv = self._exe() + [a.replace("{prompt}", content) for a in _ASK_ARGV[self.cfg.adapter]]
        argv += self._model_args()
        t0 = time.monotonic()
        code, out, err = await _run(argv, self.timeout_s)
        if code != 0:
            raise RuntimeError(f"{self.cmd} exited {code}: {err.strip()[:2000]}")
        text = out.strip()
        if self.cfg.adapter == "codex":  # codex exec prints the answer last, after progress lines
            text = text.split("\ntokens used")[0].strip()
        return AskResult(model=self.name, text=text, duration_s=round(time.monotonic() - t0, 2))

    async def run(self, task: Task, workdir: Path, budget: Budget, resume: bool) -> RunHandle:
        self._path()  # raises if missing
        inline = None if self.cfg.adapter in _READS_CHARTER_FILE else render.charter(self.repo_root)
        # Absolute workdir up front: agy/codex image tools default to their own scratch dirs.
        prompt = (
            f"Katalog roboczy (jedyne miejsce zapisu): {workdir.resolve()}\n\n"
            + render.cli_prompt(task, resume, inline)
        )
        argv = self._exe() + [
            a.replace("{prompt}", prompt).replace("{workdir}", str(workdir))
            for a in _RUN_ARGV[self.cfg.adapter]
        ]
        argv += self._approval_args() + self._model_args()
        log_dir = self.repo_root / ".council" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{task.id}-{task.attempt}-{self.name}.log"
        handle = RunHandle(task_id=task.id, model=self.name, log_path=log_path)

        async def _go() -> None:
            try:
                with log_path.open("ab") as logf:
                    logf.write(f"$ {' '.join(argv[:6])} ...\n".encode())
                    logf.flush()
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        cwd=str(workdir),
                        stdout=logf,
                        stderr=asyncio.subprocess.STDOUT,
                        stdin=asyncio.subprocess.DEVNULL,
                    )
                    code = await wait_with_budget(proc, handle, budget)
                handle.finish(code, "cancelled" if handle.cancelled else None)
            except Exception as e:  # noqa: BLE001
                log.error("cli_run_error", task=task.id, model=self.name, error=str(e))
                handle.finish(-1, str(e))

        asyncio.ensure_future(_go())
        return handle
