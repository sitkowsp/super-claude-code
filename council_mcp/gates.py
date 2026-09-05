"""Deterministic gates (DESIGN.md §14.5): shell commands run in a worktree before review and
after merge. Results go to `reports/<id>/gates.json`; the reviewer starts from them."""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from pathlib import Path

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    cmd: str
    ok: bool
    exit_code: int | None
    duration_s: float
    output: str  # tail, untrusted


class GatesReport(BaseModel):
    stage: str
    ok: bool
    results: list[GateResult] = Field(default_factory=list)


async def run_one(cmd: str, cwd: Path, timeout_s: float = 600) -> GateResult:
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            return GateResult(
                cmd=cmd,
                ok=False,
                exit_code=None,
                duration_s=round(time.monotonic() - t0, 1),
                output="timeout",
            )
        return GateResult(
            cmd=cmd,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            duration_s=round(time.monotonic() - t0, 1),
            output=out.decode(errors="replace")[-4000:],
        )
    except Exception as e:  # noqa: BLE001
        return GateResult(
            cmd=cmd,
            ok=False,
            exit_code=None,
            duration_s=round(time.monotonic() - t0, 1),
            output=str(e),
        )


async def run(cmds: list[str], cwd: Path, stage: str) -> GatesReport:
    results = [await run_one(c, cwd) for c in cmds]
    return GatesReport(stage=stage, ok=all(r.ok for r in results), results=results)


def write(report: GatesReport, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"gates-{report.stage}.json"
    path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    return path


def split(cmd: str) -> list[str]:
    return shlex.split(cmd)
