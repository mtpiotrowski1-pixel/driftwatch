"""OpenAI usage and cost summary, broken down by model, month, site, and project,
plus the human-vs-AI verdict agreement rollup."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import String, case, cast, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from driftwatch.api.deps import CurrentUser, SessionDep
from driftwatch.models import AIUsage, ChangeEvent, Project, Site
from driftwatch.schemas import (
    UsageBucket,
    UsageByModel,
    UsageSummary,
    VerdictAccuracyBucket,
    VerdictAccuracySummary,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])

_TOKENS = func.coalesce(func.sum(AIUsage.total_tokens), 0)
_COST = func.coalesce(func.sum(AIUsage.cost_usd), 0.0)
_CALLS = func.count(AIUsage.id)
_UNKNOWN = func.coalesce(func.sum(case((AIUsage.cost_usd.is_(None), 1), else_=0)), 0)


# AIUsage carries immutable organization ownership, so totals survive deletion
# of their Site. The session-level tenant criterion scopes these aggregates;
# site/project joins are used only for optional labels and drill-downs.
@router.get("/summary", response_model=UsageSummary)
async def summary(session: SessionDep, _: CurrentUser) -> UsageSummary:
    totals = (
        await session.execute(select(_COST, _TOKENS, _CALLS, _UNKNOWN).where(_usage_scope(session)))
    ).one()
    return UsageSummary(
        total_cost_usd=None if totals[3] else round(totals[0], 6),
        known_cost_usd=round(totals[0], 6),
        unknown_cost_calls=totals[3],
        total_tokens=totals[1],
        calls=totals[2],
        by_model=await _by_model(session),
        by_month=await _by_month(session),
        by_site=await _by_site(session),
        by_project=await _by_project(session),
    )


async def _by_model(session: AsyncSession) -> list[UsageByModel]:
    rows = await session.execute(
        select(AIUsage.model, _CALLS, _TOKENS, _COST, _UNKNOWN)
        .where(_usage_scope(session))
        .group_by(AIUsage.model)
        .order_by(_COST.desc())
    )
    return [
        UsageByModel(
            model=model,
            calls=calls,
            total_tokens=tokens,
            cost_usd=None if unknown else round(cost, 6),
            known_cost_usd=round(cost, 6),
            unknown_cost_calls=unknown,
        )
        for model, calls, tokens, cost, unknown in rows
    ]


async def _by_month(session: AsyncSession) -> list[UsageBucket]:
    # Portable "YYYY-MM" bucket: both SQLite (ISO text storage) and Postgres
    # render the timestamp ISO-first, so its leading 7 characters are the year
    # and month. Avoids SQLite-only strftime and Postgres-only to_char.
    month = func.substr(cast(AIUsage.created_at, String), 1, 7)
    rows = await session.execute(
        select(month, _CALLS, _TOKENS, _COST, _UNKNOWN)
        .where(_usage_scope(session))
        .group_by(month)
        .order_by(month.desc())
    )
    return [
        _bucket(label, calls, tokens, cost, unknown)
        for label, calls, tokens, cost, unknown in rows
        if label
    ]


async def _by_site(session: AsyncSession) -> list[UsageBucket]:
    name = func.coalesce(Site.name, Site.url)
    rows = await session.execute(
        select(name, _CALLS, _TOKENS, _COST, _UNKNOWN)
        .join(Site, Site.id == AIUsage.site_id)
        .where(_usage_scope(session))
        .group_by(Site.id, name)
        .order_by(_COST.desc())
    )
    return [
        _bucket(label, calls, tokens, cost, unknown) for label, calls, tokens, cost, unknown in rows
    ]


async def _by_project(session: AsyncSession) -> list[UsageBucket]:
    rows = await session.execute(
        select(Project.name, _CALLS, _TOKENS, _COST, _UNKNOWN)
        .join(Site, Site.id == AIUsage.site_id)
        .join(Project, Project.id == Site.project_id)
        .where(_usage_scope(session))
        .group_by(Project.id, Project.name)
        .order_by(_COST.desc())
    )
    return [
        _bucket(label, calls, tokens, cost, unknown) for label, calls, tokens, cost, unknown in rows
    ]


def _bucket(label: object, calls: int, tokens: int, cost: float, unknown: int) -> UsageBucket:
    return UsageBucket(
        label=str(label),
        calls=calls,
        total_tokens=tokens,
        cost_usd=None if unknown else round(cost, 6),
        known_cost_usd=round(cost, 6),
        unknown_cost_calls=unknown,
    )


def _usage_scope(session: AsyncSession) -> ColumnElement[bool]:
    info = session.sync_session.info
    if info.get("org_scoped") and not info.get("org_superadmin"):
        org_id = info.get("org_id")
        return AIUsage.organization_id == org_id
    return true()


@router.get("/verdicts", response_model=VerdictAccuracySummary)
async def verdict_summary(session: SessionDep, _: CurrentUser) -> VerdictAccuracySummary:
    """How often human reviewers agreed with the AI's significance verdicts,
    per site and overall — the feedback loop for tuning importance rules."""
    buckets = await verdict_accuracy(session)
    reviewed = sum(bucket.reviewed for bucket in buckets)
    agreed = sum(bucket.agreed for bucket in buckets)
    return VerdictAccuracySummary(
        reviewed=reviewed,
        agreed=agreed,
        false_positives=sum(bucket.false_positives for bucket in buckets),
        false_negatives=sum(bucket.false_negatives for bucket in buckets),
        agreement_rate=_rate(agreed, reviewed),
        by_site=buckets,
    )


async def verdict_accuracy(session: AsyncSession) -> list[VerdictAccuracyBucket]:
    """Per-site agreement between ``ChangeEvent.significant`` (the AI) and
    ``user_verdict`` (the human), over reviewed changes only. An override of a
    "significant" verdict is a false positive; of a "not significant" one, a
    false negative. The Site join confines the rollup to the caller's org."""
    agreed_case = case(
        (ChangeEvent.user_verdict == ChangeEvent.significant, 1),
        else_=0,
    )
    false_positive = case(
        (ChangeEvent.significant.is_(True) & ChangeEvent.user_verdict.is_(False), 1),
        else_=0,
    )
    false_negative = case(
        (ChangeEvent.significant.is_(False) & ChangeEvent.user_verdict.is_(True), 1),
        else_=0,
    )
    name = func.coalesce(Site.name, Site.url)
    rows = await session.execute(
        select(
            Site.id,
            name,
            func.count(ChangeEvent.id),
            func.sum(agreed_case),
            func.sum(false_positive),
            func.sum(false_negative),
        )
        .join(Site, Site.id == ChangeEvent.site_id)
        .where(ChangeEvent.user_verdict.is_not(None), ChangeEvent.significant.is_not(None))
        .group_by(Site.id, name)
        .order_by(name)
    )
    return [
        VerdictAccuracyBucket(
            site_id=site_id,
            label=str(label),
            reviewed=total,
            agreed=agreed or 0,
            false_positives=fp or 0,
            false_negatives=fn or 0,
            agreement_rate=_rate(agreed or 0, total),
        )
        for site_id, label, total, agreed, fp, fn in rows
    ]


def _rate(agreed: int, reviewed: int) -> float:
    return round(agreed / reviewed, 4) if reviewed else 0.0
