"""Site CRUD and the manual "check now" action."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.api.deps import (
    CurrentUser,
    OrgContext,
    SchedulerDep,
    SecretBoxDep,
    SessionDep,
    SettingsDep,
)
from driftwatch.enums import AnalysisMode, NotificationMode
from driftwatch.exceptions import InvalidRequest
from driftwatch.models import ChangeEvent, Project, Site
from driftwatch.quota import release_site_slot, reserve_site_slot
from driftwatch.runner import RunResult
from driftwatch.schemas import EffectiveRulesOut, RunResultOut, SiteCreate, SiteOut, SiteUpdate
from driftwatch.security.access import (
    require_project_edit,
    require_site_create,
    require_site_edit,
)
from driftwatch.security.interaction_secrets import replace_site_interaction_steps
from driftwatch.security.origins import http_origin
from driftwatch.security.urls import validate_public_url
from driftwatch.services import (
    effective_importance_rules,
    set_site_recipients,
    site_recipient_ids,
)

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=list[SiteOut])
async def list_sites(session: SessionDep, _: CurrentUser) -> list[SiteOut]:
    sites = list((await session.execute(select(Site).order_by(Site.created_at.desc()))).scalars())
    return await _serialize(session, sites)


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreate,
    session: SessionDep,
    user: CurrentUser,
    org_id: OrgContext,
    box: SecretBoxDep,
) -> SiteOut:
    await require_site_create(session, user, payload.project_id)
    url = await validate_public_url(payload.url)
    await reserve_site_slot(session, org_id)
    site = Site(
        organization_id=org_id,
        url=url,
        name=payload.name,
        project_id=payload.project_id,
        css_selector=payload.css_selector,
        prompt=payload.prompt,
        interaction_steps=[],
        ignore_selectors=payload.ignore_selectors,
        check_interval_minutes=payload.check_interval_minutes,
        enabled=payload.enabled,
        notification_mode=payload.notification_mode,
        analysis_mode=payload.analysis_mode,
    )
    session.add(site)
    await session.flush()
    await replace_site_interaction_steps(session, box, site, payload.interaction_steps)
    await set_site_recipients(session, site.id, payload.recipient_ids)
    return (await _serialize(session, [site]))[0]


# Registered before /{site_id} so the literal path is not captured by the
# parameterised route (which would 422 on the non-numeric segment).
@router.get("/effective-rules", response_model=EffectiveRulesOut)
async def inherited_effective_rules(
    session: SessionDep, _: CurrentUser, box: SecretBoxDep
) -> EffectiveRulesOut:
    """The rules a site with no overrides (and no project yet) inherits — what
    the add-site form shows before a project is chosen."""
    org_id = session.sync_session.info.get("org_id")
    rules = await effective_importance_rules(session, box, org_id=org_id)
    return EffectiveRulesOut(source=rules.source, text=rules.text)


@router.get("/{site_id}/effective-rules", response_model=EffectiveRulesOut)
async def site_effective_rules(
    site_id: int, session: SessionDep, _: CurrentUser, box: SecretBoxDep
) -> EffectiveRulesOut:
    """The importance rules the analyzer would apply to this site right now,
    resolved through the site -> project -> global -> default chain."""
    site = await _require_site(session, site_id)
    project = await session.get(Project, site.project_id) if site.project_id else None
    rules = await effective_importance_rules(
        session,
        box,
        org_id=site.organization_id,
        site_prompt=site.prompt,
        project_prompt=project.prompt if project else None,
    )
    return EffectiveRulesOut(source=rules.source, text=rules.text)


@router.get("/{site_id}", response_model=SiteOut)
async def get_site(site_id: int, session: SessionDep, _: CurrentUser) -> SiteOut:
    site = await _require_site(session, site_id)
    return (await _serialize(session, [site]))[0]


@router.patch("/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: int,
    payload: SiteUpdate,
    session: SessionDep,
    user: CurrentUser,
    box: SecretBoxDep,
) -> SiteOut:
    site = await _require_site(session, site_id)
    await require_site_edit(session, user, site)
    fields = payload.model_dump(exclude_unset=True, exclude={"interaction_steps"})
    recipient_ids = fields.pop("recipient_ids", None)
    interaction_steps = (
        payload.interaction_steps if "interaction_steps" in payload.model_fields_set else None
    )
    analysis_mode = fields.get("analysis_mode", site.analysis_mode)
    notification_mode = fields.get("notification_mode", site.notification_mode)
    if analysis_mode == AnalysisMode.DISABLED and notification_mode != NotificationMode.ALWAYS:
        raise InvalidRequest("Disabled AI requires notification_mode=always")
    if fields.get("url"):
        fields["url"] = await validate_public_url(fields["url"])
        if (
            http_origin(fields["url"]) != http_origin(site.url)
            and interaction_steps is None
            and any(step.get("action") == "fill" for step in site.interaction_steps)
        ):
            raise InvalidRequest(
                "Changing the origin requires clearing fill steps or entering their values again."
            )
    # Moving a site between projects is a structural change: authorize both sides
    # so a site-only editor can't relocate it into/out of a project they can't edit.
    if "project_id" in fields and fields["project_id"] != site.project_id:
        if site.project_id is not None:
            await require_project_edit(session, user, site.project_id)
        await require_site_create(session, user, fields["project_id"])
    for key, value in fields.items():
        setattr(site, key, value)
    if interaction_steps is not None:
        await replace_site_interaction_steps(session, box, site, interaction_steps)
    if recipient_ids is not None:
        await set_site_recipients(session, site.id, recipient_ids)
    return (await _serialize(session, [site]))[0]


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(site_id: int, session: SessionDep, user: CurrentUser) -> None:
    site = await _require_site(session, site_id)
    await require_site_edit(session, user, site)
    await release_site_slot(session, site.organization_id)
    await session.delete(site)


@router.post("/{site_id}/check", response_model=RunResultOut)
async def check_now(
    site_id: int,
    session: SessionDep,
    scheduler: SchedulerDep,
    user: CurrentUser,
    settings: SettingsDep,
    analyze: bool = True,
) -> RunResult:
    """Run a check now. ``analyze=false`` captures and diffs only (no AI, no email)."""
    await _authorize_manual_capture(session, user, site_id)
    return await _bounded(scheduler.run_manual_check(site_id, analyze=analyze), settings)


@router.post("/{site_id}/snapshot", response_model=RunResultOut)
async def snapshot_now(
    site_id: int,
    session: SessionDep,
    scheduler: SchedulerDep,
    user: CurrentUser,
    settings: SettingsDep,
) -> RunResult:
    """Capture the page and store it as a new baseline, without diff or analysis."""
    await _authorize_manual_capture(session, user, site_id)
    return await _bounded(scheduler.run_manual_snapshot(site_id), settings)


async def _authorize_manual_capture(session: AsyncSession, user: CurrentUser, site_id: int) -> None:
    await require_site_edit(session, user, await _require_site(session, site_id))
    # Support access adds an audit event to this request's transaction. Persist
    # it before the scheduler opens its own session, releasing the SQLite writer.
    await session.commit()


async def _bounded(coro: Awaitable[RunResult], settings: SettingsDep) -> RunResult:
    """Run a manual capture under the same hard deadline the scheduler applies, so
    a slow page or a long interaction script can't pin a browser and request
    indefinitely."""
    try:
        return await asyncio.wait_for(coro, timeout=settings.per_site_budget_seconds)
    except TimeoutError as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "The check took too long and was stopped."
        ) from exc


async def _require_site(session: AsyncSession, site_id: int) -> Site:
    site = await session.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    return site


async def _serialize(session: AsyncSession, sites: list[Site]) -> list[SiteOut]:
    if not sites:
        return []
    site_ids = [site.id for site in sites]
    recipients = await site_recipient_ids(session, site_ids)
    aggregates = await _change_aggregates(session, site_ids)

    result: list[SiteOut] = []
    for site in sites:
        count, last = aggregates.get(site.id, (0, None))
        dto = SiteOut.model_validate(site)
        dto.recipient_ids = recipients.get(site.id, [])
        dto.change_count = count
        dto.last_change_at = last
        result.append(dto)
    return result


async def _change_aggregates(
    session: AsyncSession, site_ids: list[int]
) -> dict[int, tuple[int, datetime | None]]:
    rows = await session.execute(
        select(
            ChangeEvent.site_id,
            func.count(ChangeEvent.id),
            func.max(ChangeEvent.created_at),
        )
        .where(ChangeEvent.site_id.in_(site_ids))
        .group_by(ChangeEvent.site_id)
    )
    return {site_id: (count, last) for site_id, count, last in rows}
