"""The demo must exercise recovery deterministically without real configuration."""

from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import asdict
from pathlib import Path

import pytest

from driftwatch.config import Settings
from driftwatch.demo import DemoNetworkAttempt, _deny_network, main, run_demo


async def test_demo_recovers_partial_delivery_without_reanalysis_or_duplicate_acceptance() -> None:
    report = await run_demo()
    assert report.demonstration is True
    assert [step.name for step in report.steps] == [
        "baseline",
        "noise_ignored",
        "ai_failed",
        "partial_delivery",
        "delivery_recovered",
        "ai_disabled_delivery",
    ]
    assert report.steps[1].changes == 0
    assert report.steps[2].analysis_status == "error"
    assert report.steps[3].sent == ("first@example.invalid",)
    assert report.steps[3].pending == ("retry@example.invalid",)
    assert report.steps[4].notified and not report.steps[4].pending
    assert report.steps[5].analysis_status == "disabled"
    assert report.steps[5].scripted_ai_calls == 2
    assert report.ai_reservations == 2
    assert report.accepted_deliveries == {"first@example.invalid": 2, "retry@example.invalid": 2}


@pytest.mark.parametrize("source", ["environment", "dotenv"])
async def test_demo_ignores_application_configuration_and_is_repeatable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str
) -> None:
    # A worker token without a URL fails Settings validation, so the demo would
    # crash if it read either source.
    unpaired = "DRIFTWATCH_CAPTURE_WORKER_TOKEN"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(Settings.model_config, "env_file", ".env")
    if source == "environment":
        monkeypatch.setenv(unpaired, "unpaired-token")
    else:
        (tmp_path / ".env").write_text(f"{unpaired}=unpaired-token\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be configured together"):
        Settings()

    first, second = await run_demo(), await run_demo()

    assert asdict(first) == asdict(second)


async def test_demo_denies_dns_and_async_network_connections() -> None:
    with _deny_network():
        with pytest.raises(DemoNetworkAttempt):
            socket.getaddrinfo("example.invalid", 443)
        with pytest.raises(DemoNetworkAttempt):
            await asyncio.get_running_loop().create_connection(
                asyncio.Protocol, "example.invalid", 443
            )


def test_demo_command_emits_a_single_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--json"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["network"] == "denied"
    assert report["delivery"] == "scripted; no email provider or message"
    assert len(report["steps"]) == 6
