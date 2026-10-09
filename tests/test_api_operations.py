"""The operator sees real platform telemetry without exposing it publicly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

import driftwatch.api.operations as operations_api
from driftwatch.db import Database
from driftwatch.enums import (
    AccountEmailKind,
    AccountEmailStatus,
    CheckJobKind,
    CheckJobSource,
    CheckJobStatus,
)
from driftwatch.models import (
    AccountEmailJob,
    AuditEvent,
    BillingEvent,
    BillingEventProcessing,
    Organization,
    Site,
    SiteCheckJob,
)
from driftwatch.schemas import OperationsBillingWebhooksOut, OperationsDeliveryQueueOut


async def test_operations_overview_reports_real_internal_state(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    created = await admin_client.post(
        "/api/sites",
        json={"url": "https://operations.example.test"},
    )
    assert created.status_code == 201, created.text
    site_id = int(created.json()["id"])
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        session.add(
            SiteCheckJob(
                organization_id=site.organization_id,
                site_id=site.id,
                idempotency_key="operations:test:pending",
                kind=CheckJobKind.CHECK,
                source=CheckJobSource.SCHEDULED,
                analyze=True,
                status=CheckJobStatus.PENDING,
                attempt_count=0,
                available_at=datetime.now(UTC),
                enqueued_at=datetime.now(UTC),
            )
        )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == {"backend": "sqlite", "reachable": True}
    assert body["capture"]["mode"] == "injected"
    assert body["capture"]["status"] == "not_probed"
    assert body["check_queue"]["pending"] == 1
    assert body["check_queue"]["running"] == 0
    assert body["check_queue"]["dead"] == 0
    assert body["delivery_queue"] == {
        "pending": 0,
        "failed": 0,
        "sent": 0,
        "exhausted": 0,
        "leased": 0,
        "oldest_unsent_seconds": None,
    }
    assert body["account_email_queue"] == {
        "pending": 0,
        "failed_total": 0,
        "failed_recent": 0,
        "sent": 0,
        "cancelled": 0,
        "leased": 0,
        "oldest_pending_seconds": None,
        "stale_pending": False,
        "pending_stale_after_seconds": 300,
        "recent_failure_window_seconds": 3600,
    }
    assert body["billing_webhooks"] == {
        "total": 0,
        "received": 0,
        "processing": 0,
        "stale_processing": 0,
        "completed": 0,
        "failed": 0,
        "stale_after_seconds": 300,
        "last_processed_at": None,
        "last_failed_at": None,
    }
    assert isinstance(body["storage"]["db_bytes"], int)
    assert isinstance(body["storage"]["disk_free_bytes"], int)
    assert body["maintenance"]["enabled"] is False


async def test_operations_requires_operator_and_instance_context(
    admin_client: httpx.AsyncClient,
) -> None:
    step_up = await admin_client.post(
        "/api/auth/step-up",
        json={"password": "supersecret123"},
    )
    assert step_up.status_code == 204, step_up.text
    organization = (
        await admin_client.post("/api/organizations", json={"name": "Support customer"})
    ).json()
    acting = await admin_client.get(
        "/api/operations/overview",
        headers={"X-Acting-Org": str(organization["id"])},
    )
    assert acting.status_code == 409

    await admin_client.post("/api/auth/logout")
    await admin_client.post(
        "/api/auth/register",
        json={"email": "member@example.com", "password": "member-password"},
    )
    denied = await admin_client.get("/api/operations/overview")
    assert denied.status_code == 403


async def test_operations_degrades_when_check_jobs_are_dead(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    created = await admin_client.post("/api/sites", json={"url": "https://dead-job.example.test"})
    site_id = int(created.json()["id"])
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        session.add(
            SiteCheckJob(
                organization_id=site.organization_id,
                site_id=site.id,
                idempotency_key="operations:test:dead",
                kind=CheckJobKind.CHECK,
                source=CheckJobSource.SCHEDULED,
                analyze=True,
                status=CheckJobStatus.DEAD,
                attempt_count=5,
                available_at=None,
                enqueued_at=datetime.now(UTC),
                last_error="redacted failure",
            )
        )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


async def test_dead_incident_redrive_is_scoped_safe_audited_and_idempotent(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    created = await admin_client.post(
        "/api/sites", json={"url": "https://redrive-secret-target.example.test"}
    )
    assert created.status_code == 201, created.text
    site_id = int(created.json()["id"])
    now = datetime.now(UTC)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        organization_id = site.organization_id
        dead = SiteCheckJob(
            organization_id=organization_id,
            site_id=site.id,
            idempotency_key="operations:redrive:dead",
            kind=CheckJobKind.CHECK,
            source=CheckJobSource.SCHEDULED,
            analyze=True,
            status=CheckJobStatus.DEAD,
            attempt_count=5,
            available_at=None,
            enqueued_at=now - timedelta(minutes=20),
            completed_at=now - timedelta(minutes=10),
            last_error="credential=do-not-expose upstream=10.0.0.1",
            result={"private": "diagnostic"},
        )
        session.add(dead)
        await session.flush()
        dead_id = dead.id
        other = Organization(name="Another tenant")
        session.add(other)
        await session.commit()
        other_organization_id = other.id

    instance = await admin_client.get("/api/operations/check-jobs/dead")
    assert instance.status_code == 200, instance.text
    assert instance.json()["next_before_id"] is None
    assert [item["id"] for item in instance.json()["items"]] == [dead_id]
    exposed_keys = set(instance.json()["items"][0])
    assert exposed_keys == {
        "id",
        "organization_id",
        "site_id",
        "original_job_id",
        "kind",
        "source",
        "status",
        "analyze",
        "attempt_count",
        "enqueued_at",
        "started_at",
        "completed_at",
    }
    assert "do-not-expose" not in instance.text
    assert "redrive-secret-target" not in instance.text
    assert "diagnostic" not in instance.text

    no_scope = await admin_client.get("/api/operations/tenant/check-jobs/dead")
    assert no_scope.status_code == 400
    wrong_scope = await admin_client.get(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}",
        headers={"X-Acting-Org": str(other_organization_id)},
    )
    assert wrong_scope.status_code == 404

    headers = {"X-Acting-Org": str(organization_id)}
    tenant = await admin_client.get("/api/operations/tenant/check-jobs/dead", headers=headers)
    assert tenant.status_code == 200, tenant.text
    assert [item["id"] for item in tenant.json()["items"]] == [dead_id]
    detail = await admin_client.get(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}", headers=headers
    )
    assert detail.status_code == 200, detail.text

    payload = {
        "idempotency_key": "incident-redrive-api-001",
        "reason": "Recovery after the upstream incident was resolved",
        "ticket": "OPS-417",
    }
    denied = await admin_client.post(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}/redrive",
        headers=headers,
        json=payload,
    )
    assert denied.status_code == 428
    step_up = await admin_client.post(
        "/api/auth/step-up",
        headers=headers,
        json={"password": "supersecret123"},
    )
    assert step_up.status_code == 204, step_up.text

    redriven = await admin_client.post(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}/redrive",
        headers=headers,
        json=payload,
    )
    assert redriven.status_code == 200, redriven.text
    assert redriven.json()["created"] is True
    child = redriven.json()["job"]
    child_id = int(child["id"])
    assert child["original_job_id"] == dead_id
    assert child["source"] == "redrive"
    assert child["status"] == "pending"

    replay = await admin_client.post(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}/redrive",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["job"]["id"] == child_id

    conflicting_payload = await admin_client.post(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}/redrive",
        headers=headers,
        json={**payload, "reason": "A different recovery operation was requested"},
    )
    assert conflicting_payload.status_code == 409
    second_generation = await admin_client.post(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}/redrive",
        headers=headers,
        json={**payload, "idempotency_key": "incident-redrive-api-002"},
    )
    assert second_generation.status_code == 409

    resolved_list = await admin_client.get(
        "/api/operations/tenant/check-jobs/dead", headers=headers
    )
    assert resolved_list.status_code == 200
    assert resolved_list.json()["items"] == []
    resolved_detail = await admin_client.get(
        f"/api/operations/tenant/check-jobs/dead/{dead_id}", headers=headers
    )
    assert resolved_detail.status_code == 404
    overview = await admin_client.get("/api/operations/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["check_queue"]["dead"] == 0

    async with database.session() as session:
        original = await session.get(SiteCheckJob, dead_id)
        stored_child = await session.get(SiteCheckJob, child_id)
        assert original is not None and stored_child is not None
        assert original.status == CheckJobStatus.DEAD
        assert original.last_error == "credential=do-not-expose upstream=10.0.0.1"
        stored_child.status = CheckJobStatus.DEAD
        stored_child.available_at = None
        stored_child.completed_at = now
        await session.commit()

    next_incident = await admin_client.get(
        "/api/operations/tenant/check-jobs/dead", headers=headers
    )
    assert next_incident.status_code == 200, next_incident.text
    assert [item["id"] for item in next_incident.json()["items"]] == [child_id]

    async with database.session() as session:
        events = list(
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.action == "check_job.redriven")
                )
            ).scalars()
        )
        assert len(events) == 1
        assert events[0].organization_id == organization_id
        assert events[0].target_id == str(child_id)
        assert events[0].details == {
            "original_job_id": dead_id,
            "new_job_id": child_id,
            "site_id": site_id,
            "reason": payload["reason"],
            "ticket": payload["ticket"],
        }


async def test_operations_degrades_for_failed_deliveries(
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failed_deliveries(*_: object) -> OperationsDeliveryQueueOut:
        return OperationsDeliveryQueueOut(
            pending=0,
            failed=1,
            sent=0,
            exhausted=1,
            leased=0,
        )

    monkeypatch.setattr(operations_api, "_delivery_metrics", failed_deliveries)
    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


async def test_operations_degrades_for_recent_account_email_failure(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            AccountEmailJob(
                kind=AccountEmailKind.PASSWORD_RESET,
                status=AccountEmailStatus.FAILED,
                active_key=None,
                idempotency_key="account-email:operations:failed-recent",
                attempt_count=5,
                next_attempt_at=None,
                last_error_code="email_not_configured",
                scheduled_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=1),
                updated_at=now - timedelta(minutes=1),
            )
        )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["account_email_queue"]["failed_total"] == 1
    assert body["account_email_queue"]["failed_recent"] == 1


async def test_historical_account_email_failure_does_not_degrade_forever(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            AccountEmailJob(
                kind=AccountEmailKind.PASSWORD_RESET,
                status=AccountEmailStatus.FAILED,
                active_key=None,
                idempotency_key="account-email:operations:failed-historical",
                attempt_count=5,
                next_attempt_at=None,
                last_error_code="delivery_failed",
                scheduled_at=now - timedelta(hours=3),
                finished_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=2),
            )
        )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["account_email_queue"]["failed_total"] == 1
    assert body["account_email_queue"]["failed_recent"] == 0


async def test_operations_degrades_for_stale_pending_account_email(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            AccountEmailJob(
                kind=AccountEmailKind.ACCOUNT_INVITATION,
                status=AccountEmailStatus.PENDING,
                active_key="a" * 64,
                idempotency_key="account-email:operations:stale-pending",
                attempt_count=1,
                next_attempt_at=now - timedelta(minutes=1),
                scheduled_at=now - timedelta(minutes=6),
                updated_at=now - timedelta(minutes=6),
            )
        )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["account_email_queue"]["pending"] == 1
    assert body["account_email_queue"]["stale_pending"] is True
    assert body["account_email_queue"]["oldest_pending_seconds"] >= 360


async def test_operations_reports_failed_and_stale_billing_webhooks(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    rows = (
        ("received", now - timedelta(minutes=2), None),
        ("processing", now - timedelta(minutes=1), None),
        ("processing", now - timedelta(minutes=6), None),
        ("processed", now - timedelta(minutes=4), now - timedelta(minutes=4)),
        (
            "ignored_unsupported",
            now - timedelta(minutes=3),
            now - timedelta(minutes=3),
        ),
        ("failed", now - timedelta(minutes=2), None),
    )
    async with database.session() as session:
        for index, (processing_status, updated_at, processed_at) in enumerate(rows):
            event = BillingEvent(
                provider="stripe",
                provider_event_id=f"evt_operations_{index}",
                event_type="customer.subscription.updated",
                resource_id=f"sub_operations_{index}",
                organization_id=None,
                occurred_at=updated_at,
                received_at=updated_at,
                livemode=False,
                api_version="2025-01-27.acacia",
                payload_sha256=f"{index:064x}",
                resource_data={},
            )
            session.add(event)
            await session.flush()
            session.add(
                BillingEventProcessing(
                    billing_event_id=event.id,
                    status=processing_status,
                    attempt_count=1,
                    processed_at=processed_at,
                    updated_at=updated_at,
                )
            )
        await session.commit()

    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["billing_webhooks"] == {
        "total": 6,
        "received": 1,
        "processing": 2,
        "stale_processing": 1,
        "completed": 2,
        "failed": 1,
        "stale_after_seconds": 300,
        "last_processed_at": (now - timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
        "last_failed_at": (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
    }


@pytest.mark.parametrize(("failed", "stale_processing"), ((1, 0), (0, 1)))
async def test_operations_degrades_for_each_billing_webhook_failure_signal(
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failed: int,
    stale_processing: int,
) -> None:
    async def unhealthy_billing_webhooks(*_: object) -> OperationsBillingWebhooksOut:
        return OperationsBillingWebhooksOut(
            total=1,
            received=0,
            processing=stale_processing,
            stale_processing=stale_processing,
            completed=0,
            failed=failed,
            stale_after_seconds=300,
        )

    monkeypatch.setattr(operations_api, "_billing_webhook_metrics", unhealthy_billing_webhooks)
    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "degraded"


async def test_operations_degrades_when_sqlite_cannot_fit_a_safety_copy(
    admin_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operations_api,
        "_storage_metrics",
        lambda _: {"db_bytes": 400_000_000, "wal_bytes": 0, "disk_free_bytes": 500_000_000},
    )
    response = await admin_client.get("/api/operations/overview")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
