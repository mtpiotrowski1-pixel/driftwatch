"""Operator capabilities and guarded SQLite backup/restore."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from driftwatch.api.deps import (
    DatabaseDep,
    InstanceSuperadminUser,
    MaintenanceDep,
    SchedulerDep,
    SessionDep,
    SettingsDep,
    StepUpUser,
)
from driftwatch.audit import record_audit_event
from driftwatch.db import (
    Database,
    overwrite_sqlite,
    snapshot_sqlite,
    sqlite_file_path,
    validate_sqlite_snapshot,
)
from driftwatch.exceptions import InvalidRequest
from driftwatch.models import User

logger = logging.getLogger(__name__)

# A restore upload larger than this is refused before it is written to disk.
MAX_RESTORE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB

router = APIRouter(prefix="/api", tags=["admin"])


def _audit(request: Request, admin: User, action: str) -> None:
    """Leave a forensic record for sensitive operations (the backup holds password
    hashes and recoverable secrets; a restore replaces the whole database)."""
    _audit_identity(request, user_id=admin.id, email=admin.email, action=action)


def _audit_identity(request: Request, *, user_id: int, email: str, action: str) -> None:
    client = request.client.host if request.client else "unknown"
    logger.warning("admin %s: user_id=%s email=%s from=%s", action, user_id, email, client)


def _require_sqlite_path(settings: SettingsDep, action: str) -> Path:
    db_path = sqlite_file_path(settings.database_url)
    if db_path is None:
        raise InvalidRequest(f"{action} is only available on the SQLite backend")
    return db_path


@router.get("/admin/capabilities")
async def admin_capabilities(
    settings: SettingsDep,
    _: InstanceSuperadminUser,
) -> dict[str, str | bool]:
    """Tell the operator UI which deployment-specific controls are valid."""
    sqlite = sqlite_file_path(settings.database_url) is not None
    return {
        "database_backend": "sqlite" if sqlite else "postgresql",
        "sqlite_backup_restore": sqlite,
        # Raw process logs belong in access-controlled observability, not in a
        # product endpoint. The audit ledger is the in-product forensic surface.
        "raw_logs_in_product": False,
    }


@router.get("/admin/backup")
async def download_backup(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> FileResponse:
    """Download a consistent snapshot of the SQLite database.

    The snapshot is taken with SQLite's online-backup API, so it captures
    committed pages still in the WAL that a raw file copy would miss. The file
    contains password hashes and encrypted secrets, so it requires a fresh
    re-authentication (step-up) and every download is audit-logged.
    """
    db_path = _require_sqlite_path(settings, "Backup download")
    if not db_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Database file not found")
    snapshot = _temp_db(db_path.parent, "driftwatch-backup-")
    try:
        await to_thread.run_sync(snapshot_sqlite, db_path, snapshot)
        record_audit_event(
            session,
            request,
            admin,
            action="backup.downloaded",
            target_type="database_backup",
            organization_id=None,
            target_label="driftwatch-backup.db",
        )
        # The response background task only runs after the file is sent. Own
        # this commit here so a failure cannot leave an untracked backup file.
        await session.commit()
        session.sync_session.info["skip_final_commit"] = True
        _audit(request, admin, "backup download")
        return FileResponse(
            snapshot,
            media_type="application/octet-stream",
            filename="driftwatch-backup.db",
            background=BackgroundTask(snapshot.unlink, missing_ok=True),
        )
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


@router.post("/admin/restore", status_code=status.HTTP_200_OK)
async def restore_backup(
    request: Request,
    settings: SettingsDep,
    db: DatabaseDep,
    session: SessionDep,
    scheduler: SchedulerDep,
    maintenance: MaintenanceDep,
    admin: InstanceSuperadminUser,
    _: StepUpUser,
) -> dict[str, str]:
    """Replace the live database with an uploaded snapshot.

    The upload is validated as an intact SQLite database carrying the expected
    tables before anything is touched; the current database is snapshotted to a
    timestamped safety copy first; then its contents are overwritten in place and
    the engine pool is reset. Requires step-up and is audit-logged. The caller's
    session may end here — log back in afterwards.
    """
    db_path = _require_sqlite_path(settings, "Restore")
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/octet-stream":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Restore requires an application/octet-stream request body",
        )
    admin_id, admin_email = admin.id, admin.email
    staged = _temp_db(db_path.parent, "driftwatch-restore-")
    try:
        await _stream_upload(request, staged)
        try:
            await to_thread.run_sync(validate_sqlite_snapshot, staged)
        except ValueError as exc:
            raise InvalidRequest(f"Restore rejected: {exc}") from exc

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        safety = db_path.with_name(f"{db_path.stem}-pre-restore-{stamp}.db")

        # Migrate the staged copy before it becomes live, then write the restore
        # event into that copy. Recording against the old live database would be
        # erased by the overwrite and would leave no forensic trail afterwards.
        staged_db = Database(f"sqlite+aiosqlite:///{staged.as_posix()}")
        try:
            await staged_db.upgrade()
            async with staged_db.session() as staged_session:
                await _rotate_session_generations(staged_session)
                record_audit_event(
                    staged_session,
                    request,
                    admin,
                    action="backup.restored",
                    target_type="database_backup",
                    organization_id=None,
                    target_label="uploaded-backup.db",
                    details={"safety_copy": safety.name},
                )
                await staged_session.commit()
        finally:
            await staged_db.dispose()

        # Stop accepting normal HTTP work, drain requests that were already in
        # flight, then pause and drain the scheduler. Only the restore request is
        # allowed to remain while the SQLite file is replaced.
        async with maintenance.exclusive(), scheduler.paused_for_maintenance():
            # Authentication dependencies used this request session. Close its
            # transaction before disposing the engine and tell the dependency
            # finalizer not to reopen/commit it against the restored database.
            await session.rollback()
            session.sync_session.info["skip_final_commit"] = True
            await session.close()

            # Capture the true pre-restore state only after every writer drained.
            await to_thread.run_sync(snapshot_sqlite, db_path, safety)
            await _install_with_rollback(db, staged, db_path, safety)
        _audit_identity(
            request,
            user_id=admin_id,
            email=admin_email,
            action=f"backup restore (safety copy {safety.name})",
        )
        return {"safety_copy": safety.name}
    finally:
        staged.unlink(missing_ok=True)


async def _rotate_session_generations(session: AsyncSession) -> None:
    """Invalidate every auth token carried across a database restore."""
    user_ids = list((await session.execute(select(User.id))).scalars())
    if not user_ids:
        return
    await session.execute(
        text("UPDATE users SET session_generation = :session_generation WHERE id = :user_id"),
        [{"user_id": user_id, "session_generation": str(uuid4())} for user_id in user_ids],
    )


def _temp_db(directory: Path, prefix: str) -> Path:
    """A unique empty file beside the live database, on the same filesystem."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".db", dir=directory)
    os.close(fd)
    return Path(name)


async def _stream_upload(request: Request, dest: Path) -> None:
    written = 0
    with dest.open("wb") as out:
        async for chunk in request.stream():
            written += len(chunk)
            if written > MAX_RESTORE_BYTES:
                raise InvalidRequest("Restore upload exceeds the maximum allowed size")
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())


async def _install_with_rollback(
    db: Database,
    staged: Path,
    live: Path,
    safety: Path,
) -> None:
    """Install a staged SQLite snapshot and restore the safety copy on failure."""
    await db.dispose()
    try:
        await to_thread.run_sync(overwrite_sqlite, staged, live)
        await to_thread.run_sync(validate_sqlite_snapshot, live)
        await db.ping()
    except Exception as install_error:
        logger.exception("restored database failed validation; rolling back to safety copy")
        try:
            await db.dispose()
            await to_thread.run_sync(overwrite_sqlite, safety, live)
            await to_thread.run_sync(validate_sqlite_snapshot, live)
            await db.ping()
        except Exception as rollback_error:
            logger.critical("database restore rollback failed", exc_info=True)
            raise RuntimeError(
                "Database restore failed and the safety copy could not be reinstalled"
            ) from rollback_error
        raise RuntimeError(
            "Database restore failed; the safety copy was reinstalled"
        ) from install_error
