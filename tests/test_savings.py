from __future__ import annotations

from pathlib import Path

from council_mcp import cli, obsidian, stats
from council_mcp.store import Task, TaskStore


def test_estimate_and_on_merge_counts_once() -> None:
    assert stats.estimate_saved("implement", 100) == 1500 + 6000
    assert stats.estimate_saved("assets", 0) == 2500
    assert stats.estimate_saved("unknown-role", 10) == 1000 + 400
    s = stats.Stats()
    assert stats.on_merge(s, "T-001", "codex", "implement", 50, "probation") == 4500
    assert stats.on_merge(s, "T-001", "codex", "implement", 50, "probation") == 0  # once
    assert stats.on_merge(s, "T-002", "copilot", "docs", 20, "probation") == 800 + 800
    stats.on_assist(s, "plan_draft")
    stats.on_assist(s, "review_assist")
    sv = stats.savings_summary(s)
    assert sv["tokens_saved_est"] == 4500 + 1600 + 3000 + 800
    assert sv["tasks_counted"] == 2 and sv["lines_merged"] == 70
    assert sv["per_model"]["codex"]["tokens_saved_est"] == 4500
    md = stats.savings_md(s)
    assert "9,900 Claude tokens saved" in md and "| codex | 0 | 50 | 4,500 |" in md
    assert "assistants" in md and "heuristic" in md


def test_report_and_mirror_carry_savings(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    store = TaskStore(tmp_path)
    store.save(
        Task(
            id="T-001",
            title="x",
            role="implement",
            privacy="public",
            goal="g",
            scope=["a/"],
            assigned_to="codex",
        )
    )
    s = stats.Stats()
    stats.on_merge(s, "T-001", "codex", "implement", 10, "probation")
    stats.save(tmp_path, s)
    text = cli.report(tmp_path)
    assert "## Estimated Claude tokens saved" in text and "2,100 Claude tokens saved" in text
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / ".council").mkdir(parents=True)
    stats.save(repo, s)
    TaskStore(repo)
    target = obsidian.mirror(repo, obsidian.ObsidianConfig(vault=str(vault), folder="Council"))
    assert target is not None
    note = (target / "Savings.md").read_text(encoding="utf-8")
    assert note.startswith("---\ncouncil_savings: true") and "tokens_saved: 2100" in note
