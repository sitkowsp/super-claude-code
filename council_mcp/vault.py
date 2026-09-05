"""Obsidian Phase B (DESIGN.md §20): the vault talks back.

- planning context: notes the planner reads before writing cards
- decisions: `DECISIONS.md` in the vault project folder → MEMORY.md (vault wins, append-only)
- inbox: blocked tasks become notes with an `answer:` field a human fills in Obsidian
- vault kit: Claudian slash commands that work on the mirrored notes
"""

from __future__ import annotations

import re
from pathlib import Path

from council_mcp.obsidian import ObsidianConfig, _frontmatter, _slug, resolve_vault

MAX_NOTE_CHARS = 20_000
MAX_TOTAL_CHARS = 60_000
SPEC_TAG_RE = re.compile(r"(?m)^tags?:.*council/spec|#council/spec\b")
ANSWER_RE = re.compile(r"(?ms)^---\n(.*?)\n---\n(.*)$")


def project_dir(cfg: ObsidianConfig, repo_root: Path) -> Path | None:
    vault = resolve_vault(cfg, repo_root)
    if not vault:
        return None
    return vault / cfg.folder / _slug(repo_root.name)


# ---- planning context ------------------------------------------------------------
def context_notes(cfg: ObsidianConfig, repo_root: Path) -> list[dict[str, str]]:
    """Notes for the planner: cfg.read_context (vault-relative), Plan.md, Decisions/*.md and any
    note tagged #council/spec under the project folder. Size-capped, newest first per group."""
    vault = resolve_vault(cfg, repo_root)
    pd = project_dir(cfg, repo_root)
    if not vault or not pd:
        return []
    candidates: list[Path] = []
    for rel in cfg.read_context:
        p = vault / rel
        if p.is_file():
            candidates.append(p)
    for name in ("Plan.md", "DECISIONS.md", "Questions.md"):
        if (pd / name).is_file():
            candidates.append(pd / name)
    if (pd / "Decisions").is_dir():
        candidates += sorted((pd / "Decisions").glob("*.md"), key=lambda p: -p.stat().st_mtime)
    if pd.is_dir():
        for p in sorted(pd.rglob("*.md"), key=lambda p: -p.stat().st_mtime):
            if p in candidates or "tasks" in p.parts or "reports" in p.parts or "inbox" in p.parts:
                continue
            try:
                head = p.read_text(encoding="utf-8", errors="replace")[:2000]
            except OSError:
                continue
            if SPEC_TAG_RE.search(head):
                candidates.append(p)
    out: list[dict[str, str]] = []
    total = 0
    seen: set[Path] = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        text = p.read_text(encoding="utf-8", errors="replace")[:MAX_NOTE_CHARS]
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        total += len(text)
        out.append({"note": str(p.relative_to(vault)).replace("\\", "/"), "text": text})
    return out


# ---- decisions -------------------------------------------------------------------
def sync_decisions(cfg: ObsidianConfig, repo_root: Path, memory_file: str) -> list[str]:
    """Append bullet lines from <project>/DECISIONS.md that MEMORY.md does not have yet."""
    pd = project_dir(cfg, repo_root)
    if not pd or not (pd / "DECISIONS.md").is_file():
        return []
    mem = repo_root / memory_file
    existing = mem.read_text(encoding="utf-8") if mem.exists() else ""
    new = []
    for line in (pd / "DECISIONS.md").read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")) and s[2:].strip() and s[2:].strip() not in existing:
            new.append(s[2:].strip())
    if new:
        mem.parent.mkdir(parents=True, exist_ok=True)
        with mem.open("a", encoding="utf-8") as f:
            f.write(
                "\n## Decyzje z vaulta (Obsidian)\n" if "Decyzje z vaulta" not in existing else ""
            )
            for n in new:
                f.write(f"- {n}\n")
    return new


# ---- inbox -----------------------------------------------------------------------
def inbox_write(
    cfg: ObsidianConfig, repo_root: Path, task_id: str, title: str, needs: list[str], body: str
) -> Path | None:
    pd = project_dir(cfg, repo_root)
    if not pd or not cfg.mirror:
        return None
    (pd / "inbox").mkdir(parents=True, exist_ok=True)
    note = pd / "inbox" / f"{task_id}.md"
    fm = {
        "council_inbox": task_id,
        "title": title,
        "answer": "",
        "remember": False,
        "tags": ["council", "inbox", "blocked"],
    }
    lines = [f"# {task_id} is blocked — {title}", "", "## Questions from the executor"]
    lines += [f"- {q}" for q in needs] or ["- (see report)"]
    lines += [
        "",
        "## Report excerpt",
        "",
        "> " + body[:1500].replace("\n", "\n> "),
        "",
        "---",
        "Write your answer in the `answer:` field above (one line, or use the section",
        "below for a long answer) and set `remember: true` to store it in MEMORY.md.",
        "",
        "## Answer",
        "",
    ]
    note.write_text(_frontmatter(fm) + "\n".join(lines) + "\n", encoding="utf-8")
    return note


def inbox_read(cfg: ObsidianConfig, repo_root: Path) -> list[dict[str, object]]:
    """Inbox notes with a non-empty answer (frontmatter `answer:` or text under `## Answer`)."""
    pd = project_dir(cfg, repo_root)
    if not pd or not (pd / "inbox").is_dir():
        return []
    out: list[dict[str, object]] = []
    for note in sorted((pd / "inbox").glob("T-*.md")):
        text = note.read_text(encoding="utf-8", errors="replace")
        m = ANSWER_RE.match(text)
        if not m:
            continue
        fm, body = m.group(1), m.group(2)
        ans = ""
        am = re.search(r"(?m)^answer:\s*(.+)$", fm)
        if am and am.group(1).strip().strip('"') not in ("", "''"):
            ans = am.group(1).strip().strip('"')
        if not ans:
            sec = body.split("## Answer", 1)
            if len(sec) == 2 and sec[1].strip():
                ans = sec[1].strip()
        if ans:
            remember = bool(re.search(r"(?m)^remember:\s*true", fm))
            out.append({"task": note.stem, "answer": ans, "remember": remember, "note": str(note)})
    return out


def inbox_close(cfg: ObsidianConfig, repo_root: Path, task_id: str) -> None:
    pd = project_dir(cfg, repo_root)
    if not pd:
        return
    note = pd / "inbox" / f"{task_id}.md"
    if note.exists():
        done = pd / "inbox" / "answered"
        done.mkdir(exist_ok=True)
        note.replace(done / note.name)


# ---- vault kit (Claudian) ---------------------------------------------------------
KIT: dict[str, str] = {
    "council-status.md": """---
description: Council board across projects (from the mirrored notes in this vault)
---
Read `Council/*/TASKS.md` and `Council/*/tasks/*.md`. Show a table per project: id, state, model,
attempt, title. List every note under `Council/*/inbox/` whose `answer` is empty — those tasks wait
for a human. Do not modify anything.
""",
    "council-answer.md": """---
description: Answer a blocked council task from the vault (the repo picks up the inbox note)
argument-hint: <T-001> <answer text>
---
Arguments: $ARGUMENTS — task id, then the answer. Open `Council/<project>/inbox/<id>.md`, put the
answer into the `answer:` frontmatter field (one line) or under `## Answer`, keep `remember: false`
unless the user says it is a lasting decision. The next `council_status` in Claude Code applies it.
""",
    "council-decide.md": """---
description: Record a project decision in the vault (merged into MEMORY.md at the next plan)
argument-hint: <project> <decision>
---
Append `- <decision>` to `Council/<project>/DECISIONS.md` (create it with a `# Decisions` heading if
missing). Keep decisions one line each, imperative, testable.
""",
    "council-handoff.md": """---
description: Read the latest HANDOFF.md of a project and summarise where it stopped
argument-hint: <project>
---
Read `Council/<project>/HANDOFF.md` and `Council/<project>/TASKS.md`. Summarise in under 10 lines:
state, blocked questions, planned next steps, warnings.
""",
}


def write_kit(cfg: ObsidianConfig, repo_root: Path) -> list[str]:
    vault = resolve_vault(cfg, repo_root)
    if not vault:
        return []
    d = vault / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in KIT.items():
        (d / name).write_text(text, encoding="utf-8")
        written.append(str((d / name).relative_to(vault)).replace("\\", "/"))
    claude_md = vault / "CLAUDE.md"
    marker = "<!-- council -->"
    block = (
        f"{marker}\n## Council projects\n\nFolders under `{cfg.folder}/` are mirrored from code "
        "repos by the `council` Claude Code plugin. Task notes carry `state`, `model`, `role` in "
        "frontmatter; `inbox/` holds blocked tasks waiting for a human answer; `DECISIONS.md` is "
        "merged into the repo's MEMORY.md at the next plan. Commands: /council-status, "
        "/council-answer, /council-decide, /council-handoff.\n"
    )
    existing = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    if marker not in existing:
        claude_md.write_text(
            existing.rstrip() + ("\n\n" if existing else "") + block, encoding="utf-8"
        )
        written.append("CLAUDE.md")
    return written
