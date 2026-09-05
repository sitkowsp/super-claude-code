"""Git layer (DESIGN.md §19.1–19.2): only council-mcp touches `.git`, always under one lock.

Per task:
  branch   council/<id>                (from the base branch)
  worktree .council/worktrees/<id>     owned by council-mcp; snapshots are committed here
  workdir  .council/work/<id>          what the executor sees: a copy WITHOUT .git and never_share
Sync workdir → worktree enforces `scope` deterministically; files outside scope are rejected.
"""

from __future__ import annotations

import asyncio
import filecmp
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from council_mcp import globs
from council_mcp.log import get

log = get(__name__)

CONTROL_FILES = {
    "REPORT.md",
    "PREVIOUS_REPORT.md",
    "TASK.md",
    "ANSWER.md",
    "AGENTS.md",
    "GEMINI.md",
    "CHARTER.md",
    "MEMORY.md",
}
SKIP_DIRS = {
    ".git",
    ".council",
    "node_modules",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
GIT_IDENT = ["-c", "user.name=council", "-c", "user.email=council@localhost"]


class GitError(RuntimeError):
    pass


class MergeConflict(GitError):
    def __init__(self, task_id: str, files: list[str], detail: str) -> None:
        super().__init__(f"{task_id}: rebase conflict in {files or 'unknown files'}")
        self.files = files
        self.detail = detail


@dataclass
class SyncResult:
    copied: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _walk(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file():
            out[rel.as_posix()] = p
    return out


class GitRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = asyncio.Lock()

    async def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *GIT_IDENT,
            *args,
            cwd=str(cwd or self.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if check and proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({proc.returncode}): "
                f"{err.decode(errors='replace').strip()}"
            )
        return out.decode(errors="replace")

    async def base_branch(self) -> str:
        for name in ("main", "master"):
            if (await self.git("rev-parse", "--verify", "-q", name, check=False)).strip():
                return name
        return (await self.git("rev-parse", "--abbrev-ref", "HEAD")).strip()

    # ---- create ------------------------------------------------------------
    async def create(self, task_id: str, never_share: list[str]) -> tuple[Path, Path]:
        """Create branch + worktree + executor workdir. Returns (worktree, workdir)."""
        wt = self.root / ".council" / "worktrees" / task_id
        wd = self.root / ".council" / "work" / task_id
        async with self.lock:
            base = await self.base_branch()
            if wt.exists():
                await self.git("worktree", "remove", "--force", str(wt), check=False)
            await self.git("worktree", "prune")
            branch = f"council/{task_id}"
            exists = (await self.git("rev-parse", "--verify", "-q", branch, check=False)).strip()
            if exists:
                await self.git("worktree", "add", str(wt), branch)
            else:
                await self.git("worktree", "add", "-b", branch, str(wt), base)
            self._export(wt, wd, never_share)
        return wt, wd

    def _export(self, wt: Path, wd: Path, never_share: list[str]) -> None:
        if wd.exists():
            shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True)
        for rel, src in _walk(wt).items():
            if globs.matches(rel, never_share):
                continue
            dst = wd / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # ---- sync + snapshot ---------------------------------------------------
    async def sync_and_snapshot(self, task_id: str, scope: list[str], message: str) -> SyncResult:
        wt = self.root / ".council" / "worktrees" / task_id
        wd = self.root / ".council" / "work" / task_id
        res = SyncResult()
        async with self.lock:
            src_files = _walk(wd)
            dst_files = _walk(wt)
            for rel, src in src_files.items():
                if rel in CONTROL_FILES:
                    continue
                dst = wt / rel
                if dst.exists() and filecmp.cmp(src, dst, shallow=False):
                    continue
                if not globs.matches(rel, scope):
                    res.rejected.append(rel)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                res.copied.append(rel)
            for rel in dst_files.keys() - src_files.keys():
                if rel in CONTROL_FILES:
                    continue
                if globs.matches(rel, scope):
                    (wt / rel).unlink()
                    res.deleted.append(rel)
                # deletion outside scope: keep the worktree file (executor copy lacked it,
                # e.g. never_share) — not a violation.
            if res.copied or res.deleted:
                await self.git("add", "-A", cwd=wt)
                await self.git("commit", "-q", "-m", message, cwd=wt, check=False)
        if res.rejected:
            log.warning("scope_violation", task=task_id, files=res.rejected)
        return res

    async def diff_stat(self, task_id: str) -> str:
        async with self.lock:
            base = await self.base_branch()
            return await self.git("diff", "--stat", f"{base}...council/{task_id}")

    async def merge(self, task_id: str) -> str:
        """Rebase council/<id> onto the base branch and merge --no-ff into it (one merge commit
        per task). On conflict: abort, leave everything as it was, raise MergeConflict."""
        branch = f"council/{task_id}"
        wt = self.root / ".council" / "worktrees" / task_id
        async with self.lock:
            base = await self.base_branch()
            if not wt.exists():
                await self.git("worktree", "add", str(wt), branch)
            # The executor never writes to the worktree (only sync_and_snapshot does, and it
            # commits). Unstaged changes here can only be side effects of gates run in it —
            # e.g. `uv run` refreshing a stale uv.lock, a formatter — and would make `rebase`
            # refuse with "unstaged changes" (misreported as a conflict before rc10). Discard.
            noise = (
                await self.git("status", "--porcelain", "--untracked-files=no", cwd=wt)
            ).strip()
            if noise:
                log.warning("worktree_gate_noise_discarded", task=task_id, status=noise)
                await self.git("checkout", "--", ".", cwd=wt)
            try:
                await self.git("rebase", base, cwd=wt)
            except GitError as e:
                files = (
                    await self.git("diff", "--name-only", "--diff-filter=U", cwd=wt, check=False)
                ).split()
                await self.git("rebase", "--abort", cwd=wt, check=False)
                if not files:
                    # not a content conflict — surface the real git error instead of
                    # burning one of the executor's attempts on a re-dispatch
                    raise GitError(f"{task_id}: rebase onto {base} failed: {e}") from e
                raise MergeConflict(task_id, files, str(e)) from e
            head = (await self.git("rev-parse", "--abbrev-ref", "HEAD")).strip()
            if head != base:
                raise GitError(f"repo HEAD is on '{head}', expected '{base}' — switch first")
            # council's own state under .council/ changes all the time; only user files matter
            status = (
                await self.git(
                    "status", "--porcelain", "--untracked-files=no", "--", ".", ":!.council"
                )
            ).strip()
            if status:
                raise GitError("main worktree has uncommitted changes — commit or stash first")
            await self.git("merge", "--no-ff", "-m", f"council: merge {task_id}", branch)
            return (await self.git("rev-parse", "--short", "HEAD")).strip()

    async def commit_paths(self, paths: list[str], message: str) -> str | None:
        """Commit specific tracked/untracked files on the main worktree (e.g. MEMORY.md after a
        merge) so the next merge finds a clean tree. Returns the short hash or None if nothing."""
        async with self.lock:
            await self.git("add", "--", *paths)
            staged = (await self.git("diff", "--cached", "--name-only")).strip()
            if not staged:
                return None
            await self.git("commit", "-q", "-m", message)
            return (await self.git("rev-parse", "--short", "HEAD")).strip()

    async def remove(self, task_id: str, keep_branch: bool = True) -> None:
        wt = self.root / ".council" / "worktrees" / task_id
        wd = self.root / ".council" / "work" / task_id
        async with self.lock:
            await self.git("worktree", "remove", "--force", str(wt), check=False)
            shutil.rmtree(wd, ignore_errors=True)
            if not keep_branch:
                await self.git("branch", "-D", f"council/{task_id}", check=False)
