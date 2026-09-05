"""`council` command line: init (bootstrap .council/ in a repo) and doctor (probe + report)."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from council_mcp import obsidian, probe, setup
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
            "comment": "written by `council init`; a plugin install uses the plugin's .mcp.json",
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
    print()
    print(setup.render(await setup.check_all(cfg)))
    print()
    ob = obsidian.status(cfg.obsidian, root)
    if ob["obsidian_installed"]:
        where = "repo is inside the vault" if ob["repo_inside_vault"] else f"mirror → {ob['vault']}"
        print(
            f"Obsidian: vault {ob['vault']} ({where}); Claudian plugin: "
            f"{'yes' if ob['claudian'] else 'no — install it in Obsidian for chat-in-vault'}"
        )
    else:
        print("Obsidian: not detected (optional; see docs/obsidian.md)")
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


def report(root: Path) -> str:
    """One-page Markdown report for the people who pay for this (DESIGN.md §16.14):
    tasks by state and model, review outcomes, trust table, time split Claude vs executors."""
    from collections import Counter
    from datetime import datetime

    from council_mcp import stats as st_mod
    from council_mcp.store import TaskStore

    store = TaskStore(root)
    tasks = store.all()
    evs = store.events()
    st = st_mod.load(root)
    by_state = Counter(t.state for t in tasks)
    by_model = Counter(t.assigned_to or "-" for t in tasks)
    types = Counter(e.type for e in evs)
    # executor wall time: dispatched → done/blocked/failed per task attempt
    exec_s = 0.0
    last_dispatch: dict[str, datetime] = {}
    for e in evs:
        ts = datetime.fromisoformat(e.ts)
        if e.type == "dispatched":
            last_dispatch[e.task] = ts
        elif e.type in ("done", "blocked", "failed") and e.task in last_dispatch:
            exec_s += (ts - last_dispatch.pop(e.task)).total_seconds()
    claude_actions = sum(1 for e in evs if e.actor == "claude")
    lines = [
        f"# Council report — {datetime.now().date().isoformat()}",
        "",
        f"Tasks: {len(tasks)} — " + ", ".join(f"{k} {v}" for k, v in sorted(by_state.items())),
        "By model: " + ", ".join(f"{k} {v}" for k, v in sorted(by_model.items())),
        f"Reviews: ok {types.get('review_ok', 0)}, rejected {types.get('review_reject', 0)}, "
        f"merged {types.get('merged', 0)}, defects after merge {types.get('defect', 0)}, "
        f"scope violations {types.get('scope_violation', 0)}, dissent {types.get('dissent', 0)}",
        f"Executor wall time: {exec_s / 60:.0f} min; orchestrator actions: {claude_actions}",
        "",
        "## Trust",
        "",
        st_mod.summary(st) if st.models else "_no data yet_",
        "",
        "## Tasks",
        "",
        "| id | title | model | state | attempt | reason |",
        "|---|---|---|---|---|---|",
    ]
    for t in tasks:
        lines.append(
            f"| {t.id} | {t.title} | {t.assigned_to or '-'} | {t.state} | {t.attempt} | "
            f"{(t.reason or '')[:80]} |"
        )
    return "\n".join(lines) + "\n"


async def setup_cmd(root: Path, install: bool) -> int:
    cfg = load(root)
    checks = await setup.check_all(cfg)
    print(setup.render(checks))
    cmds = await setup.install_missing(cfg, dry_run=not install)
    if cmds:
        print("\n" + ("Installing:" if install else "Would install (re-run with --install):"))
        for line in cmds:
            print("  " + line)
    logins = [c for c in checks if c.installed and c.logged_in is False]
    if logins or not install:
        print("\nLogins are done by you (they open a browser):")
        for c in checks:
            ex = setup.CATALOG.get(c.adapter)
            if ex and c.enabled and c.logged_in is not True and c.adapter not in ("ollama",):
                print(f"  {c.model:12s} {ex.login}")
    return 0


def session_start(root: Path, plugin_dir: Path) -> str:
    """SessionStart hook: make sure .council exists (idempotent) and print a one-line status.
    Cheap: no model calls, no probing beyond `which`. Output goes into Claude's context."""
    import asyncio as _asyncio

    lines = []
    if not (root / ".council" / "council.json").exists():
        done = init(root, plugin_dir)
        lines.append(
            f"[council] initialised {root.name}: {', '.join(done)} — edit .council/council.json"
        )
    try:
        cfg = load(root)
        checks = _asyncio.run(setup.check_all(cfg))
        lines.append(setup.brief(checks))
        ob = obsidian.status(cfg.obsidian, root)
        if ob["obsidian_installed"] and ob["vault"]:
            lines.append(
                f"[council] Obsidian vault: {ob['vault']}"
                + ("" if ob["claudian"] else " (Claudian plugin not installed)")
            )
        handoff = root / ".council" / "HANDOFF.md"
        if handoff.exists():
            lines.append("[council] HANDOFF.md exists — read it first (council_status returns it)")
    except Exception as e:  # noqa: BLE001
        lines.append(f"[council] config problem: {e}")
    return "\n".join(lines)


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
    p_set = sub.add_parser("setup", help="check executors; --install installs missing npm CLIs")
    p_set.add_argument("--root", type=Path, default=Path.cwd())
    p_set.add_argument("--install", action="store_true")
    p_ss = sub.add_parser("session-start", help="hook: init if needed + one-line status")
    p_ss.add_argument("--root", type=Path, default=Path.cwd())
    p_ob = sub.add_parser("obsidian", help="show vault detection or mirror council state into it")
    p_ob.add_argument("--root", type=Path, default=Path.cwd())
    p_ob.add_argument("--mirror", action="store_true")
    p_rep = sub.add_parser("report", help="one-page Markdown report (tasks, reviews, trust, time)")
    p_rep.add_argument("--root", type=Path, default=Path.cwd())
    p_rep.add_argument("--out", type=Path, default=None, help="write to file instead of stdout")
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
    elif args.cmd == "setup":
        sys.exit(asyncio.run(setup_cmd(args.root.resolve(), args.install)))
    elif args.cmd == "session-start":
        out = session_start(args.root.resolve(), plugin_dir)
        if out:
            print(out)
    elif args.cmd == "obsidian":
        cfg = load(args.root.resolve())
        print(json.dumps(obsidian.status(cfg.obsidian, args.root.resolve()), indent=2))
        if args.mirror:
            print("mirrored to:", obsidian.mirror(args.root.resolve(), cfg.obsidian))
    elif args.cmd == "report":
        text = report(args.root.resolve())
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
