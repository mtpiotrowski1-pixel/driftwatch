"""Deterministic offline tour of Driftwatch's real monitoring and delivery core.

Every external boundary is visibly scripted. An isolated temporary SQLite
schema and an explicit network denial guard keep this command separate from
real settings, API keys, monitored sites, and email providers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import socket
from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from sqlalchemy import func, select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import (
    AnalysisMode,
    AnalysisStatus,
    EmailChannelName,
    NotificationDeliveryStatus,
)
from driftwatch.models import (
    AnalysisRun,
    ChangeEvent,
    NotificationDelivery,
    NotificationOutbox,
    Organization,
    Recipient,
    Site,
    Snapshot,
)
from driftwatch.monitoring.analyzer import Analysis, AnalysisError
from driftwatch.monitoring.capture import CapturedPage
from driftwatch.monitoring.pipeline import CheckStatus
from driftwatch.monitoring.usage import CostEstimate, TokenUsage
from driftwatch.notifications.email import EmailEnvelope, SendError
from driftwatch.runner import RunResult, SiteRunner

_URL = "https://demo.invalid/pricing"
_RETRY_ADDRESS = "retry@example.invalid"


class DemoNetworkAttempt(RuntimeError):
    """The offline demonstration attempted to leave its isolation boundary."""


@contextmanager
def _deny_network() -> Iterator[None]:
    def deny(*_: Any, **__: Any) -> Any:
        raise DemoNetworkAttempt("Offline demo forbids network connections and DNS")

    async def deny_async(*_: Any, **__: Any) -> Any:
        return deny()

    loop = asyncio.get_running_loop()
    with ExitStack() as stack:
        for name in ("getaddrinfo", "create_connection"):
            stack.enter_context(patch.object(socket, name, deny))
        for name in ("connect", "connect_ex", "sendto"):
            stack.enter_context(patch.object(socket.socket, name, deny))
        # On Windows the proactor may connect via IOCP, bypassing socket.connect.
        for name in ("create_connection", "create_datagram_endpoint"):
            stack.enter_context(patch.object(loop, name, deny_async))
        yield


class DemoCapturer:
    def __init__(self) -> None:
        self.price = 10
        self.noise = "first-request"

    async def capture(self, **_: Any) -> CapturedPage:
        return CapturedPage(
            f'<div data-request-id="{self.noise}">'
            f"<span>Basic</span><span>{self.price}</span></div>",
            _URL,
        )


class DemoAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(
        self, *, diff_text: str, url: str, system_prompt: str, model: str
    ) -> Analysis:
        self.calls += 1
        if self.calls == 1:
            raise AnalysisError("DEMO: scripted AI provider failure")
        return Analysis(
            significant=True,
            headline="DEMO: the Basic price changed",
            summary="Scripted verdict for this demonstration; no AI service was contacted.",
            cost=CostEstimate(model=model, usage=TokenUsage(), cost_usd=0.0),
        )


class DemoDeliveryChannel:
    name = EmailChannelName.LOG

    def __init__(self) -> None:
        self.attempts: Counter[str] = Counter()
        self.accepted: Counter[str] = Counter()

    async def send(self, envelope: EmailEnvelope) -> str:
        self.attempts[envelope.to] += 1
        if envelope.to == _RETRY_ADDRESS and self.attempts[envelope.to] == 1:
            raise SendError("DEMO: scripted recipient delivery failure")
        self.accepted[envelope.to] += 1
        return f"demo-accepted-{sum(self.accepted.values())}"


@dataclass(frozen=True, slots=True)
class DemoStep:
    name: str
    capture_status: str
    change_id: int | None
    analysis_status: str | None
    notified: bool
    sent: tuple[str, ...]
    pending: tuple[str, ...]
    snapshots: int
    changes: int
    analysis_runs: int
    scripted_ai_calls: int


@dataclass(frozen=True, slots=True)
class DemoReport:
    demonstration: bool
    network: str
    database: str
    ai: str
    delivery: str
    steps: tuple[DemoStep, ...]
    accepted_deliveries: dict[str, int]
    ai_reservations: int


async def _record(
    name: str, result: RunResult, database: Database, analyzer: DemoAnalyzer
) -> DemoStep:
    async with database.session() as session:
        change = await session.get(ChangeEvent, result.change_id) if result.change_id else None
        deliveries = (
            await session.scalars(
                select(NotificationDelivery)
                .join(NotificationOutbox)
                .where(NotificationOutbox.change_id == result.change_id)
                .order_by(NotificationDelivery.destination_label)
            )
        ).all()
        return DemoStep(
            name=name,
            capture_status=str(result.status),
            change_id=result.change_id,
            analysis_status=str(change.analysis_status) if change else None,
            notified=change.notified_at is not None if change else False,
            sent=tuple(
                row.destination_label
                for row in deliveries
                if row.status == NotificationDeliveryStatus.SENT
            ),
            pending=tuple(
                row.destination_label
                for row in deliveries
                if row.status != NotificationDeliveryStatus.SENT
            ),
            snapshots=int(await session.scalar(select(func.count()).select_from(Snapshot)) or 0),
            changes=int(await session.scalar(select(func.count()).select_from(ChangeEvent)) or 0),
            analysis_runs=int(
                await session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
            ),
            scripted_ai_calls=analyzer.calls,
        )


async def _seed(database: Database) -> tuple[int, int]:
    async with database.session() as session:
        org = Organization(name="Offline demonstration", monthly_ai_check_limit=20)
        session.add(org)
        await session.flush()
        site = Site(
            organization_id=org.id,
            name="DEMO prices",
            url=_URL,
            recipients=[
                Recipient(organization_id=org.id, email="first@example.invalid"),
                Recipient(organization_id=org.id, email=_RETRY_ADDRESS),
            ],
        )
        session.add(site)
        await session.flush()
        ids = org.id, site.id
        await session.commit()
        return ids


async def _scenario(database: Database, settings: Settings) -> DemoReport:
    org_id, site_id = await _seed(database)
    capturer, analyzer, channel = DemoCapturer(), DemoAnalyzer(), DemoDeliveryChannel()
    runner = SiteRunner(database, capturer, settings, analyzer=analyzer, channel=channel)
    steps: list[DemoStep] = []

    steps.append(await _record("baseline", await runner.run(site_id), database, analyzer))
    capturer.noise = "second-request"
    steps.append(await _record("noise_ignored", await runner.run(site_id), database, analyzer))
    capturer.price = 20
    failed = await runner.run(site_id)
    steps.append(await _record("ai_failed", failed, database, analyzer))
    if failed.change_id is None:
        raise RuntimeError("Demo contract failed: price change did not create an event")
    analyzed = await runner.reprocess_change(failed.change_id)
    steps.append(await _record("partial_delivery", analyzed, database, analyzer))
    delivered = await runner.reprocess_change(failed.change_id, force_delivery=True)
    steps.append(await _record("delivery_recovered", delivered, database, analyzer))

    async with database.session() as session:
        site = await session.get(Site, site_id)
        if site is None:
            raise RuntimeError("Demo site disappeared")
        site.analysis_mode = AnalysisMode.DISABLED
        await session.commit()
    capturer.price = 25
    steps.append(
        await _record("ai_disabled_delivery", await runner.run(site_id), database, analyzer)
    )
    async with database.session() as session:
        org = await session.get(Organization, org_id)
        if org is None:
            raise RuntimeError("Demo organization disappeared")
        reservations = org.ai_checks_reserved

    report = DemoReport(
        demonstration=True,
        network="denied",
        database="isolated temporary SQLite; removed after the run",
        ai="scripted; no OpenAI request or charge",
        delivery="scripted; no email provider or message",
        steps=tuple(steps),
        accepted_deliveries=dict(sorted(channel.accepted.items())),
        ai_reservations=reservations,
    )
    _require_expected_outcomes(report)
    return report


def _require_expected_outcomes(report: DemoReport) -> None:
    baseline, noise, failed, partial, recovered, disabled = report.steps
    expectations = (
        baseline.capture_status == CheckStatus.BASELINE and baseline.changes == 0,
        noise.capture_status == CheckStatus.UNCHANGED and noise.snapshots == 1,
        failed.analysis_status == AnalysisStatus.ERROR and not failed.notified,
        partial.analysis_status == AnalysisStatus.SUCCEEDED
        and len(partial.sent) == len(partial.pending) == 1,
        recovered.notified and len(recovered.sent) == 2 and not recovered.pending,
        recovered.scripted_ai_calls == partial.scripted_ai_calls == 2,
        disabled.analysis_status == AnalysisStatus.DISABLED and disabled.notified,
        disabled.scripted_ai_calls == 2 and disabled.analysis_runs == 1,
        report.ai_reservations == 2,
        all(count == 2 for count in report.accepted_deliveries.values()),
    )
    if not all(expectations):
        raise RuntimeError("Offline demo failed its behavioral contract; inspect the real scenario")


async def run_demo() -> DemoReport:
    """Run the deterministic scenario without loading normal application settings."""
    with TemporaryDirectory(prefix="driftwatch-demo-") as temporary:
        directory = Path(temporary)
        settings = Settings(
            _env_file=None,
            _env_prefix="DRIFTWATCH_INTERNAL_OFFLINE_DEMO_",
            host="127.0.0.1",
            base_url="http://localhost:8000",
            data_dir=directory,
            database_url=f"sqlite+aiosqlite:///{(directory / 'demo.db').as_posix()}",
            session_secret_key=secrets.token_urlsafe(32),
            encryption_key=secrets.token_urlsafe(32),
            run_migrations=False,
            picker_enabled=False,
            capture_allow_in_process=True,
            openai_model="demo-scripted",
        )
        database = Database(settings.database_url)
        try:
            with _deny_network():
                # This is a disposable model-schema fixture, not an installation
                # or migration smoke. Production startup uses Alembic migrations.
                await database.create_all()
                return await _scenario(database, settings)
        finally:
            await database.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Driftwatch's deterministic offline DEMO")
    parser.add_argument(
        "--json", action="store_true", help="Print a machine-readable scenario report"
    )
    args = parser.parse_args(argv)
    report = asyncio.run(run_demo())
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    else:
        print("DEMO — scripted capture, AI and delivery; network disabled; temporary database")
        for step in report.steps:
            print(
                f"  {step.name}: {step.capture_status}, analysis={step.analysis_status or '—'}, "
                f"sent={len(step.sent)}, pending={len(step.pending)}, "
                f"notified={step.notified}, AI calls={step.scripted_ai_calls}"
            )
        print(
            "Verified: delivery retries reuse the verdict; AI-disabled monitoring delivers changes."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
