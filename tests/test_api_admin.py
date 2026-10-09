"""Tests for the admin log and backup endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

import driftwatch.api.admin as admin_api
from driftwatch.db import Database, snapshot_sqlite
from driftwatch.models import Organization


class _UnreadableBody(httpx.AsyncByteStream):
    async def __aiter__(self):  # type: ignore[no-untyped-def]
        raise AssertionError("unauthorized restore request body was consumed")
        yield b""  # pragma: no cover


async def test_raw_process_logs_are_not_exposed_in_product(
    admin_client: httpx.AsyncClient,
) -> None:
    assert (await admin_client.get("/api/logs/recent")).status_code == 404
    assert (await admin_client.get("/api/logs")).status_code == 404


async def test_admin_capabilities_report_sqlite_controls(
    admin_client: httpx.AsyncClient,
) -> None:
    response = await admin_client.get("/api/admin/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "database_backend": "sqlite",
        "sqlite_backup_restore": True,
        "raw_logs_in_product": False,
    }


async def test_backup_requires_step_up(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/admin/backup")).status_code == 428


async def test_backup_serves_sqlite_file_after_step_up(admin_client: httpx.AsyncClient) -> None:
    step_up = await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    assert step_up.status_code == 204
    response = await admin_client.get("/api/admin/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content[:15] == b"SQLite format 3"


async def test_admin_endpoints_require_admin(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )  # session is now the member
    assert (await client.get("/api/admin/capabilities")).status_code == 403
    assert (await client.get("/api/admin/backup")).status_code == 403
    restore = await client.post(
        "/api/admin/restore",
        content=b"SQLite format 3\x00",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert restore.status_code == 403


async def test_restore_requires_step_up(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/admin/restore",
        content=b"not-a-db",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 428


async def test_restore_rejects_non_sqlite(admin_client: httpx.AsyncClient) -> None:
    await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    response = await admin_client.post(
        "/api/admin/restore",
        content=b"this is not a database",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 400


async def test_backup_then_restore_round_trips(admin_client: httpx.AsyncClient) -> None:
    await admin_client.post("/api/auth/step-up", json={"password": "supersecret123"})
    backup = await admin_client.get("/api/admin/backup")
    assert backup.status_code == 200

    restore = await admin_client.post(
        "/api/admin/restore",
        content=backup.content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert restore.status_code == 200
    assert restore.json()["safety_copy"].endswith(".db")

    # Even an identical snapshot receives fresh auth generations. A cookie from
    # either timeline must not survive the restore.
    assert (await admin_client.get("/api/auth/me")).status_code == 401
    login = await admin_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "supersecret123"},
    )
    assert login.status_code == 200


async def test_unauthenticated_restore_does_not_read_request_body(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/admin/restore",
        content=_UnreadableBody(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 401


async def test_failed_install_reinstalls_and_verifies_safety_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Build two valid but distinguishable databases. The first validation after
    # install is forced to fail; the recovery validation uses the real checker.
    live_path = tmp_path / "live.db"
    staged_path = tmp_path / "staged.db"
    safety_path = tmp_path / "safety.db"
    live = Database(f"sqlite+aiosqlite:///{live_path.as_posix()}")
    staged = Database(f"sqlite+aiosqlite:///{staged_path.as_posix()}")
    await live.create_all()
    await staged.create_all()
    async with live.session() as session:
        session.add(Organization(name="original"))
        await session.commit()
    async with staged.session() as session:
        session.add(Organization(name="replacement"))
        await session.commit()
    await staged.dispose()
    snapshot_sqlite(live_path, safety_path)

    real_validate = admin_api.validate_sqlite_snapshot
    validations = 0

    def fail_installed_database_once(path: Path) -> None:
        nonlocal validations
        validations += 1
        if validations == 1:
            raise ValueError("simulated post-install validation failure")
        real_validate(path)

    monkeypatch.setattr(admin_api, "validate_sqlite_snapshot", fail_installed_database_once)
    with pytest.raises(RuntimeError, match="safety copy was reinstalled"):
        await admin_api._install_with_rollback(live, staged_path, live_path, safety_path)

    async with live.session() as session:
        names = list((await session.execute(select(Organization.name))).scalars())
    assert names == ["original"]
    assert validations == 2
    await live.dispose()
