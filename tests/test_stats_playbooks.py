from __future__ import annotations

from pathlib import Path

import pytest

from council_mcp import playbooks, stats


def test_trust_promotes_after_first_pass_oks() -> None:
    s = stats.Stats()
    pol = stats.TrustPolicy(promote_after=2)
    assert stats.on_verdict(s, "codex", True, 1, pol) == ("probation", "probation", None)
    old, new, why = stats.on_verdict(s, "codex", True, 1, pol)
    assert (old, new) == ("probation", "standard") and "first-pass" in (why or "")
    stats.on_verdict(s, "codex", True, 2, pol)  # attempt 2 does not count as first-pass
    assert s.models["codex"].first_pass_ok == 0
    stats.on_verdict(s, "codex", True, 1, pol)
    stats.on_verdict(s, "codex", True, 1, pol)
    assert s.models["codex"].trust == "trusted"


def test_trust_demotes_after_consecutive_rejects_and_defect() -> None:
    s = stats.Stats()
    s.get("gemini").trust = "trusted"
    pol = stats.TrustPolicy(demote_after=2)
    stats.on_verdict(s, "gemini", False, 1, pol)
    assert s.models["gemini"].trust == "trusted"
    old, new, why = stats.on_verdict(s, "gemini", False, 2, pol)
    assert (old, new) == ("trusted", "standard") and "consecutive" in (why or "")
    assert stats.on_defect(s, "gemini", pol) == ("standard", "probation")
    assert s.models["gemini"].defects_after_merge == 1
    assert stats.on_defect(s, "gemini", pol) == ("probation", "probation")


def test_stats_roundtrip_and_lessons(tmp_path: Path) -> None:
    s = stats.Stats()
    s.get("codex").tasks = 3
    stats.save(tmp_path, s)
    assert stats.load(tmp_path).models["codex"].tasks == 3
    stats.add_lesson(
        tmp_path, "codex", "implement", "add return types in tests under mypy --strict"
    )
    stats.add_lesson(tmp_path, "codex", "docs", "docs lesson")
    stats.add_lesson(tmp_path, "codex", "*", "always run ruff")
    assert stats.lessons_for(tmp_path, "codex", "implement") == [
        "add return types in tests under mypy --strict",
        "always run ruff",
    ]
    assert stats.lessons_for(tmp_path, "gemini", "implement") == []
    assert "| codex | probation | 3 |" in stats.summary(s)


def test_diff_lines() -> None:
    assert (
        stats.diff_lines(
            " a.py | 4 ++++\n b.py | 9 +++++----\n"
            " 2 files changed, 10 insertions(+), 3 deletions(-)\n"
        )
        == 13
    )
    assert stats.diff_lines("") == 0


def test_playbook_selection(tmp_path: Path) -> None:
    books = playbooks.load_all(tmp_path)
    assert {"feature", "bug-hunt", "data-internal"} <= set(books)
    pb, why = playbooks.select("users report a crash when the export fails", books)
    assert pb.name == "bug-hunt" and "crash" in why
    pb, _ = playbooks.select("monthly sales report from the database", books)
    assert pb.name == "data-internal"
    pb, why = playbooks.select("refactor the logging module", books)
    assert pb.name == "feature" and "default" in why
    pb, why = playbooks.select("anything", books, forced="bug-hunt")
    assert pb.name == "bug-hunt" and why == "forced by user"
    with pytest.raises(KeyError):
        playbooks.select("x", books, forced="nope")


def test_user_playbook_overrides_shipped(tmp_path: Path) -> None:
    d = tmp_path / ".council" / "playbooks"
    d.mkdir(parents=True)
    (d / "feature.json").write_text(
        '{"name": "feature", "description": "mine", "trigger": ["zzz"], "waves": []}',
        encoding="utf-8",
    )
    books = playbooks.load_all(tmp_path)
    assert books["feature"].source == "user" and books["feature"].description == "mine"
