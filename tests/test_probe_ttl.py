"""Daily availability refresh (probe_ttl_hours) + CLI model/effort discovery."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from council_mcp import probe
from council_mcp.adapters.base import Capabilities
from council_mcp.adapters.cli import CliAdapter, parse_model_list
from council_mcp.config import CouncilConfig, ModelConfig


def _caps(age_hours: float, enabled: dict[str, bool] | None = None) -> probe.CapabilitiesFile:
    ts = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat(timespec="seconds")
    models = {
        n: Capabilities(name=n, adapter="codex", enabled=e) for n, e in (enabled or {}).items()
    }
    return probe.CapabilitiesFile(probed_at=ts, models=models)


def test_is_fresh_ttl() -> None:
    assert probe.is_fresh(_caps(1), 24)
    assert not probe.is_fresh(_caps(25), 24)
    assert probe.is_fresh(_caps(9999), 0)  # ttl 0 = never auto-refresh
    corrupt = probe.CapabilitiesFile(probed_at="not-a-date")
    assert not probe.is_fresh(corrupt, 24)
    assert probe.is_fresh(corrupt, 0)


def test_load_missing_and_corrupt(tmp_path: Path) -> None:
    assert probe.load(tmp_path) is None
    p = tmp_path / ".council" / "capabilities.json"
    p.parent.mkdir(parents=True)
    p.write_text("{broken", encoding="utf-8")
    assert probe.load(tmp_path) is None


async def test_ensure_fresh_keeps_fresh_memory(
    template_cfg: CouncilConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(cfg: CouncilConfig) -> probe.CapabilitiesFile:
        raise AssertionError("must not probe while the in-memory copy is fresh")

    monkeypatch.setattr(probe, "probe_all", boom)
    cur = _caps(1)
    got, reprobed = await probe.ensure_fresh(template_cfg, tmp_path, cur)
    assert got is cur and not reprobed


async def test_ensure_fresh_trusts_fresh_file(
    template_cfg: CouncilConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(cfg: CouncilConfig) -> probe.CapabilitiesFile:
        raise AssertionError("must not probe while the on-disk copy is fresh")

    monkeypatch.setattr(probe, "probe_all", boom)
    disk = _caps(2, {"codex": False})
    probe.write(disk, tmp_path)
    assert template_cfg.models["codex"].enabled
    got, reprobed = await probe.ensure_fresh(template_cfg, tmp_path, None)
    assert not reprobed and got.probed_at == disk.probed_at
    assert template_cfg.models["codex"].enabled is False  # the file's verdict is applied


async def test_ensure_fresh_reprobes_stale_and_restores_enabled(
    template_cfg: CouncilConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    persisted = template_cfg.model_copy(deep=True)  # council.json still says codex enabled
    probe.write(_caps(30, {"codex": False}), tmp_path)  # yesterday's probe: codex down
    template_cfg.models["codex"].enabled = False
    seen: list[bool] = []

    async def fake(cfg: CouncilConfig) -> probe.CapabilitiesFile:
        seen.append(cfg.models["codex"].enabled)  # restored from council.json before probing
        return _caps(0, {"codex": True})

    monkeypatch.setattr(probe, "probe_all", fake)
    monkeypatch.setattr("council_mcp.config.load", lambda root=None: persisted)
    got, reprobed = await probe.ensure_fresh(template_cfg, tmp_path, None)
    assert reprobed and seen == [True]
    on_disk = probe.load(tmp_path)
    assert on_disk is not None and on_disk.probed_at == got.probed_at  # file rewritten


def test_parse_model_list() -> None:
    text = (
        "Available models:\n\n"
        "gpt-6-astra   1M context\n"
        "  gpt-5.1-codex\n"
        "- legacy-1 deprecated\n"
        "--verbose\n"
        "NAME\n"
        "usage: codex models\n"
        "qwen3-coder:30b\n"
        "gpt-6-astra\n"
    )
    assert parse_model_list(text) == ["gpt-6-astra", "gpt-5.1-codex", "qwen3-coder:30b"]


async def test_codex_probe_reports_efforts_and_silent_discovery() -> None:
    # `python` stands in for the codex CLI: `python models [list]` exits non-zero, so discovery
    # stays silent and the configured model remains authoritative; the effort registry is static.
    a = CliAdapter("codex", ModelConfig(adapter="codex", cmd=sys.executable))
    caps = await a.probe()
    assert caps.enabled
    assert caps.efforts == ["low", "medium", "high", "xhigh", "max"]
    assert caps.models == []
