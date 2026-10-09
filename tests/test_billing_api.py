from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.billing.provider import (
    CheckoutRequest,
    HostedSession,
    PortalRequest,
    ProviderEvent,
    ProviderPrice,
    SubscriptionSnapshot,
)
from driftwatch.config import Settings
from driftwatch.models import (
    AuditEvent,
    BillingCustomer,
    BillingPrice,
    CheckoutAttempt,
    Organization,
    Plan,
    User,
)

_TERMS_SHA256 = "a" * 64
_PRIVACY_SHA256 = "b" * 64


class BillingDouble:
    provider_name = "stripe"

    def __init__(self) -> None:
        self.checkout_calls: list[CheckoutRequest] = []
        self.portal_calls: list[PortalRequest] = []
        self.price = ProviderPrice("price_paid", 1900, "USD", "month", 1, True, True)
        self.event: ProviderEvent | None = None
        self.reconciliation_calls: list[str] = []
        self.checkout_session = HostedSession(
            "cs_same",
            "https://checkout.stripe.com/c/pay/cs_same",
            datetime.now(UTC) + timedelta(hours=1),
        )
        self.portal_session = HostedSession("bps_same", "https://billing.stripe.com/p/session/test")

    async def create_checkout(self, request: CheckoutRequest) -> HostedSession:
        self.checkout_calls.append(request)
        return self.checkout_session

    async def create_portal(self, request: PortalRequest) -> HostedSession:
        self.portal_calls.append(request)
        return self.portal_session

    async def get_price(self, provider_price_id: str) -> ProviderPrice:
        return self.price

    def verify_webhook(
        self,
        raw_body: bytes,
        headers: Mapping[str, str],
        *,
        now: datetime | None = None,
    ) -> ProviderEvent:
        assert self.event is not None
        return self.event

    async def list_subscriptions(self, customer_id: str) -> Sequence[SubscriptionSnapshot]:
        self.reconciliation_calls.append(customer_id)
        return ()

    async def aclose(self) -> None:
        return None


@pytest.fixture
def billing_settings(tmp_path: object) -> Settings:
    return Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite+aiosqlite:///{tmp_path}/billing.db",
        secret_key="test-secret-key-0123456789-abcdef",
        scheduler_enabled=False,
        run_migrations=True,
        base_url="http://localhost:8000",
        billing_provider="stripe",
        public_registration_enabled=False,
        initial_admin_email="owner@example.com",
        initial_admin_password="supersecret123",
        billing_self_serve_enabled=True,
        billing_legal_gate_enabled=True,
        billing_terms_version="terms-2026-01",
        billing_privacy_version="privacy-2026-01",
        billing_terms_url="https://legal.example.test/terms/2026-01",
        billing_privacy_url="https://legal.example.test/privacy/2026-01",
        billing_terms_sha256=_TERMS_SHA256,
        billing_privacy_sha256=_PRIVACY_SHA256,
        stripe_secret_key="sk_test_1234567890",
        stripe_webhook_secret="whsec_1234567890",
        stripe_api_version="2025-06-30.basil",
    )


@pytest_asyncio.fixture
async def billing_client(
    billing_settings: Settings,
    capturer: object,
    analyzer: object,
    channel: object,
    picker: object,
) -> AsyncIterator[tuple[httpx.AsyncClient, BillingDouble, object]]:
    from driftwatch.app import create_app

    provider = BillingDouble()
    app = create_app(
        billing_settings,
        capturer=capturer,  # type: ignore[arg-type]
        analyzer=analyzer,  # type: ignore[arg-type]
        channel=channel,  # type: ignore[arg-type]
        picker=picker,  # type: ignore[arg-type]
        billing_provider=provider,
        enable_scheduler=False,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url=billing_settings.base_url
        ) as client:
            yield client, provider, app


async def _register_and_catalog(
    client: httpx.AsyncClient,
    app: object,
    *,
    enter_organization: bool = True,
) -> int:
    registered = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "supersecret123"},
    )
    assert registered.status_code == 200, registered.text
    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        organization = (await session.execute(Organization.__table__.select())).first()
        assert organization is not None
        organization_id = int(organization.id)
        plan = Plan(
            key="paid",
            name="Paid",
            max_sites=10,
            max_members=8,
            monthly_ai_check_limit=100,
            currency="USD",
            is_active=True,
            is_self_serve=True,
        )
        session.add(plan)
        await session.flush()
        session.add(
            BillingPrice(
                plan_id=plan.id,
                provider="stripe",
                provider_price_id="price_paid",
                version=1,
                unit_amount_minor=1900,
                currency="USD",
                recurring_interval="month",
                interval_count=1,
                is_active=True,
            )
        )
        await session.commit()
        if enter_organization:
            client.headers["X-Acting-Org"] = str(organization_id)
        return organization_id


def _checkout_payload(idempotency_key: str) -> dict[str, object]:
    return {
        "billing_price_id": 1,
        "idempotency_key": idempotency_key,
        "accepted_terms_version": "terms-2026-01",
        "accepted_privacy_version": "privacy-2026-01",
        "accepted_terms_sha256": _TERMS_SHA256,
        "accepted_privacy_sha256": _PRIVACY_SHA256,
    }


@pytest.mark.asyncio
async def test_billing_catalog_exposes_member_entitlement(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, _, app = billing_client
    await _register_and_catalog(client, app)

    catalog = await client.get("/api/billing/catalog")

    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["prices"][0]["max_members"] == 8


@pytest.mark.asyncio
async def test_operator_home_org_is_not_an_implicit_billing_context(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(
        client,
        app,
        enter_organization=False,
    )
    stepped = await client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
    )
    assert stepped.status_code == 204

    responses = (
        await client.get("/api/billing/status"),
        await client.get("/api/billing/catalog"),
        await client.post(
            "/api/billing/checkout",
            json=_checkout_payload("checkout-without-tenant"),
        ),
        await client.post(
            "/api/billing/portal",
            json={"idempotency_key": "portal-without-tenant"},
        ),
        await client.post(f"/api/billing/reconcile/{organization_id}"),
    )

    assert {response.status_code for response in responses} == {400}
    assert all(
        response.json()["detail"] == "Enter an organization before accessing tenant billing"
        for response in responses
    )
    assert provider.checkout_calls == []
    assert provider.portal_calls == []
    assert provider.reconciliation_calls == []

    client.headers["X-Acting-Org"] = str(organization_id)
    assert (await client.get("/api/billing/status")).status_code == 200


@pytest.mark.asyncio
async def test_checkout_requires_step_up_and_reuses_durable_attempt(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    await _register_and_catalog(client, app)
    payload = _checkout_payload("checkout-request-1")

    assert (await client.post("/api/billing/checkout", json=payload)).status_code == 428
    stepped = await client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
    )
    assert stepped.status_code == 204
    first = await client.post("/api/billing/checkout", json=payload)
    second = await client.post("/api/billing/checkout", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert len(provider.checkout_calls) == 1
    competing = {**payload, "idempotency_key": "checkout-request-competing"}
    assert (await client.post("/api/billing/checkout", json=competing)).status_code == 409
    assert len(provider.checkout_calls) == 1
    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        attempts = (await session.execute(CheckoutAttempt.__table__.select())).all()
    assert len(attempts) == 1
    assert attempts[0].status == "created"
    assert attempts[0].active_marker is True
    assert attempts[0].terms_sha256 == _TERMS_SHA256
    assert attempts[0].privacy_sha256 == _PRIVACY_SHA256
    assert provider.checkout_calls[0].terms_sha256 == _TERMS_SHA256


@pytest.mark.asyncio
async def test_checkout_retry_recovers_atomic_attempt_and_audit_commit(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    payload = _checkout_payload("checkout-audit-recovery")

    original_commit = AsyncSession.commit
    fail_once = True

    async def flaky_commit(session: AsyncSession) -> None:
        nonlocal fail_once
        has_checkout_audit = any(
            isinstance(row, AuditEvent) and row.action == "billing.checkout_created"
            for row in session.new
        )
        if fail_once and has_checkout_audit:
            fail_once = False
            raise RuntimeError("simulated final transaction failure")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)
    failed = await client.post("/api/billing/checkout", json=payload)
    recovered = await client.post("/api/billing/checkout", json=payload)

    assert failed.status_code == 500
    assert recovered.status_code == 200, recovered.text
    assert len(provider.checkout_calls) == 2
    assert {request.idempotency_key for request in provider.checkout_calls} == {
        f"checkout:{organization_id}:checkout-audit-recovery"
    }

    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        attempts = (await session.execute(CheckoutAttempt.__table__.select())).all()
        audits = (
            await session.execute(
                AuditEvent.__table__.select().where(AuditEvent.action == "billing.checkout_created")
            )
        ).all()
    assert len(attempts) == 1
    assert attempts[0].status == "created"
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_checkout_recovers_a_stale_pending_attempt_after_client_loses_its_key(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    database = app.state.db  # type: ignore[attr-defined]
    stale_at = datetime.now(UTC) - timedelta(minutes=6)
    async with database.session() as session:
        owner_id = await session.scalar(select(User.id).where(User.email == "owner@example.com"))
        price_id = await session.scalar(select(BillingPrice.id))
        assert owner_id is not None and price_id is not None
        session.add(
            CheckoutAttempt(
                organization_id=organization_id,
                billing_price_id=price_id,
                requested_by_user_id=owner_id,
                idempotency_key="checkout-key-lost-on-reload",
                terms_version="terms-2026-01",
                privacy_version="privacy-2026-01",
                terms_sha256=_TERMS_SHA256,
                privacy_sha256=_PRIVACY_SHA256,
                status="pending",
                active_marker=True,
                created_at=stale_at,
                updated_at=stale_at,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/billing/checkout",
        json=_checkout_payload("checkout-new-browser-key"),
    )

    assert response.status_code == 200, response.text
    assert [request.idempotency_key for request in provider.checkout_calls] == [
        f"checkout:{organization_id}:checkout-key-lost-on-reload"
    ]
    async with database.session() as session:
        attempts = (await session.scalars(select(CheckoutAttempt))).all()
        actions = (
            await session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.action.in_(
                        {
                            "billing.checkout_pending_recovered",
                            "billing.checkout_created",
                        }
                    )
                )
            )
        ).all()
    assert len(attempts) == 1
    assert attempts[0].status == "created"
    assert set(actions) == {
        "billing.checkout_pending_recovered",
        "billing.checkout_created",
    }


@pytest.mark.asyncio
async def test_checkout_abandons_only_an_incompatible_day_old_pending_attempt(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    database = app.state.db  # type: ignore[attr-defined]
    stale_at = datetime.now(UTC) - timedelta(hours=25)
    async with database.session() as session:
        owner_id = await session.scalar(select(User.id).where(User.email == "owner@example.com"))
        price_id = await session.scalar(select(BillingPrice.id))
        assert owner_id is not None and price_id is not None
        session.add(
            CheckoutAttempt(
                organization_id=organization_id,
                billing_price_id=price_id,
                requested_by_user_id=owner_id,
                idempotency_key="checkout-obsolete-legal-version",
                terms_version="terms-obsolete",
                privacy_version="privacy-obsolete",
                terms_sha256="c" * 64,
                privacy_sha256="d" * 64,
                status="pending",
                active_marker=True,
                created_at=stale_at,
                updated_at=stale_at,
            )
        )
        await session.commit()

    response = await client.post(
        "/api/billing/checkout",
        json=_checkout_payload("checkout-current-legal-version"),
    )

    assert response.status_code == 200, response.text
    assert [request.idempotency_key for request in provider.checkout_calls] == [
        f"checkout:{organization_id}:checkout-current-legal-version"
    ]
    async with database.session() as session:
        attempts = (
            await session.scalars(select(CheckoutAttempt).order_by(CheckoutAttempt.id))
        ).all()
        abandoned_audits = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action == "billing.checkout_pending_abandoned")
            )
        ).all()
    assert [(row.status, row.active_marker) for row in attempts] == [
        ("abandoned", None),
        ("created", True),
    ]
    assert len(abandoned_audits) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_stale_legal_document_fingerprint(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    payload = _checkout_payload("checkout-stale-legal")
    payload["accepted_terms_sha256"] = "c" * 64

    response = await client.post("/api/billing/checkout", json=payload)

    assert response.status_code == 409
    assert provider.checkout_calls == []


@pytest.mark.asyncio
async def test_checkout_rejects_provider_catalog_mismatch(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    provider.price = ProviderPrice("price_paid", 2900, "USD", "month", 1, True, True)

    response = await client.post(
        "/api/billing/checkout",
        json=_checkout_payload("checkout-request-2"),
    )

    assert response.status_code == 409
    assert provider.checkout_calls == []


@pytest.mark.asyncio
async def test_portal_requires_step_up(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        session.add(
            BillingCustomer(
                organization_id=organization_id,
                provider="stripe",
                provider_customer_id="cus_acme",
            )
        )
        await session.commit()

    response = await client.post(
        "/api/billing/portal",
        json={"idempotency_key": "portal-request-1"},
    )

    assert response.status_code == 428
    assert provider.portal_calls == []


@pytest.mark.asyncio
async def test_suspended_customer_can_open_portal_when_new_checkout_is_closed(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        organization.is_active = False
        organization.billing_suspended_at = datetime.now(UTC)
        owner = (await session.execute(User.__table__.select())).first()
        assert owner is not None
        await session.execute(
            User.__table__.update().where(User.id == owner.id).values(is_superadmin=False)
        )
        session.add(
            BillingCustomer(
                organization_id=organization_id,
                provider="stripe",
                provider_customer_id="cus_recovery",
            )
        )
        await session.commit()
    app.state.settings.billing_self_serve_enabled = False  # type: ignore[attr-defined]
    client.headers.pop("X-Acting-Org", None)

    assert (await client.post("/api/auth/logout")).status_code == 204
    login = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["organization_suspended"] is True
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["organization_suspended"] is True
    catalog = await client.get("/api/billing/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["self_serve_ready"] is False
    assert (await client.get("/api/billing/status")).status_code == 200
    stepped = await client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
    )
    assert stepped.status_code == 204, stepped.text

    portal = await client.post(
        "/api/billing/portal",
        json={"idempotency_key": "portal-recovery-request"},
    )

    assert portal.status_code == 200, portal.text
    assert portal.json()["url"].startswith("https://billing.stripe.com/")
    assert len(provider.portal_calls) == 1


@pytest.mark.asyncio
async def test_checkout_rejects_an_untrusted_provider_redirect(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    await _register_and_catalog(client, app)
    await client.post("/api/auth/step-up", json={"password": "supersecret123"})
    provider.checkout_session = HostedSession(
        "cs_untrusted",
        "https://checkout.stripe.com.evil.test/c/pay/session",
        datetime.now(UTC) + timedelta(hours=1),
    )

    response = await client.post(
        "/api/billing/checkout",
        json=_checkout_payload("checkout-untrusted-host"),
    )

    assert response.status_code == 502
    assert "evil.test" not in response.text


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_live_mode_before_persistence(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, _app = billing_client
    now = datetime.now(UTC)
    provider.event = ProviderEvent(
        provider="stripe",
        event_id="evt_live",
        event_type="unsupported.event",
        occurred_at=now,
        received_at=now,
        livemode=True,
        api_version="2025-06-30.basil",
        payload_sha256="a" * 64,
        resource=None,
    )

    response = await client.post(
        "/api/billing/webhooks/stripe",
        content=b"{}",
        headers={"content-type": "application/json", "stripe-signature": "fake"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_api_version_before_persistence(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, _app = billing_client
    now = datetime.now(UTC)
    provider.event = ProviderEvent(
        provider="stripe",
        event_id="evt_wrong_api_version",
        event_type="unsupported.event",
        occurred_at=now,
        received_at=now,
        livemode=False,
        api_version="2025-03-31.basil",
        payload_sha256="b" * 64,
        resource=None,
    )

    response = await client.post(
        "/api/billing/webhooks/stripe",
        content=b"{}",
        headers={"content-type": "application/json", "stripe-signature": "fake"},
    )

    assert response.status_code == 400
    assert "API version" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reconciliation_cannot_cross_the_active_support_tenant(
    billing_client: tuple[httpx.AsyncClient, BillingDouble, object],
) -> None:
    client, provider, app = billing_client
    organization_id = await _register_and_catalog(client, app)
    database = app.state.db  # type: ignore[attr-defined]
    async with database.session() as session:
        session.add(
            BillingCustomer(
                organization_id=organization_id,
                provider="stripe",
                provider_customer_id="cus_target",
            )
        )
        other = Organization(name="Different acting tenant")
        session.add(other)
        await session.commit()
        other_id = other.id
    stepped = await client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
        headers={"X-Acting-Org": str(other_id)},
    )
    assert stepped.status_code == 204, stepped.text

    response = await client.post(
        f"/api/billing/reconcile/{organization_id}",
        headers={"X-Acting-Org": str(other_id)},
    )

    assert response.status_code == 409
    assert provider.reconciliation_calls == []
