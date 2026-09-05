"""Obsidian bridge (DESIGN.md §20): an Obsidian vault as the project "mastermind".

Phase A (this module): detect vaults and the Claudian plugin; mirror council's Markdown state
(MEMORY, HANDOFF, LESSONS, TASKS, reports, task cards as notes with YAML frontmatter) into
`<vault>/<folder>/<project>/` so Obsidian/Dataview/Claudian can read and link it.
Reading vault notes back as planning context is Phase B (see DESIGN §20).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ObsidianConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault: str | None = None  # absolute path; None = auto-detect the open vault
    folder: str = "Council"  # folder inside the vault
    mirror: bool = True  # mirror state on handoff / merge / plan
    read_context: list[str] = Field(default_factory=list)  # vault-relative notes for the planner


def config_file() -> Path | None:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return Path(base) / "obsidian" / "obsidian.json" if base else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "obsidian" / "obsidian.json"


def detect_vaults() -> list[dict[str, object]]:
    """Vaults Obsidian knows about: [{path, open, ts}]. Empty if Obsidian is not installed."""
    p = config_file()
    if not p or not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for v in data.get("vaults", {}).values():
        if isinstance(v, dict) and v.get("path"):
            out.append({"path": v["path"], "open": bool(v.get("open")), "ts": v.get("ts", 0)})
    return sorted(out, key=lambda v: (not v["open"], -int(v["ts"] or 0)))


CLAUDIAN_IDS = {"realclaudian", "oh-my-claudian", "claudian"}


def has_claudian(vault: Path) -> bool:
    """Claudian (community id `realclaudian`) or its fork: match on manifest id, not folder name."""
    plugins = vault / ".obsidian" / "plugins"
    if not plugins.is_dir():
        return False
    for d in plugins.iterdir():
        if d.name in CLAUDIAN_IDS:
            return True
        manifest = d / "manifest.json"
        if manifest.exists():
            try:
                if json.loads(manifest.read_text(encoding="utf-8")).get("id") in CLAUDIAN_IDS:
                    return True
            except (OSError, json.JSONDecodeError):
                continue
    return False


ENV_VAULT = "COUNCIL_OBSIDIAN_VAULT"  # user-level default: one vault for all council projects


def resolve_vault(cfg: ObsidianConfig, repo_root: Path) -> Path | None:
    """Order: council.json `vault` → env COUNCIL_OBSIDIAN_VAULT → vault containing the repo →
    the open vault."""
    for candidate in (cfg.vault, os.environ.get(ENV_VAULT)):
        if candidate:
            p = Path(os.path.expandvars(candidate)).expanduser()
            if p.exists():
                return p
    for v in detect_vaults():
        vp = Path(str(v["path"]))
        # prefer a vault that already contains the repo, else the open one
        if vp.exists() and repo_root.resolve().is_relative_to(vp.resolve()):
            return vp
    for v in detect_vaults():
        vp = Path(str(v["path"]))
        if v["open"] and vp.exists():
            return vp
    return None


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "project"


def mirror(repo_root: Path, cfg: ObsidianConfig, project: str | None = None) -> Path | None:
    """Copy council state into the vault as notes. Returns the target folder or None."""
    vault = resolve_vault(cfg, repo_root)
    if not vault or not cfg.mirror:
        return None
    if repo_root.resolve().is_relative_to(vault.resolve()):
        # repo lives inside the vault: .council/*.md is already visible — write only an index note
        target = vault / cfg.folder
        target.mkdir(parents=True, exist_ok=True)
        _write_index(
            target / f"{_slug(project or repo_root.name)}.md", repo_root, vault, inline=False
        )
        return target
    target = vault / cfg.folder / _slug(project or repo_root.name)
    (target / "tasks").mkdir(parents=True, exist_ok=True)
    (target / "reports").mkdir(parents=True, exist_ok=True)
    c = repo_root / ".council"
    for name in ("MEMORY.md", "HANDOFF.md", "LESSONS.md", "TASKS.md"):
        if (c / name).exists():
            shutil.copy2(c / name, target / name)
    for rep in c.glob("REPORT-*.md"):
        shutil.copy2(rep, target / rep.name)
    from council_mcp.store import TaskStore  # local import: config → obsidian → store → config

    store = TaskStore(repo_root)
    for t in store.all():
        fm = {
            "council_task": t.id,
            "title": t.title,
            "state": t.state,
            "role": t.role,
            "privacy": t.privacy,
            "model": t.assigned_to or "",
            "attempt": t.attempt,
            "created": t.created,
            "finished": t.finished or "",
            "tags": ["council", t.state],
        }
        acceptance = [f"- {a}" for a in t.acceptance] or ["- (none)"]
        body = [
            f"# {t.id} — {t.title}",
            "",
            t.goal,
            "",
            "## Scope",
            *[f"- `{s}`" for s in t.scope],
            "",
            "## Acceptance",
            *acceptance,
        ]
        if t.last_report:
            body += [
                "",
                "## Last report",
                f"status: {t.last_report.status} ({t.last_report.percent}%)",
                "",
                t.last_report.body,
            ]
        if t.reason:
            body += ["", f"> reason: {t.reason}"]
        (target / "tasks" / f"{t.id}.md").write_text(
            _frontmatter(fm) + "\n".join(body) + "\n", encoding="utf-8"
        )
        src = c / "reports" / t.id
        if src.exists():
            dst = target / "reports" / t.id
            dst.mkdir(exist_ok=True)
            for f in src.glob("*"):
                shutil.copy2(f, dst / f.name)
    _write_index(target / "README.md", repo_root, vault, inline=True)
    return target


def _frontmatter(d: dict[str, object]) -> str:
    lines = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, str) else v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _write_index(path: str | Path, repo_root: Path, vault: Path, inline: bool) -> None:
    path = Path(path)
    rel = os.path.relpath(repo_root, vault).replace("\\", "/") if not inline else "."
    fm: dict[str, object] = {
        "council_project": repo_root.name,
        "repo": str(repo_root),
        "tags": ["council", "project"],
    }
    body = [f"# {repo_root.name} — council", ""]
    if inline:
        body += [
            "Mirrored from `.council/` in the repo. Notes: [[MEMORY]], [[HANDOFF]], [[LESSONS]], "
            "[[TASKS]]; task cards in `tasks/`, executor reports in `reports/`.",
            "",
            "```dataview",
            'TABLE state, model, attempt FROM "'
            + str(path.parent.relative_to(vault)).replace("\\", "/")
            + '/tasks" SORT file.name',
            "```",
        ]
    else:
        body += [
            f"The repo lives inside this vault at `{rel}`; its `.council/` notes are here:",
            f"[[{rel}/.council/MEMORY|MEMORY]], [[{rel}/.council/HANDOFF|HANDOFF]], "
            f"[[{rel}/.council/LESSONS|LESSONS]], [[{rel}/.council/TASKS|TASKS]].",
        ]
    path.write_text(_frontmatter(fm) + "\n".join(body) + "\n", encoding="utf-8")


def status(cfg: ObsidianConfig, repo_root: Path) -> dict[str, object]:
    vaults = detect_vaults()
    vault = resolve_vault(cfg, repo_root)
    return {
        "obsidian_installed": bool(config_file() and config_file().exists()),  # type: ignore[union-attr]
        "vaults": [v["path"] for v in vaults],
        "vault": str(vault) if vault else None,
        "repo_inside_vault": bool(vault and repo_root.resolve().is_relative_to(vault.resolve())),
        "claudian": has_claudian(vault) if vault else False,
        "mirror": cfg.mirror,
    }
