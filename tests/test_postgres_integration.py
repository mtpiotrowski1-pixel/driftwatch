"""Production-database migration and concurrency checks.

The regular suite stays on SQLite for speed. CI supplies a dedicated Postgres
database through ``DRIFTWATCH_TEST_POSTGRES_URL`` and runs this module alone.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

import driftwatch.billing.service as billing_service
from driftwatch.account_mail import AccountEmailWorker, enqueue_account_invitation
from driftwatch.billing.access import lock_organization_access
from driftwatch.billing.plan_contract import lock_plan_contract
from driftwatch.billing.provider import ProviderEvent, SubscriptionLine, SubscriptionSnapshot
from driftwatch.billing.service import expire_billing_entitlements, ingest_provider_event
from driftwatch.check_queue import (
    DueSite,
    claim_next_check,
    enqueue_scheduled_checks,
    redrive_dead_check,
)
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import CheckJobStatus
from driftwatch.exceptions import ConflictError, PlanLimitReached
from driftwatch.models import (
    AccountEmailJob,
    AuditEvent,
    BillingCustomer,
    BillingPrice,
    Organization,
    Plan,
    Site,
    SiteCheckJob,
    Subscription,
    User,
)
from driftwatch.quota import reserve_member_slot, reserve_site_slot
from tests.conftest import RecordingChannel

_URL = os.environ.get("DRIFTWATCH_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="Postgres integration URL is not configured")


@pytest_asyncio.fixture
async def postgres_database() -> AsyncIterator[Database]:
    assert _URL is not None
    database = Database(_URL)
    await database.upgrade()
    try:
        yield database
    finally:
        await database.dispose()


async def test_postgres_migrations_and_atomic_site_cap(postgres_database: Database) -> None:
    async with postgres_database.session() as session:
        organization = Organization(name="Postgres concurrency", max_sites=3)
        session.add(organization)
        await session.commit()
        organization_id = organization.id

    async def create_site(index: int) -> bool:
        async with postgres_database.session() as session:
            try:
                await reserve_site_slot(session, organization_id)
            except PlanLimitReached:
                await session.rollback()
                return False
            session.add(
                Site(
                    organization_id=organization_id,
                    url=f"https://postgres-{index}.example",
                )
            )
            await session.commit()
            return True

    created = await asyncio.gather(*(create_site(index) for index in range(12)))

    assert sum(created) == 3
    async with postgres_database.session() as session:
        count = await session.scalar(
            select(func.count(Site.id)).where(Site.organization_id == organization_id)
        )
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert count == organization.site_slots_used == 3


async def test_postgres_atomic_member_cap(postgres_database: Database) -> None:
    suffix = uuid4().hex
    async with postgres_database.session() as session:
        organization = Organization(name="Postgres member concurrency", max_members=3)
        session.add(organization)
        await session.commit()
        organization_id = organization.id

    async def create_member(index: int) -> bool:
        async with postgres_database.session() as session:
            try:
                await reserve_member_slot(session, organization_id)
            except PlanLimitReached:
                await session.rollback()
                return False
            session.add(
                User(
                    organization_id=organization_id,
                    email=f"postgres-member-{suffix}-{index}@example.test",
                    password_hash="unusable-test-hash",
                )
            )
            await session.commit()
            return True

    created = await asyncio.gather(*(create_member(index) for index in range(12)))

    assert sum(created) == 3
    async with postgres_database.session() as session:
        count = await session.scalar(
            select(func.count(User.id)).where(
                User.organization_id == organization_id,
                User.is_superadmin.is_(False),
            )
        )
        organization = await session.get(Organization, organization_id)
        assert organization is not None
        assert count == organization.member_slots_used == 3


async def test_postgres_concurrent_claim_leases_a_check_once(
    postgres_database: Database,
) -> None:
    now = datetime.now(UTC)
    async with postgres_database.session() as session:
        organization = Organization(name="Postgres check queue")
        session.add(organization)
        await session.flush()
        site = Site(
            organization_id=organization.id,
            url="https://postgres-check-queue.example",
        )
        session.add(site)
        await session.flush()
        [job_id] = await enqueue_scheduled_checks(
            session,
            [DueSite(site.id, organization.id, None)],
            now=now,
            limit=1,
            global_capacity=1_000,
            per_org_capacity=100,
        )
        await session.commit()

    async def claim() -> object:
        async with postgres_database.session() as session:
            return await claim_next_check(session, now=now, lease_seconds=30)

    claims = await asyncio.gather(claim(), claim())

    assert sum(claim is not None for claim in claims) == 1
    async with postgres_database.session() as session:
        job = await session.get(SiteCheckJob, job_id)
        assert job is not None
        assert job.status == CheckJobStatus.RUNNING
        assert job.attempt_count == 1


async def test_postgres_serializes_concurrent_dead_check_redrive(
    postgres_database: Database,
) -> None:
    now = datetime.now(UTC)
    suffix = uuid4().hex
    async with postgres_database.session() as session:
        organization = Organization(name=f"Postgres redrive {suffix[:8]}")
        session.add(organization)
        await session.flush()
        site = Site(
            organization_id=organization.id,
            url=f"https://postgres-redrive-{suffix}.example",
        )
        session.add(site)
        await session.flush()
        dead = SiteCheckJob(
            organization_id=organization.id,
            site_id=site.id,
            idempotency_key=f"scheduled:postgres-redrive:{suffix}",
            kind="check",
            source="scheduled",
            analyze=True,
            status=CheckJobStatus.DEAD,
            attempt_count=5,
            available_at=None,
            enqueued_at=now,
            completed_at=now,
        )
        session.add(dead)
        await session.commit()
        organization_id = organization.id
        dead_id = dead.id

    async def redrive(request_key: str) -> tuple[int, bool] | str:
        async with postgres_database.session() as session:
            try:
                child, created = await redrive_dead_check(
                    session,
                    dead_id,
                    organization_id=organization_id,
                    request_key=request_key,
                    request_sha256="d" * 64,
                    now=now,
                    global_capacity=1_000,
                    per_org_capacity=100,
                )
                await session.commit()
                return child.id, created
            except ConflictError:
                await session.rollback()
                return "conflict"

    same_key = await asyncio.gather(
        redrive("postgres-redrive-same-key"),
        redrive("postgres-redrive-same-key"),
    )
    assert all(result != "conflict" for result in same_key)
    typed_results = [result for result in same_key if isinstance(result, tuple)]
    assert len(typed_results) == 2
    assert len({result[0] for result in typed_results}) == 1
    assert sorted(result[1] for result in typed_results) == [False, True]

    assert await redrive("postgres-redrive-second-key") == "conflict"
    async with postgres_database.session() as session:
        children = list(
            (
                await session.execute(
                    select(SiteCheckJob).where(SiteCheckJob.original_job_id == dead_id)
                )
            ).scalars()
        )
        assert len(children) == 1
        assert children[0].redrive_request_sha256 == "d" * 64


async def test_postgres_concurrent_account_email_claim_delivers_once(
    postgres_database: Database,
    settings: Settings,
) -> None:
    async with postgres_database.session() as session:
        organization = Organization(name="Postgres account email")
        session.add(organization)
        await session.flush()
        user = User(
            organization_id=organization.id,
            email=f"postgres-account-{uuid4().hex}@example.test",
            password_hash="unusable-test-hash",
        )
        session.add(user)
        await session.flush()
        job, _ = await enqueue_account_invitation(session, user=user)
        await session.commit()
        job_id = job.id

    channel = RecordingChannel()
    worker_settings = settings.model_copy(update={"database_url": _URL})
    workers = [
        AccountEmailWorker(postgres_database, worker_settings, channel=channel),
        AccountEmailWorker(postgres_database, worker_settings, channel=channel),
    ]
    results = await asyncio.gather(*(worker.drain(limit=1) for worker in workers))

    assert sum(results) == 1
    assert len(channel.sent) == 1
    async with postgres_database.session() as session:
        stored = await session.get(AccountEmailJob, job_id)
        assert stored is not None
        assert str(stored.status) == "sent"
        assert stored.attempt_count == 1


async def test_postgres_plan_contract_lock_serializes_first_price_publication(
    postgres_database: Database,
) -> None:
    suffix = uuid4().hex
    async with postgres_database.session() as session:
        plan = Plan(key=f"lock-{suffix[:12]}", name="Contract lock", currency="USD")
        session.add(plan)
        await session.commit()
        plan_id = plan.id

    publisher_locked = asyncio.Event()
    allow_publish = asyncio.Event()

    async def publish_price() -> None:
        async with postgres_database.session() as session:
            locked = await lock_plan_contract(session, plan_id)
            assert locked is not None
            publisher_locked.set()
            await allow_publish.wait()
            session.add(
                BillingPrice(
                    plan_id=plan_id,
                    provider="stripe",
                    provider_price_id=f"price_{suffix}",
                    version=1,
                    unit_amount_minor=2_500,
                    currency="USD",
                )
            )
            await session.commit()

    async def edit_contract() -> int:
        await publisher_locked.wait()
        async with postgres_database.session() as session:
            locked = await lock_plan_contract(session, plan_id)
            assert locked is not None
            count = await session.scalar(
                select(func.count(BillingPrice.id)).where(BillingPrice.plan_id == plan_id)
            )
            await session.commit()
            return int(count or 0)

    publisher = asyncio.create_task(publish_price())
    await publisher_locked.wait()
    editor = asyncio.create_task(edit_contract())
    await asyncio.sleep(0.1)
    assert not editor.done(), "the competing contract edit must wait for publication"

    allow_publish.set()
    await publisher
    assert await editor == 1


async def test_postgres_audit_ledger_rejects_database_level_mutation(
    postgres_database: Database,
) -> None:
    async with postgres_database.session() as session:
        event = AuditEvent(
            actor_user_id=1,
            actor_email="operator@example.com",
            actor_is_superadmin=True,
            action="postgres.test",
            target_type="integration",
            details={},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with postgres_database.session() as session:
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(
                text("UPDATE audit_events SET action = 'tampered' WHERE id = :event_id"),
                {"event_id": event_id},
            )
        await session.rollback()

    async with postgres_database.session() as session:
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(
                text("DELETE FROM audit_events WHERE id = :event_id"),
                {"event_id": event_id},
            )
        await session.rollback()

    async with postgres_database.session() as session:
        stored = await session.get(AuditEvent, event_id)
        assert stored is not None
        assert stored.action == "postgres.test"


async def test_postgres_serializes_subscription_events_per_billing_customer(
    postgres_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    newer_event_id = f"evt_pg_newer_{suffix}"
    older_event_id = f"evt_pg_older_{suffix}"
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    async with postgres_database.session() as session:
        organization = Organization(name=f"Webhook ordering {suffix[:8]}")
        plan = Plan(
            key=f"webhook-{suffix[:12]}",
            name="Webhook ordering",
            max_sites=10,
            max_members=5,
            monthly_ai_check_limit=50,
            currency="USD",
        )
        session.add_all([organization, plan])
        await session.flush()
        session.add_all(
            [
                BillingCustomer(
                    organization_id=organization.id,
                    provider="stripe",
                    provider_customer_id=f"cus_{suffix}",
                ),
                BillingPrice(
                    plan_id=plan.id,
                    provider="stripe",
                    provider_price_id=f"price_{suffix}",
                    version=1,
                    unit_amount_minor=1900,
                    currency="USD",
                    recurring_interval="month",
                    interval_count=1,
                ),
            ]
        )
        await session.commit()
        organization_id = organization.id

    def subscription_event(*, event_id: str, status: str, offset: int) -> ProviderEvent:
        occurred_at = base_time + timedelta(seconds=offset)
        return ProviderEvent(
            provider="stripe",
            event_id=event_id,
            event_type="customer.subscription.updated",
            occurred_at=occurred_at,
            received_at=occurred_at,
            livemode=False,
            api_version="2025-06-30.basil",
            payload_sha256=("a" if status == "active" else "b") * 64,
            resource=SubscriptionSnapshot(
                provider_subscription_id=f"sub_{suffix}",
                provider_customer_id=f"cus_{suffix}",
                status=status,
                organization_reference=None,
                items=(SubscriptionLine(f"si_{suffix}", f"price_{suffix}", 1),),
                current_period_start=base_time,
                current_period_end=base_time + timedelta(days=30),
            ),
        )

    newer_inside_projection = asyncio.Event()
    release_newer = asyncio.Event()
    original_sync = billing_service._sync_subscription_items
    paused = False

    async def pause_newer_projection(
        session: object,
        subscription: Subscription,
        *,
        provider: str,
        snapshots: tuple[SubscriptionLine, ...],
    ) -> int | None:
        nonlocal paused
        if subscription.last_event_id == newer_event_id and not paused:
            paused = True
            newer_inside_projection.set()
            await release_newer.wait()
        return await original_sync(
            session,  # type: ignore[arg-type]
            subscription,
            provider=provider,
            snapshots=snapshots,
        )

    monkeypatch.setattr(billing_service, "_sync_subscription_items", pause_newer_projection)

    async def ingest(event: ProviderEvent) -> str:
        async with postgres_database.session() as session:
            result = await ingest_provider_event(session, event, grace_days=7)
            return result.status

    newer = asyncio.create_task(
        ingest(subscription_event(event_id=newer_event_id, status="active", offset=2))
    )
    await asyncio.wait_for(newer_inside_projection.wait(), timeout=10)
    older = asyncio.create_task(
        ingest(subscription_event(event_id=older_event_id, status="canceled", offset=1))
    )
    await asyncio.sleep(0.2)
    assert not older.done(), "the older event must wait for the BillingCustomer row lock"

    release_newer.set()
    assert await newer == "processed"
    assert await older == "ignored_out_of_order"

    async with postgres_database.session() as session:
        subscription = (
            await session.execute(
                select(Subscription).where(Subscription.provider_subscription_id == f"sub_{suffix}")
            )
        ).scalar_one()
        organization = await session.get(Organization, organization_id)

    assert subscription.status == "active"
    assert subscription.last_event_id == newer_event_id
    assert organization is not None and organization.is_active is True


async def test_postgres_operator_suspension_wins_against_paid_webhook(
    postgres_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    base_time = datetime(2026, 2, 1, tzinfo=UTC)
    manual_suspension_at = base_time + timedelta(minutes=1)
    async with postgres_database.session() as session:
        organization = Organization(name=f"Operator webhook race {suffix[:8]}")
        plan = Plan(
            key=f"operator-race-{suffix[:12]}",
            name="Operator webhook race",
            max_sites=11,
            max_members=7,
            monthly_ai_check_limit=60,
            currency="USD",
        )
        session.add_all([organization, plan])
        await session.flush()
        session.add_all(
            [
                BillingCustomer(
                    organization_id=organization.id,
                    provider="stripe",
                    provider_customer_id=f"cus_operator_{suffix}",
                ),
                BillingPrice(
                    plan_id=plan.id,
                    provider="stripe",
                    provider_price_id=f"price_operator_{suffix}",
                    version=1,
                    unit_amount_minor=2100,
                    currency="USD",
                    recurring_interval="month",
                    interval_count=1,
                ),
            ]
        )
        await session.commit()
        organization_id = organization.id

    event = ProviderEvent(
        provider="stripe",
        event_id=f"evt_operator_paid_{suffix}",
        event_type="customer.subscription.updated",
        occurred_at=base_time,
        received_at=base_time,
        livemode=False,
        api_version="2025-06-30.basil",
        payload_sha256="c" * 64,
        resource=SubscriptionSnapshot(
            provider_subscription_id=f"sub_operator_{suffix}",
            provider_customer_id=f"cus_operator_{suffix}",
            status="active",
            organization_reference=None,
            items=(
                SubscriptionLine(
                    f"si_operator_{suffix}",
                    f"price_operator_{suffix}",
                    1,
                ),
            ),
            current_period_start=base_time,
            current_period_end=base_time + timedelta(days=30),
        ),
    )

    operator_locked = asyncio.Event()
    release_operator = asyncio.Event()
    paid_waiting = asyncio.Event()
    original_access_lock = billing_service.lock_organization_access

    async def observe_paid_access_lock(session: object, organization_id_arg: int) -> Organization:
        task = asyncio.current_task()
        if task is not None and task.get_name() == "paid-webhook":
            paid_waiting.set()
        organization = await original_access_lock(
            session,  # type: ignore[arg-type]
            organization_id_arg,
        )
        assert organization is not None
        return organization

    monkeypatch.setattr(
        billing_service,
        "lock_organization_access",
        observe_paid_access_lock,
    )

    async def suspend_as_operator() -> None:
        async with postgres_database.session() as session:
            organization = await lock_organization_access(session, organization_id)
            assert organization is not None
            organization.is_active = False
            organization.manually_suspended_at = manual_suspension_at
            operator_locked.set()
            await release_operator.wait()
            await session.commit()

    async def project_paid_webhook() -> str:
        async with postgres_database.session() as session:
            result = await ingest_provider_event(session, event, grace_days=7)
            return result.status

    operator = asyncio.create_task(suspend_as_operator(), name="operator-suspension")
    await asyncio.wait_for(operator_locked.wait(), timeout=10)
    paid = asyncio.create_task(project_paid_webhook(), name="paid-webhook")
    await asyncio.wait_for(paid_waiting.wait(), timeout=10)
    await asyncio.sleep(0.1)
    assert not paid.done(), "the paid projection must wait for the operator's organization lock"

    release_operator.set()
    await operator
    assert await paid == "processed"

    async with postgres_database.session() as session:
        organization = await session.get(Organization, organization_id)

    assert organization is not None
    assert organization.manually_suspended_at == manual_suspension_at
    assert organization.billing_suspended_at is None
    assert organization.is_active is False


async def test_postgres_renewal_wins_after_expiry_sweep(
    postgres_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    base_time = datetime(2026, 3, 1, tzinfo=UTC)
    async with postgres_database.session() as session:
        organization = Organization(name=f"Sweep renewal race {suffix[:8]}")
        plan = Plan(
            key=f"sweep-race-{suffix[:12]}",
            name="Sweep renewal race",
            max_sites=12,
            max_members=8,
            monthly_ai_check_limit=70,
            currency="USD",
        )
        session.add_all([organization, plan])
        await session.flush()
        session.add_all(
            [
                BillingCustomer(
                    organization_id=organization.id,
                    provider="stripe",
                    provider_customer_id=f"cus_sweep_{suffix}",
                ),
                BillingPrice(
                    plan_id=plan.id,
                    provider="stripe",
                    provider_price_id=f"price_sweep_{suffix}",
                    version=1,
                    unit_amount_minor=2200,
                    currency="USD",
                    recurring_interval="month",
                    interval_count=1,
                ),
            ]
        )
        await session.commit()
        organization_id = organization.id

    def subscription_event(*, event_id: str, period_end: datetime) -> ProviderEvent:
        return ProviderEvent(
            provider="stripe",
            event_id=event_id,
            event_type="customer.subscription.updated",
            occurred_at=period_end - timedelta(days=1),
            received_at=period_end - timedelta(days=1),
            livemode=False,
            api_version="2025-06-30.basil",
            payload_sha256=("d" if "initial" in event_id else "e") * 64,
            resource=SubscriptionSnapshot(
                provider_subscription_id=f"sub_sweep_{suffix}",
                provider_customer_id=f"cus_sweep_{suffix}",
                status="active",
                organization_reference=None,
                items=(
                    SubscriptionLine(
                        f"si_sweep_{suffix}",
                        f"price_sweep_{suffix}",
                        1,
                    ),
                ),
                current_period_start=period_end - timedelta(days=30),
                current_period_end=period_end,
            ),
        )

    initial_period_end = base_time + timedelta(days=1)
    async with postgres_database.session() as session:
        initial = await ingest_provider_event(
            session,
            subscription_event(
                event_id=f"evt_sweep_initial_{suffix}",
                period_end=initial_period_end,
            ),
            grace_days=7,
        )
    assert initial.status == "processed"

    sweep_holds_access = asyncio.Event()
    release_sweep = asyncio.Event()
    renewal_waiting = asyncio.Event()
    original_require_org = billing_service._require_locked_organization
    original_lock_customer = billing_service._lock_customer

    async def pause_target_sweep(session: object, organization_id_arg: int) -> Organization:
        organization = await original_require_org(
            session,  # type: ignore[arg-type]
            organization_id_arg,
        )
        if (
            organization_id_arg == organization_id
            and asyncio.current_task() is not None
            and asyncio.current_task().get_name() == "entitlement-sweep"
        ):
            sweep_holds_access.set()
            await release_sweep.wait()
        return organization

    async def observe_renewal_customer_lock(
        session: object,
        *,
        provider: str,
        customer_id: str,
    ) -> BillingCustomer | None:
        if asyncio.current_task() is not None and asyncio.current_task().get_name() == "renewal":
            renewal_waiting.set()
        return await original_lock_customer(
            session,  # type: ignore[arg-type]
            provider=provider,
            customer_id=customer_id,
        )

    monkeypatch.setattr(billing_service, "_require_locked_organization", pause_target_sweep)
    monkeypatch.setattr(billing_service, "_lock_customer", observe_renewal_customer_lock)

    async def run_sweep() -> int:
        async with postgres_database.session() as session:
            refreshed = await expire_billing_entitlements(
                session,
                now=base_time + timedelta(days=2),
                grace_days=7,
            )
            await session.commit()
            return refreshed

    async def project_renewal() -> str:
        async with postgres_database.session() as session:
            result = await ingest_provider_event(
                session,
                subscription_event(
                    event_id=f"evt_sweep_renewal_{suffix}",
                    period_end=base_time + timedelta(days=32),
                ),
                grace_days=7,
            )
            return result.status

    sweep = asyncio.create_task(run_sweep(), name="entitlement-sweep")
    await asyncio.wait_for(sweep_holds_access.wait(), timeout=10)
    renewal = asyncio.create_task(project_renewal(), name="renewal")
    await asyncio.wait_for(renewal_waiting.wait(), timeout=10)
    await asyncio.sleep(0.1)
    assert not renewal.done(), "the renewal must wait for the sweep's billing-customer lock"

    release_sweep.set()
    assert await sweep >= 1
    assert await renewal == "processed"

    async with postgres_database.session() as session:
        organization = await session.get(Organization, organization_id)
        subscription = (
            await session.execute(
                select(Subscription).where(
                    Subscription.provider_subscription_id == f"sub_sweep_{suffix}"
                )
            )
        ).scalar_one()

    assert organization is not None
    assert organization.is_active is True
    assert organization.billing_suspended_at is None
    assert subscription.current_period_end == base_time + timedelta(days=32)
    assert subscription.access_suspended_at is None
