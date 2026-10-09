"""Shared fixtures and test doubles.

The doubles let the full stack run without a browser, an OpenAI key, or a mail
server: a scripted capturer returns canned HTML, a stub analyzer returns a fixed
verdict (or raises), and a recording channel captures outbound mail.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import driftwatch.security.urls as urls
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import EmailChannelName
from driftwatch.exceptions import NotFoundError
from driftwatch.models import Organization, User
from driftwatch.monitoring.analyzer import Analysis, AnalysisError
from driftwatch.monitoring.picker import (
    PickerCapabilities,
    PickerMode,
    PickerResult,
    PickerState,
    PickerStatus,
    PickerUnavailable,
)
from driftwatch.monitoring.usage import CostEstimate, TokenUsage
from driftwatch.notifications.email import EmailEnvelope, SendError
from driftwatch.security.passwords import ahash_password


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve hostnames to a fixed public IP so the suite stays offline while
    still exercising the real SSRF validation (literal/private IPs keep their
    real behavior, so the reject cases still reject)."""

    async def fake_resolve(host: str) -> list[urls.IpAddress]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(urls, "_resolve", fake_resolve)


class ScriptedCapturer:
    """Returns queued HTML responses, then a fixed fallback.

    ``queue`` is public so a test can stage successive page versions on the same
    instance that was injected into the application.
    """

    def __init__(self, *, queue: list[str] | None = None, html: str = "") -> None:
        self.queue = list(queue or [])
        self.fallback = html
        self.calls: list[str] = []
        self.interaction_calls: list[list[dict[str, object]]] = []

    async def capture(
        self,
        *,
        url: str,
        css_selector: str | None = None,
        interaction_steps: list[dict[str, object]] | None = None,
        **_: object,
    ) -> str:
        self.calls.append(url)
        self.interaction_calls.append(interaction_steps or [])
        if self.queue:
            return self.queue.pop(0)
        return self.fallback


class StubAnalyzer:
    def __init__(
        self,
        *,
        significant: bool = True,
        headline: str = "Headline",
        summary: str = "Summary",
        error: str | None = None,
    ) -> None:
        self._significant = significant
        self._headline = headline
        self._summary = summary
        self._error = error
        self.calls: list[str] = []

    async def analyze(
        self, *, diff_text: str, url: str, system_prompt: str, model: str
    ) -> Analysis:
        self.calls.append(system_prompt)
        if self._error is not None:
            raise AnalysisError(self._error)
        return Analysis(
            significant=self._significant,
            headline=self._headline,
            summary=self._summary,
            cost=CostEstimate(model, TokenUsage(40, 12), 0.0001),
        )


class RecordingChannel:
    name = EmailChannelName.LOG

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.sent: list[EmailEnvelope] = []

    async def send(self, envelope: EmailEnvelope) -> str:
        if self._fail:
            raise SendError("simulated failure")
        self.sent.append(envelope)
        return f"msg-{len(self.sent)}"


class FakePicker:
    """Stand-in for PickerManager — no browser. Saves immediately on start."""

    _SESSION = "fake-session"

    def __init__(self) -> None:
        self.available = True
        self._mode = PickerMode.SELECT
        self._owner = 0

    async def capabilities(self) -> PickerCapabilities:
        if self.available:
            return PickerCapabilities(available=True)
        return PickerCapabilities(available=False, reason="The visual picker is disabled.")

    async def start(self, *, url: str, mode: PickerMode, owner_user_id: int) -> PickerStatus:
        if not self.available:
            raise PickerUnavailable("The visual picker is disabled.")
        self._mode = mode
        self._owner = owner_user_id
        return self._status()

    async def status(self, session_id: str, *, requester_id: int) -> PickerStatus:
        self._require(session_id, requester_id)
        return self._status()

    async def result(self, session_id: str, *, requester_id: int) -> PickerResult:
        self._require(session_id, requester_id)
        return PickerResult(selectors=["main .price"], steps=[])

    async def cancel(self, session_id: str, *, requester_id: int) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def _status(self) -> PickerStatus:
        return PickerStatus(
            session_id=self._SESSION,
            state=PickerState.SAVED,
            mode=self._mode,
            selector_count=1,
            step_count=0,
            channel="chromium",
        )

    def _require(self, session_id: str, requester_id: int) -> None:
        if session_id != self._SESSION or requester_id != self._owner:
            raise NotFoundError(f"picker session {session_id} not found")


async def create_org(session: AsyncSession, name: str = "Test") -> int:
    """Create an organization in the given session and return its id.

    Tests that build Project/Site/Recipient rows directly need an org to satisfy
    the NOT NULL organization_id FK. Flushes so the id is available immediately.
    """
    org = Organization(name=name)
    session.add(org)
    await session.flush()
    return org.id


async def set_test_user_password(
    database: Database,
    email: str,
    password: str = "password123",
) -> None:
    """Assign a known credential only inside an isolated test database.

    Product tests outside the invitation flow sometimes need to switch identities.
    Keeping that setup at the persistence boundary prevents them from reintroducing
    an administrator-controlled password into the production user API.
    """
    async with database.session() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        user.password_hash = await ahash_password(password)
        await session.commit()


@pytest.fixture
def picker() -> FakePicker:
    return FakePicker()


@pytest.fixture
def settings(tmp_path: object) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        secret_key="test-secret-key-0123456789-abcdef",
        scheduler_enabled=False,
        run_migrations=True,
        base_url="http://localhost:8000",
        # These multi-user API fixtures deliberately exercise optional open
        # registration. The shipped default closes signup after the first owner.
        public_registration_enabled=True,
    )


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database(settings.database_url)
    await db.upgrade()
    yield db
    await db.dispose()


@pytest.fixture
def capturer() -> ScriptedCapturer:
    # Ordinary API fixtures represent a successful, nonempty observation.
    # Missing-capture regressions construct an explicitly empty double.
    return ScriptedCapturer(html="<main><p>Owned test baseline</p></main>")


@pytest.fixture
def analyzer() -> StubAnalyzer:
    return StubAnalyzer()


@pytest.fixture
def channel() -> RecordingChannel:
    return RecordingChannel()


@pytest_asyncio.fixture
async def client(
    settings: Settings,
    capturer: ScriptedCapturer,
    analyzer: StubAnalyzer,
    channel: RecordingChannel,
    picker: FakePicker,
) -> AsyncIterator[httpx.AsyncClient]:
    from driftwatch.app import create_app

    app = create_app(
        settings,
        capturer=capturer,
        analyzer=analyzer,
        channel=channel,
        picker=picker,
        enable_scheduler=False,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=settings.base_url
        ) as http_client:
            yield http_client


@pytest_asyncio.fixture
async def admin_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """A client whose cookie jar holds a registered administrator session."""
    response = await client.post(
        "/api/auth/register",
        json={"email": "admin@example.com", "password": "supersecret123", "name": "Admin"},
    )
    assert response.status_code == 201, response.text
    return client
