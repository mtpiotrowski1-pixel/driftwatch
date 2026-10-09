"""Database ownership for one persisted change's AI analysis.

A reservation commits before the provider call. Only its current, unexpired
token can publish a result. A crash leaves a recoverable interrupted marker;
retrying a completed analysis requires the explicit re-analysis operation.
"""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.enums import AnalysisStatus
from driftwatch.models import ChangeEvent
from driftwatch.monitoring.analyzer import AnalysisError

ANALYSIS_TIMEOUT_SECONDS = 90
ANALYSIS_LEASE_SECONDS = 120


class AnalysisOwnershipLost(AnalysisError):
    """A late result cannot replace the current owner's work."""


async def claim_analysis(
    session: AsyncSession, change_id: int, *, now: datetime, force: bool = False
) -> str | None:
    token = str(uuid4())
    expiry = now + timedelta(seconds=ANALYSIS_LEASE_SECONDS)
    statement = update(ChangeEvent).where(
        ChangeEvent.id == change_id,
        or_(
            ChangeEvent.analysis_lease_token.is_(None),
            ChangeEvent.analysis_lease_expires_at <= now,
        ),
    )
    if not force:
        statement = statement.where(
            or_(ChangeEvent.significant.is_(None), ChangeEvent.ai_error.is_not(None))
        )
    claimed = await session.scalar(
        statement.values(
            analysis_status=AnalysisStatus.PROCESSING,
            analysis_lease_token=token,
            analysis_lease_expires_at=expiry,
            ai_error="Analysis interrupted before completion",
            next_retry_at=expiry,
            retry_status=None,
        )
        .returning(ChangeEvent.id)
        .execution_options(synchronize_session=False)
    )
    return token if claimed is not None else None


async def release_analysis(
    session: AsyncSession,
    change_id: int,
    token: str,
    *,
    now: datetime,
    status: AnalysisStatus,
    error: str | None = None,
    next_retry_at: datetime | None = None,
) -> bool:
    released = await session.scalar(
        update(ChangeEvent)
        .where(
            ChangeEvent.id == change_id,
            ChangeEvent.analysis_lease_token == token,
            ChangeEvent.analysis_lease_expires_at > now,
        )
        .values(
            analysis_status=status,
            analysis_lease_token=None,
            analysis_lease_expires_at=None,
            ai_error=error,
            next_retry_at=next_retry_at,
        )
        .returning(ChangeEvent.id)
        .execution_options(synchronize_session=False)
    )
    return released is not None
