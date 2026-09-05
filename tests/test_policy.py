from __future__ import annotations

from pathlib import Path

from council_mcp import policy


def test_decide_rules() -> None:
    p = policy.DelegationPolicy()
    c = ["codex", "copilot"]
    assert policy.decide(p, "docs", 5, 1, False, "public", c).verdict == "delegate"
    assert policy.decide(p, "implement", 120, 3, False, "public", c).verdict == "delegate"
    r = policy.decide(p, "implement", 120, 3, True, "public", c)
    assert r.verdict == "self" and "seams" in r.reason
    assert policy.decide(p, "implement", 8, 1, False, "public", c).verdict == "self"
    assert policy.decide(p, "implement", 30, 1, False, "public", c).verdict == "ask"
    assert policy.decide(p, "implement", 120, 3, False, "local-only", []).verdict == "self"
    p.mode = "ask"
    assert policy.decide(p, "docs", 5, 1, False, "public", c).verdict == "ask"
    p.mode = "off"
    assert policy.decide(p, "docs", 500, 9, False, "public", c).verdict == "self"


def test_budget_hint_and_session_clock(tmp_path: Path) -> None:
    p = policy.DelegationPolicy(session_budget_minutes=300, warn_after_minutes=210)
    assert policy.budget_hint(p, 100) is None
    hint = policy.budget_hint(p, 250)
    assert hint and "~50 min" in hint and "offload" in hint
    assert policy.session_minutes(tmp_path) == 0
    assert (tmp_path / ".council" / ".session_started").exists()
    policy.reset_session(tmp_path)
    assert not (tmp_path / ".council" / ".session_started").exists()


def test_reminder() -> None:
    p = policy.DelegationPolicy()
    assert policy.reminder(p, []) == ""
    text = policy.reminder(p, ["codex", "local"])
    assert "≥40 lines" in text and "codex, local" in text and "ask the user only" in text
    p.mode = "ask"
    assert "confirm before delegating" in policy.reminder(p, ["codex"])
