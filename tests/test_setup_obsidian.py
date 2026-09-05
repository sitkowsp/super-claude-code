from __future__ import annotations

import json
from pathlib import Path

import pytest

from council_mcp import obsidian, setup
from council_mcp.config import CouncilConfig
from council_mcp.store import Task, TaskStore


async def test_check_all_reports_missing_and_actions(
    template_cfg: CouncilConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    for m in template_cfg.models.values():
        if m.cmd:
            m.cmd = "definitely-not-a-real-cli-xyz"
    checks = await setup.check_all(template_cfg)
    by = {c.model: c for c in checks}
    assert not by["codex"].installed and by["codex"].action.startswith(
        "install: npm i -g @openai/codex"
    )
    assert by["local"].adapter == "ollama"
    table = setup.render(checks)
    assert "| codex | codex | NO |" in table
    assert "executors ready" in setup.brief(checks)
    cmds = await setup.install_missing(template_cfg, dry_run=True)
    assert any("@openai/codex" in c for c in cmds) and any("@github/copilot" in c for c in cmds)


def test_detect_vaults_and_resolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(obsidian.ENV_VAULT, raising=False)  # the developer's machine may set it
    vault = tmp_path / "Vault"
    (vault / ".obsidian" / "plugins" / "claudian").mkdir(parents=True)
    repo = vault / "code" / "proj"
    repo.mkdir(parents=True)
    other = tmp_path / "Other"
    other.mkdir()
    cfgfile = tmp_path / "obsidian.json"
    cfgfile.write_text(
        json.dumps(
            {
                "vaults": {
                    "a": {"path": str(other), "ts": 2, "open": True},
                    "b": {"path": str(vault), "ts": 1},
                }
            }
        )
    )
    monkeypatch.setattr(obsidian, "config_file", lambda: cfgfile)
    vaults = obsidian.detect_vaults()
    assert [v["path"] for v in vaults] == [str(other), str(vault)]  # open first
    cfg = obsidian.ObsidianConfig()
    assert obsidian.resolve_vault(cfg, repo) == vault  # repo inside vault wins over open vault
    assert obsidian.resolve_vault(cfg, tmp_path / "elsewhere") == other
    assert obsidian.has_claudian(vault) and not obsidian.has_claudian(other)
    st = obsidian.status(cfg, repo)
    assert st["repo_inside_vault"] and st["claudian"]
    monkeypatch.setenv(obsidian.ENV_VAULT, str(other))
    assert obsidian.resolve_vault(cfg, repo) == other  # env default beats the containing vault
    monkeypatch.delenv(obsidian.ENV_VAULT)


def test_mirror_writes_notes_with_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / ".council").mkdir(parents=True)
    (repo / ".council" / "MEMORY.md").write_text("# mem\n")
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
    target = obsidian.mirror(repo, cfg)
    assert target == vault / "Council" / "repo"
    note = (target / "tasks" / "T-001.md").read_text(encoding="utf-8")
    assert note.startswith('---\ncouncil_task: "T-001"') and 'state: "queued"' in note
    assert (target / "MEMORY.md").read_text() == "# mem\n"
    assert "dataview" in (target / "README.md").read_text(encoding="utf-8")
    cfg.mirror = False
    assert obsidian.mirror(repo, cfg) is None
