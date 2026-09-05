from __future__ import annotations

from pathlib import Path

from council_mcp import analyze, vault
from council_mcp.obsidian import ObsidianConfig


def _vault(tmp_path: Path) -> tuple[Path, Path, ObsidianConfig]:
    v = tmp_path / "Vault"
    (v / ".obsidian").mkdir(parents=True)
    repo = tmp_path / "proj"
    (repo / ".council").mkdir(parents=True)
    return v, repo, ObsidianConfig(vault=str(v), folder="Council")


def test_context_notes_plan_decisions_and_tagged(tmp_path: Path) -> None:
    v, repo, cfg = _vault(tmp_path)
    pd = v / "Council" / "proj"
    (pd / "Decisions").mkdir(parents=True)
    (pd / "Plan.md").write_text("# plan\nbuild X", encoding="utf-8")
    (pd / "Decisions" / "001-db.md").write_text("use sqlite", encoding="utf-8")
    (pd / "notes.md").write_text("---\ntags: [council/spec]\n---\nspec body", encoding="utf-8")
    (pd / "random.md").write_text("not relevant", encoding="utf-8")
    (pd / "tasks").mkdir()
    (pd / "tasks" / "T-001.md").write_text("---\ntags: [council/spec]\n---\nx", encoding="utf-8")
    (v / "Global.md").write_text("global note", encoding="utf-8")
    cfg.read_context = ["Global.md", "missing.md"]
    notes = vault.context_notes(cfg, repo)
    names = [n["note"] for n in notes]
    assert names[0] == "Global.md"
    assert "Council/proj/Plan.md" in names and "Council/proj/Decisions/001-db.md" in names
    assert "Council/proj/notes.md" in names and "Council/proj/random.md" not in names
    assert not any("tasks/" in n for n in names)


def test_sync_decisions_appends_new_bullets_once(tmp_path: Path) -> None:
    v, repo, cfg = _vault(tmp_path)
    pd = v / "Council" / "proj"
    pd.mkdir(parents=True)
    (pd / "DECISIONS.md").write_text("# Decisions\n- use sqlite\n- no CDN\n", encoding="utf-8")
    mem = repo / ".council" / "MEMORY.md"
    mem.write_text("# mem\n- no CDN\n", encoding="utf-8")
    assert vault.sync_decisions(cfg, repo, ".council/MEMORY.md") == ["use sqlite"]
    text = mem.read_text(encoding="utf-8")
    assert "Decyzje z vaulta" in text and text.count("use sqlite") == 1
    assert vault.sync_decisions(cfg, repo, ".council/MEMORY.md") == []


def test_inbox_roundtrip(tmp_path: Path) -> None:
    v, repo, cfg = _vault(tmp_path)
    note = vault.inbox_write(cfg, repo, "T-007", "db choice", ["which db?", "why?"], "body text")
    assert note and note.name == "T-007.md" and vault.inbox_read(cfg, repo) == []
    text = note.read_text(encoding="utf-8").replace('answer: ""', 'answer: "use sqlite"')
    text = text.replace("remember: False", "remember: true")
    note.write_text(text, encoding="utf-8")
    items = vault.inbox_read(cfg, repo)
    assert (
        items[0]["task"] == "T-007" and items[0]["answer"] == "use sqlite" and items[0]["remember"]
    )
    vault.inbox_close(cfg, repo, "T-007")
    assert not note.exists() and (note.parent / "answered" / "T-007.md").exists()
    # long answer under the section
    n2 = vault.inbox_write(cfg, repo, "T-008", "t", [], "b")
    assert n2
    n2.write_text(n2.read_text(encoding="utf-8") + "multi\nline answer\n", encoding="utf-8")
    assert vault.inbox_read(cfg, repo)[0]["answer"].startswith("multi")


def test_write_kit(tmp_path: Path) -> None:
    v, repo, cfg = _vault(tmp_path)
    written = vault.write_kit(cfg, repo)
    assert ".claude/commands/council-status.md" in written and "CLAUDE.md" in written
    assert vault.write_kit(cfg, repo).count("CLAUDE.md") == 0  # marker prevents duplicate block


def test_analyze_scan_python_repo(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n" * 10)
    (tmp_path / "tests" / "test_a.py").write_text("def test(): pass\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "db.yaml").write_text("host: x\n")
    a = analyze.scan(tmp_path)
    assert a.primary == "python" and a.has_tests and not a.has_ci and a.state == "greenfield"
    assert a.proposed_gates["before_review"] == ["uv run ruff check .", "uv run pytest -q"]
    assert "config/db.yaml" in a.sensitive_paths
    md = analyze.render(a, "x")
    assert "Proposed gates" in md and "uv run pytest -q" in md and "no CI detected" in md
    assert analyze.scan(tmp_path) == a  # deterministic
