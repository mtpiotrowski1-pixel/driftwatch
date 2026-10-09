"""Drive the visual selector picker / interaction recorder.

The picker opens a real browser window on the backend host, so these endpoints
are gated by the same edit access as changing a site. The frontend starts a
session, polls its status, then fetches the result to fill the form.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from driftwatch.api.deps import CurrentUser, PickerDep, SessionDep
from driftwatch.exceptions import ConflictError, NotFoundError
from driftwatch.models import Site
from driftwatch.monitoring.picker import PickerMode, PickerUnavailable
from driftwatch.schemas import (
    PickerCapabilitiesOut,
    PickerResultOut,
    PickerSessionCreate,
    PickerStatusOut,
)
from driftwatch.security.access import require_any_edit, require_site_edit
from driftwatch.security.urls import validate_public_url

router = APIRouter(prefix="/api/picker", tags=["picker"])


@router.get("/capabilities", response_model=PickerCapabilitiesOut)
async def capabilities(picker: PickerDep, _: CurrentUser) -> PickerCapabilitiesOut:
    caps = await picker.capabilities()
    return PickerCapabilitiesOut(available=caps.available, reason=caps.reason)


@router.post("/sessions", response_model=PickerStatusOut, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: PickerSessionCreate, picker: PickerDep, session: SessionDep, user: CurrentUser
) -> PickerStatusOut:
    await _authorize(session, user, payload.site_id)
    url = await validate_public_url(payload.url)
    try:
        status_ = await picker.start(url=url, mode=PickerMode(payload.mode), owner_user_id=user.id)
    except PickerUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return PickerStatusOut.model_validate(status_)


@router.get("/sessions/{session_id}", response_model=PickerStatusOut)
async def session_status(session_id: str, picker: PickerDep, user: CurrentUser) -> PickerStatusOut:
    try:
        return PickerStatusOut.model_validate(await picker.status(session_id, requester_id=user.id))
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/sessions/{session_id}/result", response_model=PickerResultOut)
async def session_result(session_id: str, picker: PickerDep, user: CurrentUser) -> PickerResultOut:
    try:
        result = await picker.result(session_id, requester_id=user.id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return PickerResultOut(
        css_selector=result.css_selector, selectors=result.selectors, steps=result.steps
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_session(session_id: str, picker: PickerDep, user: CurrentUser) -> None:
    await picker.cancel(session_id, requester_id=user.id)


async def _authorize(session: SessionDep, user: CurrentUser, site_id: int | None) -> None:
    if site_id is None:
        await require_any_edit(session, user)
        return
    site = await session.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    await require_site_edit(session, user, site)
