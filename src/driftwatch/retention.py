"""Bound stored history per site.

Snapshots are large (full cleaned HTML), so old ones are pruned. The catch is
that a :class:`ChangeEvent` references the snapshots on either side of its diff,
so pruning must not orphan a surviving change. The diff text and HTML are stored
on the change itself, so the diff view keeps working even after its snapshots go.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from driftwatch.enums import AnalysisStatus, NotificationDeliveryStatus
from driftwatch.models import (
    AIUsage,
    ChangeEvent,
    NotificationDelivery,
    NotificationOutbox,
    Snapshot,
)


async def prune_ai_usage(session: AsyncSession, *, older_than_days: int) -> int:
    """Delete AI usage rows older than the retention window so the table — the
    one that grows on every analyzed change with no other cleanup path — stays
    bounded over months of operation. ``created_at`` is indexed."""
    # Naive UTC cutoff to match SQLite's naive-stored datetimes.
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than_days)
    result = cast(
        CursorResult[object],
        await session.execute(delete(AIUsage).where(AIUsage.created_at < cutoff)),
    )
    return result.rowcount or 0


async def prune_site_history(session: AsyncSession, site_id: int, *, keep: int) -> int:
    """Prune resolved history, retaining the evidence for unfinished work.

    The snapshot count is a target, not permission to abandon pending analysis,
    required delivery or an incident awaiting an operator's action.
    """
    if keep < 1:
        raise ValueError("keep must be positive")
    keep_ids = list(
        (
            await session.execute(
                select(Snapshot.id)
                .where(Snapshot.site_id == site_id)
                .order_by(Snapshot.id.desc())
                .limit(keep)
            )
        ).scalars()
    )
    if not keep_ids:
        return 0

    await session.execute(
        delete(ChangeEvent).where(
            ChangeEvent.site_id == site_id,
            ChangeEvent.new_snapshot_id.notin_(keep_ids),
            ~_unfinished_change(),
        )
    )

    referenced = await _referenced_snapshot_ids(session, site_id)
    survivors = set(keep_ids) | referenced
    result = cast(
        CursorResult[object],
        await session.execute(
            delete(Snapshot).where(
                Snapshot.site_id == site_id,
                Snapshot.id.notin_(survivors),
            )
        ),
    )
    return result.rowcount or 0


def _unfinished_change() -> ColumnElement[bool]:
    unfinished_outbox = exists(
        select(NotificationOutbox.id).where(
            NotificationOutbox.change_id == ChangeEvent.id,
            or_(
                NotificationOutbox.completed_at.is_(None),
                exists(
                    select(NotificationDelivery.id).where(
                        NotificationDelivery.outbox_id == NotificationOutbox.id,
                        NotificationDelivery.status != NotificationDeliveryStatus.SENT,
                    )
                ),
            ),
        )
    )
    return or_(
        ChangeEvent.analysis_status.in_(
            (
                AnalysisStatus.PENDING,
                AnalysisStatus.PROCESSING,
                AnalysisStatus.ERROR,
                AnalysisStatus.QUOTA_BLOCKED,
            )
        ),
        ChangeEvent.analysis_lease_token.is_not(None),
        ChangeEvent.ai_error.is_not(None),
        ChangeEvent.notification_error.is_not(None),
        ChangeEvent.next_retry_at.is_not(None),
        ChangeEvent.retry_status.is_not(None),
        unfinished_outbox,
    )


async def _referenced_snapshot_ids(session: AsyncSession, site_id: int) -> set[int]:
    rows = await session.execute(
        select(ChangeEvent.old_snapshot_id, ChangeEvent.new_snapshot_id).where(
            ChangeEvent.site_id == site_id
        )
    )
    referenced: set[int] = set()
    for old_id, new_id in rows:
        if old_id is not None:
            referenced.add(old_id)
        referenced.add(new_id)
    return referenced
