"""`council` command line: init (bootstrap .council/ in a repo) and doctor (probe + report)."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from council_mcp import probe
from council_mcp.config import Privacy, Role, load
from council_mcp.render import TEMPLATES

GITIGNORE_LINES = [
    ".council/worktrees/",
    ".council/work/",
    ".council/capabilities.json",
    ".council/.last_seen",
    ".council/logs/",
]
MCP_JSON = {
    "mcpServers": {
        "council": {
            "command": "uv",
            "args": ["run", "--directory", "${COUNCIL_PLUGIN_DIR}", "council-mcp"],
            "env": {
                "COUNCIL_REPO_ROOT": "${CLAUDE_PROJECT_DIR}",
                "COUNCIL_OLLAMA_URL": "http://localhost:11434",
            },
        }
    }
}


def init(root: Path, plugin_dir: Path, force: bool = False) -> list[str]:
    done = []
    c = root / ".council"
    c.mkdir(exist_ok=True)
    for name, src in (
        ("council.json", TEMPLATES / "council.json"),
        ("CHARTER.md", TEMPLATES / "CHARTER.md"),
    ):
        dst = c / name
        if force or not dst.exists():
            shutil.copy2(src, dst)
            done.append(str(dst.relative_to(root)))
    mem = c / "MEMORY.md"
    if not mem.exists():
        mem.write_text("# Project memory\n\n## Decyzje\n\n## Konwencje\n", encoding="utf-8")
        done.append(".council/MEMORY.md")
    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing:
        with gi.open("a", encoding="utf-8") as f:
            f.write("\n# council runtime\n" + "\n".join(missing) + "\n")
        done.append(".gitignore")
    mcp = root / ".mcp.json"
    if force or not mcp.exists():
        data = json.loads(
            json.dumps(MCP_JSON).replace("${COUNCIL_PLUGIN_DIR}", plugin_dir.as_posix())
        )
        mcp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        done.append(".mcp.json")
    ga = root / ".gitattributes"
    if not ga.exists():
        ga.write_text("* text=auto eol=lf\n", encoding="utf-8")
        done.append(".gitattributes")
    return done


async def doctor(root: Path) -> int:
    problems = 0
    if not shutil.which("git"):
        print("FAIL git not on PATH")
        problems += 1
    if not shutil.which("uv"):
        print("WARN uv not on PATH (Claude Code needs it to start council-mcp)")
    try:
        cfg = load(root)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL config: {e}")
        return 1
    caps = await probe.probe_all(cfg)
    probe.write(caps, root)
    for name, c in caps.models.items():
        print(
            f"{'OK  ' if c.enabled else 'OFF '} {name:8s} {c.adapter:10s} "
            f"{c.version or ''} {c.error or ''}"
        )
    roles: list[Role] = ["implement", "review", "docs", "chores"]
    privacies: list[Privacy] = ["public", "internal", "local-only"]
    for role in roles:
        for privacy in privacies:
            cands = cfg.candidates(role, privacy)
            if not cands and role in cfg.routing.by_role:
                print(f"WARN no model for role={role} privacy={privacy}")
    print("wrote .council/capabilities.json")
    return problems


def events(root: Path) -> str:
    """Brief of events newer than `.council/.last_seen_hook` (own marker, not council_status's)."""
    from council_mcp.store import TaskStore

    c = root / ".council"
    if not (c / "events.jsonl").exists():
        return ""
    store = TaskStore(root)
    marker = c / ".last_seen_hook"
    since = marker.read_text().strip() if marker.exists() else None
    evs = [
        e
        for e in store.events(since)
        if e.type
        in (
            "blocked",
            "done",
            "failed",
            "scope_violation",
            "review_reject",
            "merged",
            "injection_suspect",
        )
    ]
    if not evs:
        return ""
    marker.write_text(evs[-1].ts if evs else "")
    lines = []
    for e in evs[-5:]:
        detail = e.reason or e.data.get("status") or ""
        if e.type == "blocked":
            detail = "; ".join(e.data.get("needs", [])) or detail
        lines.append(f"- {e.task} {e.type}" + (f": {str(detail)[:120]}" if detail else ""))
    more = f" (+{len(evs) - 5} more)" if len(evs) > 5 else ""
    return "[council] new events" + more + " — run council_status for details:\n" + "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="council")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="bootstrap .council/ and .mcp.json in a repo")
    p_init.add_argument("--root", type=Path, default=Path.cwd())
    p_init.add_argument("--force", action="store_true")
    p_doc = sub.add_parser("doctor", help="probe models and validate config")
    p_doc.add_argument("--root", type=Path, default=Path.cwd())
    p_ev = sub.add_parser("events", help="print a brief of new council events (hook)")
    p_ev.add_argument("--root", type=Path, default=Path.cwd())
    args = ap.parse_args(argv)
    plugin_dir = Path(__file__).resolve().parent.parent
    if args.cmd == "init":
        for d in init(args.root.resolve(), plugin_dir, args.force):
            print(f"wrote {d}")
        print("next: edit .council/council.json, then `council doctor`")
    elif args.cmd == "doctor":
        sys.exit(asyncio.run(doctor(args.root.resolve())))
    elif args.cmd == "events":
        brief = events(args.root.resolve())
        if brief:
            print(brief)
