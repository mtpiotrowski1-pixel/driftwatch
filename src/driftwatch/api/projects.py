"""Project CRUD. Projects group sites and supply inherited AI rules and mode."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.api.deps import AdminUser, CurrentUser, OrgContext, SecretBoxDep, SessionDep
from driftwatch.models import Project, Site
from driftwatch.schemas import EffectiveRulesOut, ProjectCreate, ProjectOut, ProjectUpdate
from driftwatch.security.access import require_project_edit
from driftwatch.services import (
    effective_importance_rules,
    project_recipient_ids,
    set_project_recipients,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: SessionDep, _: CurrentUser) -> list[ProjectOut]:
    projects = list((await session.execute(select(Project).order_by(Project.name))).scalars())
    return await _serialize(session, projects)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: SessionDep, _: AdminUser, org_id: OrgContext
) -> ProjectOut:
    project = Project(
        organization_id=org_id,
        name=payload.name,
        prompt=payload.prompt,
        notification_mode=payload.notification_mode,
    )
    session.add(project)
    await session.flush()
    await set_project_recipients(session, project.id, payload.recipient_ids)
    return (await _serialize(session, [project]))[0]


@router.get("/{project_id}/effective-rules", response_model=EffectiveRulesOut)
async def project_effective_rules(
    project_id: int, session: SessionDep, _: CurrentUser, box: SecretBoxDep
) -> EffectiveRulesOut:
    """The importance rules sites of this project inherit unless they override
    them: the project's own prompt, else the global rules, else the default."""
    project = await _require_project(session, project_id)
    rules = await effective_importance_rules(
        session, box, org_id=project.organization_id, project_prompt=project.prompt
    )
    return EffectiveRulesOut(source=rules.source, text=rules.text)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int, payload: ProjectUpdate, session: SessionDep, user: CurrentUser
) -> ProjectOut:
    project = await _require_project(session, project_id)
    await require_project_edit(session, user, project_id)
    fields = payload.model_dump(exclude_unset=True)
    recipient_ids = fields.pop("recipient_ids", None)
    for key, value in fields.items():
        setattr(project, key, value)
    if recipient_ids is not None:
        await set_project_recipients(session, project.id, recipient_ids)
    return (await _serialize(session, [project]))[0]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, session: SessionDep, _: AdminUser) -> None:
    project = await _require_project(session, project_id)
    await session.delete(project)


async def _require_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id} not found")
    return project


async def _serialize(session: AsyncSession, projects: list[Project]) -> list[ProjectOut]:
    if not projects:
        return []
    project_ids = [project.id for project in projects]
    recipients = await project_recipient_ids(session, project_ids)
    count_rows = await session.execute(
        select(Site.project_id, func.count(Site.id))
        .where(Site.project_id.in_(project_ids))
        .group_by(Site.project_id)
    )
    counts: dict[int, int] = {
        project_id: count for project_id, count in count_rows if project_id is not None
    }

    result: list[ProjectOut] = []
    for project in projects:
        dto = ProjectOut.model_validate(project)
        dto.site_count = counts.get(project.id, 0)
        dto.recipient_ids = recipients.get(project.id, [])
        result.append(dto)
    return result
