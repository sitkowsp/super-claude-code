from __future__ import annotations

from pathlib import Path

from council_mcp import obsidian


def _note(vault: Path, proj: str, tid: str, state: str) -> None:
    d = vault / "Council" / proj / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tid}.md").write_text(
        f'---\ncouncil_task: "{tid}"\nstate: "{state}"\n---\n', encoding="utf-8"
    )


def test_update_dashboard_upserts_block_and_keeps_user_content(tmp_path: Path) -> None:
    vault = tmp_path / "V"
    (vault / ".obsidian").mkdir(parents=True)
    _note(vault, "alpha", "T-001", "review")
    _note(vault, "alpha", "T-002", "failed")
    _note(vault, "beta", "T-001", "merged")
    (vault / "Council" / "beta" / "Savings.md").write_text(
        "---\ncouncil_savings: true\ntokens_saved: 12345\n---\n", encoding="utf-8"
    )
    dash = obsidian.update_dashboard(vault, "Council")
    assert dash is not None
    text = dash.read_text(encoding="utf-8")
    assert text.count(obsidian.DASH_START) == 1
    assert "| [[Council/alpha/README\\|alpha]] | 0 | 0 | 0 | 1 | 0 | 1 | - |" in text.replace(
        "\\|", "\\|"
    )
    assert "12,345" in text and "Council status (auto)" in text
    # user content survives, block is replaced not duplicated
    dash.write_text("# My stuff\n\nkeep me\n\n" + text, encoding="utf-8")
    _note(vault, "alpha", "T-003", "merged")
    obsidian.update_dashboard(vault, "Council")
    text2 = dash.read_text(encoding="utf-8")
    assert text2.count(obsidian.DASH_START) == 1 and "keep me" in text2
    assert "| 0 | 0 | 0 | 1 | 1 | 1 |" in text2  # alpha now has a merged task


def test_mirror_writes_dashboard(tmp_path: Path) -> None:
    from council_mcp.store import Task, TaskStore

    vault = tmp_path / "V"
    (vault / ".obsidian").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / ".council").mkdir(parents=True)
    store = TaskStore(repo)
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
    cfg = obsidian.ObsidianConfig(vault=str(vault), folder="Council")
    assert obsidian.mirror(repo, cfg) is not None
    assert (vault / "Dashboard.md").exists()
    assert "| 1 | 0 | 0 | 0 | 0 | 0 |" in (vault / "Dashboard.md").read_text(encoding="utf-8")
