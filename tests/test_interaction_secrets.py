"""Interaction fill values remain encrypted outside the capture boundary."""

from __future__ import annotations

import html
import io
import logging
import sqlite3
import zipfile
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import InteractionSecret, Site, Snapshot
from driftwatch.monitoring.capture import CaptureError
from driftwatch.monitoring.pipeline import capture_and_store
from driftwatch.schemas import InteractionStepIn
from driftwatch.security.crypto import SecretBox
from driftwatch.security.interaction_secrets import replace_site_interaction_steps
from tests.conftest import ScriptedCapturer, create_org

_SECRET = "vault-only-s3cret-value"


async def _create_site_with_secret(
    client: httpx.AsyncClient, secret: str = _SECRET
) -> dict[str, object]:
    response = await client.post(
        "/api/sites",
        json={
            "url": "https://example.test/private",
            "interaction_steps": [
                {
                    "action": "fill",
                    "selector": "#access-token",
                    "secret_value": secret,
                },
                {"action": "click", "selector": "#submit"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert secret not in response.text
    return response.json()


async def test_secret_is_redacted_from_api_database_backup_export_and_logs(
    admin_client: httpx.AsyncClient,
    settings: Settings,
    capturer: ScriptedCapturer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    created = await _create_site_with_secret(admin_client)
    site_id = int(created["id"])
    fill = created["interaction_steps"][0]  # type: ignore[index]
    assert fill == {
        "action": "fill",
        "selector": "#access-token",
        "timeout_ms": 10_000,
        "secret_ref": fill["secret_ref"],  # type: ignore[index]
        "has_secret": True,
    }
    assert "value" not in fill
    assert "secret_value" not in fill

    listed = await admin_client.get("/api/sites")
    fetched = await admin_client.get(f"/api/sites/{site_id}")
    assert _SECRET not in listed.text
    assert _SECRET not in fetched.text

    db_path = Path(settings.database_url.split("///", 1)[1])
    with sqlite3.connect(db_path) as connection:
        stored_steps = connection.execute(
            "SELECT interaction_steps FROM sites WHERE id = ?", (site_id,)
        ).fetchone()[0]
        ciphertext = connection.execute(
            "SELECT ciphertext FROM interaction_secrets WHERE site_id = ?", (site_id,)
        ).fetchone()[0]
    assert _SECRET not in stored_steps
    assert _SECRET not in ciphertext
    assert "secret_ref" in stored_steps

    baseline = await admin_client.post(f"/api/sites/{site_id}/check")
    assert baseline.status_code == 200
    assert baseline.json()["status"] == "baseline"
    assert capturer.interaction_calls[-1][0]["value"] == _SECRET
    assert _SECRET not in baseline.text

    exported = await admin_client.get("/api/exports/changes.xlsx")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as workbook:
        exported_xml = b"".join(workbook.read(name) for name in workbook.namelist())
    assert _SECRET.encode() not in exported_xml

    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204
    backup = await admin_client.get("/api/admin/backup")
    assert backup.status_code == 200
    assert _SECRET.encode() not in backup.content
    # Raw process logs are deliberately not exposed through the product API.
    assert (await admin_client.get("/api/logs/recent")).status_code == 404
    if settings.log_file.exists():
        assert _SECRET not in settings.log_file.read_text(encoding="utf-8")
    assert _SECRET not in caplog.text


async def test_update_reuses_rotates_and_removes_only_owned_references(
    admin_client: httpx.AsyncClient, settings: Settings
) -> None:
    created = await _create_site_with_secret(admin_client)
    site_id = int(created["id"])
    reference = created["interaction_steps"][0]["secret_ref"]  # type: ignore[index]

    renamed = await admin_client.patch(f"/api/sites/{site_id}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["interaction_steps"][0]["secret_ref"] == reference

    reused = await admin_client.patch(
        f"/api/sites/{site_id}",
        json={
            "interaction_steps": [
                {
                    "action": "fill",
                    "selector": "#access-token",
                    "secret_ref": reference,
                }
            ]
        },
    )
    assert reused.status_code == 200, reused.text
    assert reused.json()["interaction_steps"][0]["secret_ref"] == reference

    other_site = await admin_client.post("/api/sites", json={"url": "https://example.test/other"})
    rejected = await admin_client.patch(
        f"/api/sites/{other_site.json()['id']}",
        json={
            "interaction_steps": [{"action": "fill", "selector": "#token", "secret_ref": reference}]
        },
    )
    assert rejected.status_code == 400
    assert reference not in rejected.text

    replacement = "rotated-secret-value"
    rotated = await admin_client.patch(
        f"/api/sites/{site_id}",
        json={
            "interaction_steps": [
                {
                    "action": "fill",
                    "selector": "#access-token",
                    "secret_value": replacement,
                }
            ]
        },
    )
    assert rotated.status_code == 200, rotated.text
    new_reference = rotated.json()["interaction_steps"][0]["secret_ref"]
    assert new_reference != reference
    assert replacement not in rotated.text

    db_path = Path(settings.database_url.split("///", 1)[1])
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, ciphertext FROM interaction_secrets WHERE site_id = ?", (site_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == new_reference
    assert replacement not in rows[0][1]

    cleared = await admin_client.patch(f"/api/sites/{site_id}", json={"interaction_steps": []})
    assert cleared.status_code == 200
    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT count(*) FROM interaction_secrets WHERE site_id = ?", (site_id,)
        ).fetchone()[0]
    assert count == 0


async def test_capture_errors_cannot_echo_a_resolved_secret(
    database: Database, settings: Settings
) -> None:
    class EchoingFailure:
        async def capture(
            self,
            *,
            url: str,
            css_selector: str | None = None,
            interaction_steps: list[dict[str, object]] | None = None,
        ) -> str:
            assert interaction_steps is not None
            raise CaptureError(f"browser rejected {interaction_steps[0]['value']}")

    box = SecretBox(settings.secret_key)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test", interaction_steps=[])
        session.add(site)
        await session.flush()
        await replace_site_interaction_steps(
            session,
            box,
            site,
            [InteractionStepIn(action="fill", selector="#token", secret_value=_SECRET)],
        )
        with pytest.raises(CaptureError) as raised:
            await capture_and_store(session, site, capturer=EchoingFailure(), secret_box=box)

    assert str(raised.value) == "browser rejected [REDACTED]"
    assert _SECRET not in repr(raised.value)


async def test_capture_cannot_persist_a_reflected_fill_secret(
    database: Database, settings: Settings
) -> None:
    class ReflectingCapture:
        async def capture(
            self,
            *,
            url: str,
            css_selector: str | None = None,
            interaction_steps: list[dict[str, object]] | None = None,
        ) -> str:
            assert interaction_steps is not None
            value = interaction_steps[0]["value"]
            return f"<main><p>{value}</p><span>public content</span></main>"

    box = SecretBox(settings.secret_key)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test", interaction_steps=[])
        session.add(site)
        await session.flush()
        await replace_site_interaction_steps(
            session,
            box,
            site,
            [InteractionStepIn(action="fill", selector="#token", secret_value=_SECRET)],
        )

        snapshot_id = await capture_and_store(
            session,
            site,
            capturer=ReflectingCapture(),
            secret_box=box,
        )
        snapshot = await session.get(Snapshot, snapshot_id)

    assert snapshot is not None
    assert _SECRET not in snapshot.content_html
    assert _SECRET not in snapshot.content_text
    assert "[REDACTED]" in snapshot.content_html


@pytest.mark.parametrize("encoding", ["text", "attribute", "numeric"])
async def test_html_entities_cannot_reintroduce_a_fill_secret(
    database: Database,
    settings: Settings,
    encoding: str,
) -> None:
    secret = "synthetic'&\"token"
    if encoding == "numeric":
        echoed = "".join(f"&#{ord(char)};" for char in secret)
    else:
        echoed = html.escape(secret, quote=encoding == "attribute")
    markup = (
        f'<main><a href="https://example.test/{echoed}">Public link</a><div>{echoed}</div></main>'
    )
    box = SecretBox(settings.secret_key)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test", interaction_steps=[])
        session.add(site)
        await session.flush()
        await replace_site_interaction_steps(
            session,
            box,
            site,
            [InteractionStepIn(action="fill", selector="#token", secret_value=secret)],
        )
        snapshot_id = await capture_and_store(
            session, site, capturer=ScriptedCapturer(html=markup), secret_box=box
        )
        snapshot = await session.get(Snapshot, snapshot_id)
        assert snapshot is not None
        assert secret not in html.unescape(snapshot.content_html)
        assert secret not in snapshot.content_text
        assert "[REDACTED]" in snapshot.content_text


async def test_invalid_fill_request_does_not_echo_secret(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/sites",
        json={
            "url": "https://example.test",
            "interaction_steps": [{"action": "fill", "selector": "", "secret_value": _SECRET}],
        },
    )
    assert response.status_code == 422
    assert _SECRET not in response.text


async def test_ciphertext_is_bound_to_its_reference(database: Database, settings: Settings) -> None:
    box = SecretBox(settings.secret_key)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test", interaction_steps=[])
        session.add(site)
        await session.flush()
        await replace_site_interaction_steps(
            session,
            box,
            site,
            [
                InteractionStepIn(action="fill", selector="#a", secret_value="first"),
                InteractionStepIn(action="fill", selector="#b", secret_value="second"),
            ],
        )
        rows = list(
            (
                await session.execute(
                    select(InteractionSecret).where(InteractionSecret.site_id == site.id)
                )
            ).scalars()
        )
        rows[0].ciphertext, rows[1].ciphertext = rows[1].ciphertext, rows[0].ciphertext

        with pytest.raises(CaptureError, match="cannot be decrypted"):
            await capture_and_store(session, site, capturer=ScriptedCapturer(), secret_box=box)
