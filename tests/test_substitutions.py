"""Tests for recipient substitutions and their send-time resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
from tests.conftest import create_org

from driftwatch.db import Database
from driftwatch.models import Project, Recipient, RecipientSubstitution, Site
from driftwatch.notifications.dispatch import resolve_send_targets


@dataclass
class Fixture:
    org_id: int
    project_id: int
    project_site_id: int
    standalone_site_id: int
    recipient_id: int


async def _setup(database: Database) -> Fixture:
    """An org with a project holding one site, plus a second project-less site,
    and one recipient — enough to exercise every substitution scope."""
    async with database.session() as session:
        org_id = await create_org(session)
        project = Project(name="Marketing", organization_id=org_id)
        session.add(project)
        await session.flush()
        project_site = Site(url="https://a.example", project_id=project.id, organization_id=org_id)
        standalone = Site(url="https://b.example", project_id=None, organization_id=org_id)
        recipient = Recipient(
            email="primary@example.com", name="Primary", active=True, organization_id=org_id
        )
        session.add_all([project_site, standalone, recipient])
        await session.commit()
        return Fixture(org_id, project.id, project_site.id, standalone.id, recipient.id)


async def _add_cover(
    database: Database,
    fixture: Fixture,
    *,
    start: str = "2026-06-10",
    end: str = "2026-06-20",
    project_id: int | None = None,
    site_id: int | None = None,
    email: str = "cover@example.com",
) -> None:
    async with database.session() as session:
        session.add(
            RecipientSubstitution(
                recipient_id=fixture.recipient_id,
                project_id=project_id,
                site_id=site_id,
                substitute_email=email,
                substitute_name="Cover",
                start_date=start,
                end_date=end,
            )
        )
        await session.commit()


async def _targets(database: Database, fixture: Fixture, site_id: int, on: date) -> list[tuple]:
    async with database.session() as session:
        recipient = await session.get(Recipient, fixture.recipient_id)
        site = await session.get(Site, site_id)
        assert recipient is not None and site is not None
        return await resolve_send_targets(session, [recipient], on, site)


async def test_unscoped_cover_redirects_within_range(database: Database) -> None:
    fixture = await _setup(database)
    await _add_cover(database, fixture)
    targets = await _targets(database, fixture, fixture.standalone_site_id, date(2026, 6, 17))
    assert targets == [("cover@example.com", "Cover")]


async def test_cover_ignored_outside_range(database: Database) -> None:
    fixture = await _setup(database)
    await _add_cover(database, fixture)
    targets = await _targets(database, fixture, fixture.standalone_site_id, date(2026, 7, 1))
    assert targets == [("primary@example.com", "Primary")]


async def test_site_scoped_cover_applies_only_to_its_site(database: Database) -> None:
    fixture = await _setup(database)
    await _add_cover(database, fixture, site_id=fixture.project_site_id)
    on = date(2026, 6, 17)
    redirected = await _targets(database, fixture, fixture.project_site_id, on)
    untouched = await _targets(database, fixture, fixture.standalone_site_id, on)
    assert redirected == [("cover@example.com", "Cover")]
    assert untouched == [("primary@example.com", "Primary")]


async def test_project_scoped_cover_applies_to_sites_in_project(database: Database) -> None:
    fixture = await _setup(database)
    await _add_cover(database, fixture, project_id=fixture.project_id)
    on = date(2026, 6, 17)
    in_project = await _targets(database, fixture, fixture.project_site_id, on)
    outside = await _targets(database, fixture, fixture.standalone_site_id, on)
    assert in_project == [("cover@example.com", "Cover")]
    assert outside == [("primary@example.com", "Primary")]


async def test_more_specific_cover_wins(database: Database) -> None:
    fixture = await _setup(database)
    await _add_cover(database, fixture, email="global@example.com")
    await _add_cover(database, fixture, site_id=fixture.project_site_id, email="site@example.com")
    targets = await _targets(database, fixture, fixture.project_site_id, date(2026, 6, 17))
    assert targets == [("site@example.com", "Cover")]


async def test_substitution_crud_via_api(admin_client: httpx.AsyncClient) -> None:
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "lead@example.com"})
    ).json()["id"]

    created = await admin_client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "stand-in@example.com",
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["project_id"] is None and body["site_id"] is None
    substitution_id = body["id"]

    listed = await admin_client.get(f"/api/recipients/{recipient_id}/substitutions")
    assert [s["id"] for s in listed.json()] == [substitution_id]

    assert (
        await admin_client.delete(f"/api/recipients/substitutions/{substitution_id}")
    ).status_code == 204


async def test_project_scoped_substitution_via_api(admin_client: httpx.AsyncClient) -> None:
    project_id = (await admin_client.post("/api/projects", json={"name": "Ops"})).json()["id"]
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "ops-lead@example.com"})
    ).json()["id"]

    created = await admin_client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "ops-cover@example.com",
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
            "project_id": project_id,
        },
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == project_id


async def test_substitution_rejects_both_scopes(admin_client: httpx.AsyncClient) -> None:
    project_id = (await admin_client.post("/api/projects", json={"name": "P"})).json()["id"]
    site_id = (
        await admin_client.post(
            "/api/sites", json={"url": "https://x.example", "project_id": project_id}
        )
    ).json()["id"]
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "both@example.com"})
    ).json()["id"]
    response = await admin_client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "x@example.com",
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
            "project_id": project_id,
            "site_id": site_id,
        },
    )
    assert response.status_code == 422


async def test_substitution_rejects_unknown_scope(admin_client: httpx.AsyncClient) -> None:
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "ghost@example.com"})
    ).json()["id"]
    response = await admin_client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "x@example.com",
            "start_date": "2026-08-01",
            "end_date": "2026-08-14",
            "project_id": 999_999,
        },
    )
    assert response.status_code == 404


async def test_substitution_rejects_reversed_range(admin_client: httpx.AsyncClient) -> None:
    recipient_id = (
        await admin_client.post("/api/recipients", json={"email": "lead2@example.com"})
    ).json()["id"]
    response = await admin_client.post(
        f"/api/recipients/{recipient_id}/substitutions",
        json={
            "substitute_email": "x@example.com",
            "start_date": "2026-08-20",
            "end_date": "2026-08-01",
        },
    )
    assert response.status_code == 422
