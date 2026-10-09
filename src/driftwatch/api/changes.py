"""Read access to detected changes, plus retry, re-analyze, and review actions."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from driftwatch.api.deps import CurrentUser, RunnerDep, SessionDep
from driftwatch.enums import RetryStatus
from driftwatch.exceptions import NotFoundError
from driftwatch.models import AnalysisRun, ChangeEvent, Site, User
from driftwatch.monitoring.analyzer import AnalysisError
from driftwatch.runner import RunResult
from driftwatch.schemas import (
    AnalysisRunOut,
    AnalyzePreviewOut,
    AnalyzePreviewRequest,
    ChangeDetail,
    ChangeOut,
    RunResultOut,
    VerdictUpdate,
)
from driftwatch.security.access import require_site_edit

router = APIRouter(prefix="/api/changes", tags=["changes"])

# List views serialize ChangeOut, which omits the large diff_text/diff_html Text
# columns — load only what's needed so they aren't read from disk per row.
_LIST_COLUMNS = load_only(
    ChangeEvent.site_id,
    ChangeEvent.created_at,
    ChangeEvent.significant,
    ChangeEvent.headline,
    ChangeEvent.summary,
    ChangeEvent.ai_error,
    ChangeEvent.ai_retry_count,
    ChangeEvent.analysis_status,
    ChangeEvent.notification_error,
    ChangeEvent.notification_retry_count,
    ChangeEvent.retry_status,
    ChangeEvent.next_retry_at,
    ChangeEvent.notified_at,
    ChangeEvent.user_verdict,
    ChangeEvent.user_verdict_at,
)


@router.get("", response_model=list[ChangeOut])
async def list_changes(
    session: SessionDep,
    _: CurrentUser,
    site_id: int | None = None,
    significant_only: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    before_id: int | None = Query(default=None, ge=1),
) -> list[ChangeEvent]:
    # Join Site so the org-scope filter (which can't see the column-less
    # ChangeEvent) confines the list to the caller's organization.
    query = (
        select(ChangeEvent)
        .join(Site, Site.id == ChangeEvent.site_id)
        .options(_LIST_COLUMNS)
        .order_by(ChangeEvent.id.desc())
        .limit(limit)
    )
    if site_id is not None:
        query = query.where(ChangeEvent.site_id == site_id)
    if before_id is not None:
        query = query.where(ChangeEvent.id < before_id)
    if significant_only:
        query = query.where(ChangeEvent.significant.is_(True))
    return list((await session.execute(query)).scalars())


@router.get("/action-required", response_model=list[ChangeOut])
async def action_required(session: SessionDep, _: CurrentUser) -> list[ChangeEvent]:
    """Changes whose automatic retries are exhausted or are still failing."""
    query = (
        select(ChangeEvent)
        .join(Site, Site.id == ChangeEvent.site_id)  # confine to the caller's org
        .options(_LIST_COLUMNS)
        .where(
            or_(
                ChangeEvent.retry_status == RetryStatus.REQUIRES_ACTION,
                ChangeEvent.ai_error.is_not(None),
                ChangeEvent.notification_error.is_not(None),
            )
        )
        .order_by(ChangeEvent.created_at.desc())
        .limit(200)
    )
    return list((await session.execute(query)).scalars())


@router.get("/{change_id}", response_model=ChangeDetail)
async def get_change(change_id: int, session: SessionDep, _: CurrentUser) -> ChangeDetail:
    change = await _scoped_change(session, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Change {change_id} not found")
    detail = ChangeDetail.model_validate(change)
    # Newest first, so the head mirrors the verdict shown on the change itself
    # and everything after it is a previous verdict.
    runs = (
        await session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.change_id == change_id)
            .order_by(AnalysisRun.id.desc())
        )
    ).scalars()
    detail.analysis_runs = [AnalysisRunOut.model_validate(run) for run in runs]
    return detail


async def _scoped_change(session: AsyncSession, change_id: int) -> ChangeEvent | None:
    """Fetch a change only if its site is in the caller's org — ChangeEvent carries
    no organization_id, so it's isolated by joining the (org-scoped) Site."""
    return (
        await session.execute(
            select(ChangeEvent)
            .join(Site, Site.id == ChangeEvent.site_id)
            .where(ChangeEvent.id == change_id)
        )
    ).scalar_one_or_none()


@router.post("/{change_id}/retry", response_model=RunResultOut)
async def retry_change(
    change_id: int, session: SessionDep, runner: RunnerDep, user: CurrentUser
) -> RunResult:
    await _require_change_edit(session, user, change_id)
    # Persist support-access audit before a second session performs the work.
    await session.commit()
    try:
        return await runner.reprocess_change(change_id, force_delivery=True)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{change_id}/analyze", response_model=RunResultOut)
async def analyze_change_endpoint(
    change_id: int, session: SessionDep, runner: RunnerDep, user: CurrentUser
) -> RunResult:
    await _require_change_edit(session, user, change_id)
    await session.commit()
    try:
        return await runner.analyze_only(change_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{change_id}/analyze-preview", response_model=AnalyzePreviewOut)
async def analyze_preview_endpoint(
    change_id: int,
    payload: AnalyzePreviewRequest,
    session: SessionDep,
    runner: RunnerDep,
    user: CurrentUser,
) -> AnalyzePreviewOut:
    """Dry-run draft importance rules against this change's diff.

    Returns the verdict the draft rules would produce without persisting
    anything to the change, so rules can be iterated safely. Bills the model
    (and counts toward the AI quota) like any analysis, hence edit access."""
    await _require_change_edit(session, user, change_id)
    await session.commit()
    try:
        analysis = await runner.analyze_preview(change_id, payload.rules)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (AnalysisError, TimeoutError) as exc:
        detail = str(exc) if isinstance(exc, AnalysisError) else "AI analysis timed out"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from exc
    return AnalyzePreviewOut(
        significant=analysis.significant,
        headline=analysis.headline,
        summary=analysis.summary,
        model=analysis.cost.model,
        cost_usd=analysis.cost.cost_usd,
    )


@router.post("/{change_id}/verdict", response_model=ChangeOut)
async def set_user_verdict(
    change_id: int, payload: VerdictUpdate, session: SessionDep, user: CurrentUser
) -> ChangeEvent:
    """Record (or clear) the human review of the AI's significance verdict.

    The AI's own ``significant`` is never touched — the review is stored beside
    it so per-site accuracy can be measured. Feedback shapes how the site's
    rules should evolve, so it demands the same edit access as re-analysis."""
    change = await _require_change_edit(session, user, change_id)
    if change.significant is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This change has no AI verdict to review yet")
    change.user_verdict = payload.verdict
    change.user_verdict_at = datetime.now(UTC) if payload.verdict is not None else None
    change.user_verdict_user_id = user.id if payload.verdict is not None else None
    return change


async def _require_change_edit(session: AsyncSession, user: User, change_id: int) -> ChangeEvent:
    """Re-analysis and retry re-bill the model and re-send email, so they require
    edit access to the change's site — not merely a signed-in account. The site
    join also confines this to the caller's organization."""
    change = await _scoped_change(session, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Change {change_id} not found")
    site = await session.get(Site, change.site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Change {change_id} not found")
    await require_site_edit(session, user, site)
    return change
