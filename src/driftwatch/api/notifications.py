"""Read access to the notification delivery audit log."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from driftwatch.api.deps import CurrentUser, SessionDep
from driftwatch.enums import NotificationStatus
from driftwatch.models import ChangeEvent, NotificationLog, Site
from driftwatch.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    session: SessionDep,
    _: CurrentUser,
    status: NotificationStatus | None = None,
    change_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    before_id: int | None = Query(default=None, ge=1),
) -> list[NotificationOut]:
    # The Site join both enriches the rows and confines them to the caller's
    # organization (NotificationLog itself carries no org column), so the
    # change_id filter cannot leak another org's deliveries.
    query = (
        select(NotificationLog, ChangeEvent.headline, Site.id, Site.name, Site.url)
        .join(ChangeEvent, ChangeEvent.id == NotificationLog.change_id)
        .join(Site, Site.id == ChangeEvent.site_id)
        .order_by(NotificationLog.id.desc())
        .limit(limit)
    )
    if status is not None:
        query = query.where(NotificationLog.status == status)
    if before_id is not None:
        query = query.where(NotificationLog.id < before_id)
    if change_id is not None:
        query = query.where(NotificationLog.change_id == change_id)

    notifications: list[NotificationOut] = []
    for log, headline, site_id, site_name, site_url in await session.execute(query):
        entry = NotificationOut.model_validate(log)
        entry.site_id = site_id
        entry.site_name = site_name or site_url
        entry.headline = headline
        notifications.append(entry)
    return notifications
