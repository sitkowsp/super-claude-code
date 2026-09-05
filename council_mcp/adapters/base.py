"""BaseAdapter protocol (DESIGN.md §5.1). Phase 0 implements `probe` and `ask` only;
`run`/`cancel` (worktree dispatch) arrive in Phase 1."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class Capabilities(BaseModel):
    name: str
    adapter: str
    enabled: bool
    version: str | None = None
    path: str | None = None
    flags: list[str] = Field(default_factory=list)  # detected from --help
    models: list[str] = Field(default_factory=list)  # ollama: /api/tags
    error: str | None = None


class AskResult(BaseModel):
    model: str
    text: str
    duration_s: float
    tokens_in: int | None = None
    tokens_out: int | None = None


class Adapter(Protocol):
    name: str

    async def probe(self) -> Capabilities: ...

    async def ask(self, prompt: str, files: list[Path] | None = None) -> AskResult:
        """One-shot question, no worktree, no tools. Files (if any) are inlined into the prompt."""
        ...


MAX_FILE_CHARS = 40_000


def inline_files(prompt: str, files: list[Path] | None, root: Path | None = None) -> str:
    """Append file contents to the prompt as fenced blocks. Refuses to leave `root` (cwd)."""
    if not files:
        return prompt
    base = (root or Path.cwd()).resolve()
    parts = [prompt, "", "## Files"]
    for f in files:
        p = (base / f).resolve()
        if not p.is_relative_to(base):
            raise ValueError(f"refusing to read outside repo: {f}")
        body = p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        parts += [f"### {Path(f).as_posix()}", "```", body, "```"]
    return "\n".join(parts)
