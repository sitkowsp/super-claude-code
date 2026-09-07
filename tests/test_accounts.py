from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest
from test_fallback import DoneAdapter, QuotaAdapter, repo  # noqa: F401 - fixture reuse

from council_mcp import cli, setup, stats
from council_mcp.adapters.base import RunHandle
from council_mcp.adapters.cli import executor_env
from council_mcp.config import CouncilConfig
from council_mcp.scheduler import Scheduler, parse_reset
from council_mcp.store import Task, TaskStore
from council_mcp.watcher import Watcher
from council_mcp.worktree import GitRepo


def test_parse_reset_variants() -> None:
    now = datetime(2026, 9, 7, 10, 0, 0)
    assert parse_reset("You've hit your limit · resets 3pm (Europe/Warsaw)", now) == now.replace(
        hour=15
    )
    assert parse_reset("usage limit reached, resets at 14:30", now) == now.replace(
        hour=14, minute=30
    )
    assert parse_reset("resets 9am", now) == now.replace(hour=9) + __import__("datetime").timedelta(
        days=1
    )
    assert parse_reset("limit resets in 45 min", now) == now.replace(minute=45)
    assert parse_reset("rate limit", now) is None


def test_add_profile_creates_alt_models_and_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup, "PROFILES_DIR", tmp_path / "profiles")
    cli.init(tmp_path, Path.cwd())
    out = setup.add_profile(tmp_path, "alt")
    assert out["profile"] == "alt" and "claude auth login" in out["login"]
    assert (tmp_path / "profiles" / "alt").is_dir()
    cfg = CouncilConfig.model_validate(
        json.loads((tmp_path / ".council" / "council.json").read_text(encoding="utf-8"))
    )
    assert set(out["models"].split(", ")) == {"fable-alt", "cheap-alt"}
    assert cfg.models["fable-alt"].profile == "alt" and not cfg.models["fable-alt"].enabled
    assert cfg.models["fable-alt"].config_dir == str(tmp_path / "profiles" / "alt")
    assert cfg.fallback.targets("fable") == ["fable-alt", "cheap"]
    assert cfg.fallback.targets("cheap") == ["cheap-alt"]
    assert (
        "cheap-alt" in cfg.routing.by_role["docs"]
        and "fable-alt" in cfg.routing.by_privacy["internal"]
    )
    with pytest.raises(ValueError):
        setup.add_profile(tmp_path, "default")
    assert executor_env(cfg.models["fable-alt"].config_dir)["CLAUDE_CONFIG_DIR"] == str(
        tmp_path / "profiles" / "alt"
    )
    assert (
        "CLAUDE_CONFIG_DIR" not in executor_env(None)
        or executor_env(None)["CLAUDE_CONFIG_DIR"] != ""
    )
    # login detection from the credentials file; verify enables the models
    assert setup.profile_logged_in(str(tmp_path / "profiles" / "alt")) is False
    (tmp_path / "profiles" / "alt" / ".credentials.json").write_text("{}")
    assert setup.profile_logged_in(str(tmp_path / "profiles" / "alt")) is True

    async def fake_status(argv, env, timeout=20):  # type: ignore[no-untyped-def]
        assert env.get("CLAUDE_CONFIG_DIR") or "auth" in argv
        return 0, '{"loggedIn": true, "email": "u@example.com", "orgName": "Org B"}'

    monkeypatch.setattr(setup, "_run_env", fake_status)
    monkeypatch.setattr(setup, "_which", lambda _c: "claude")  # CI runners have no claude on PATH
    rows = asyncio.run(setup.profiles_status(cfg, tmp_path))
    alt = [r for r in rows if r["profile"] == "alt"][0]
    assert alt["org"] == "Org B"
    assert alt["logged_in"] is True and set(alt["models"]) == {"fable-alt", "cheap-alt"}
    enabled = setup.enable_logged_in_profiles(tmp_path, rows)
    assert set(enabled) == {"fable-alt", "cheap-alt"}
    assert "alt" in setup.render_profiles(
        rows
    ) and "switch profile automatically" in setup.switch_hint(cfg, rows)
    assert set(setup.remove_profile(tmp_path, "alt")) == {"fable-alt", "cheap-alt"}
    cfg2 = CouncilConfig.model_validate(
        json.loads((tmp_path / ".council" / "council.json").read_text(encoding="utf-8"))
    )
    assert "alt" not in cfg2.claude_profiles and cfg2.fallback.targets("fable") == ["cheap"]


def test_config_rejects_unknown_profile_or_chain(template_cfg: CouncilConfig) -> None:
    data = template_cfg.model_dump()
    data["models"]["fable"]["profile"] = "ghost"
    with pytest.raises(ValueError):
        CouncilConfig.model_validate(data)
    data["models"]["fable"]["profile"] = None
    data["fallback"]["by_model"] = {"fable": ["nope"]}
    with pytest.raises(ValueError):
        CouncilConfig.model_validate(data)


class QuotaWithReset(QuotaAdapter):
    async def run(self, task: Task, workdir: Path, budget, resume: bool) -> RunHandle:  # type: ignore[no-untyped-def]
        h = await super().run(task, workdir, budget, resume)
        assert h.log_path
        h.log_path.write_text(
            "Claude usage limit reached. Your limit resets 11pm (Europe/Warsaw).\n"
        )
        return h


async def test_quota_on_fable_moves_task_to_fable_alt_with_reset_cooldown(
    repo: Path,  # noqa: F811 - fixture imported from test_fallback
    template_cfg: CouncilConfig,
) -> None:
    """Simulated second account: fable (default profile) hits its limit → the same executor on
    the alternate profile (fable-alt) finishes the task; fable's cooldown ends at the reset time."""
    data = template_cfg.model_dump()
    data["claude_profiles"]["alt"] = str(repo / "alt-profile")
    data["models"]["fable"]["enabled"] = True
    data["models"]["fable-alt"] = {**data["models"]["fable"], "profile": "alt"}
    data["routing"]["by_privacy"]["public"].append("fable-alt")
    data["routing"]["by_role"]["implement"].append("fable-alt")
    data["fallback"]["by_model"] = {"fable": ["fable-alt", "codex"]}
    data["chair"]["coder"] = "fable"
    data["models"]["local"]["enabled"] = False
    cfg = CouncilConfig.model_validate(data)
    assert cfg.models["fable-alt"].config_dir == str(repo / "alt-profile")
    store = TaskStore(repo)
    git = GitRepo(repo)
    w = Watcher(store, git, interval_s=0.05)
    w.start()
    s = Scheduler(cfg, store, git, w, repo)
    s.adapters["fable"] = QuotaWithReset("fable", repo)  # type: ignore[assignment]
    s.adapters["fable-alt"] = DoneAdapter("fable-alt")  # type: ignore[assignment]
    store.save(
        Task(id="T-001", title="t", role="implement", privacy="public", goal="g", scope=["src/"])
    )
    assert s.pick_model(store.get("T-001")) == "fable"  # coder=fable goes first
    s.dispatch(["T-001"])
    await asyncio.wait_for(s.jobs["T-001"], 10)
    for _ in range(100):
        if store.get("T-001").state == "review":
            break
        await asyncio.sleep(0.1)
    if "T-001" in s.jobs and not s.jobs["T-001"].done():
        await asyncio.wait_for(s.jobs["T-001"], 10)
    t = store.get("T-001")
    assert t.state == "review" and t.assigned_to == "fable-alt" and t.fallbacks == 1
    st = stats.load(repo)
    until = st.models["fable"].cooldown_until
    assert until and until.endswith("+00:00")
    # cooldown taken from the "resets 11pm" text, not the 60-minute default
    assert datetime.fromisoformat(until).astimezone().hour == 23
    assert s.pick_fallback("fable", "public") == "fable-alt"
    w.stop()
