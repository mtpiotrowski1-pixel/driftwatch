"""Public, unauthenticated branding for the marketing landing page.

The landing is served before anyone signs in, so it cannot read settings through
the admin-gated ``/api/settings``. This endpoint exposes only the operator's
instance-level branding — never any other setting — so the page can render the
operator's name, logo, accent colour, and hero copy with sensible fallbacks.
"""

from __future__ import annotations

import hashlib
import os
import zlib
from pathlib import Path
from typing import Literal
from uuid import uuid4

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from driftwatch.api.deps import (
    AdminUser,
    CurrentUser,
    SecretBoxDep,
    SessionDep,
    SettingsDep,
)
from driftwatch.schemas import BrandingOut
from driftwatch.settings_store import SettingsStore

router = APIRouter(prefix="/api/branding", tags=["branding"])

_AssetKind = Literal["logo", "hero"]
_ASSET_SETTING: dict[_AssetKind, str] = {
    "logo": "brand_logo_url",
    "hero": "landing_hero_background_url",
}
_MAX_ASSET_BYTES: dict[_AssetKind, int] = {
    "logo": 2 * 1024 * 1024,
    "hero": 8 * 1024 * 1024,
}
_MAX_ASSET_DIMENSION: dict[_AssetKind, int] = {"logo": 4096, "hero": 10_000}


@router.get("", response_model=BrandingOut)
async def read_public_branding(
    session: SessionDep, box: SecretBoxDep, response: Response
) -> BrandingOut:
    """Return only the instance brand, regardless of an incidental session cookie."""
    values = await SettingsStore(session, box, org_id=None).branding()
    response.headers["Cache-Control"] = "public, max-age=60"
    return _branding_out(values)


@router.get("/workspace", response_model=BrandingOut)
async def read_workspace_branding(
    session: SessionDep,
    box: SecretBoxDep,
    response: Response,
    _: CurrentUser,
) -> BrandingOut:
    """Return branding for the server-authorized organization context."""
    org_id = session.sync_session.info.get("org_id")
    values = await SettingsStore(session, box, org_id=org_id).branding()
    response.headers["Cache-Control"] = "private, no-store"
    return _branding_out(values)


def _branding_out(values: dict[str, str]) -> BrandingOut:
    return BrandingOut(
        brand_name=values["brand_name"],
        logo_url=_safe_asset_url(values["brand_logo_url"]),
        accent_color=values["brand_accent_color"],
        tagline=values["landing_tagline"],
        hero_title=values["landing_hero_title"],
        hero_subtitle=values["landing_hero_subtitle"],
        hero_background_url=_safe_asset_url(values["landing_hero_background_url"]),
    )


@router.post("/assets/{kind}", response_model=dict[str, str])
async def upload_branding_asset(
    kind: _AssetKind,
    request: Request,
    session: SessionDep,
    box: SecretBoxDep,
    settings: SettingsDep,
    _: AdminUser,
) -> dict[str, str]:
    """Store a validated bitmap under the application's own origin.

    Remote image URLs are deliberately unsupported: proxying arbitrary operator
    input would reintroduce SSRF, while loading it in the browser conflicts with
    the strict CSP. Only bounded PNG/JPEG payloads are accepted; SVG is excluded
    because it is active XML rather than a passive bitmap.
    """
    org_id = session.sync_session.info.get("org_id")
    if kind == "hero" and org_id is not None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the instance operator can change the public hero image",
        )

    limit = _MAX_ASSET_BYTES[kind]
    payload = await _read_asset(request, limit)
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image file is empty")
    if len(payload) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image file is too large")
    extension, media_type, width, height = _inspect_bitmap(payload)
    max_dimension = _MAX_ASSET_DIMENSION[kind]
    if width > max_dimension or height > max_dimension:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Image dimensions must not exceed {max_dimension} pixels",
        )

    scope = _asset_scope(org_id)
    directory = _asset_directory(settings, scope)
    destination = directory / f"{kind}.{extension}"
    await to_thread.run_sync(_replace_asset, directory, kind, destination, payload)
    version = hashlib.sha256(payload).hexdigest()[:12]
    url = f"/api/branding/assets/{scope}/{destination.name}?v={version}"
    await SettingsStore(session, box, org_id=org_id).set_many({_ASSET_SETTING[kind]: url})
    return {"url": url, "media_type": media_type}


async def _read_asset(request: Request, limit: int) -> bytes:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type not in {"application/octet-stream", "image/jpeg", "image/png"}:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Upload a PNG or JPEG bitmap as the request body",
        )
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "Image file is too large",
            )
    return bytes(payload)


@router.delete("/assets/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branding_asset(
    kind: _AssetKind,
    session: SessionDep,
    box: SecretBoxDep,
    settings: SettingsDep,
    _: AdminUser,
) -> None:
    org_id = session.sync_session.info.get("org_id")
    if kind == "hero" and org_id is not None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the instance operator can change the public hero image",
        )
    await SettingsStore(session, box, org_id=org_id).set_many({_ASSET_SETTING[kind]: ""})
    directory = _asset_directory(settings, _asset_scope(org_id))
    await to_thread.run_sync(_remove_assets, directory, kind)


@router.get("/assets/{scope}/{filename}", include_in_schema=False)
def serve_branding_asset(
    scope: str,
    filename: str,
    settings: SettingsDep,
    request: Request,
) -> FileResponse:
    if not _valid_scope(scope) or filename not in {
        "logo.png",
        "logo.jpg",
        "hero.png",
        "hero.jpg",
    }:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = _asset_directory(settings, scope) / filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    media_type = "image/png" if path.suffix == ".png" else "image/jpeg"
    cache_control = (
        "public, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "public, max-age=60, must-revalidate"
    )
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": cache_control})


def _safe_asset_url(value: str) -> str:
    """Hide legacy remote URLs; only same-origin uploaded/static paths render."""
    return (
        value if value.startswith("/") and not value.startswith("//") and "\\" not in value else ""
    )


def _asset_scope(org_id: object) -> str:
    if org_id is None:
        return "instance"
    if not isinstance(org_id, int) or org_id < 1:
        raise RuntimeError("invalid organization scope")
    return f"org-{org_id}"


def _valid_scope(scope: str) -> bool:
    return scope == "instance" or (
        scope.startswith("org-") and scope.removeprefix("org-").isdigit()
    )


def _asset_directory(settings: SettingsDep, scope: str) -> Path:
    return settings.data_dir / "branding" / scope


def _replace_asset(
    directory: Path,
    kind: str,
    destination: Path,
    payload: bytes,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".upload-{uuid4().hex}"
    try:
        temporary.write_bytes(payload)
        _remove_assets(directory, kind)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_assets(directory: Path, kind: str) -> None:
    if not directory.is_dir():
        return
    for extension in ("png", "jpg"):
        (directory / f"{kind}.{extension}").unlink(missing_ok=True)


def _inspect_bitmap(payload: bytes) -> tuple[str, str, int, int]:
    png = _png_dimensions(payload)
    if png is not None:
        return "png", "image/png", *png
    jpeg = _jpeg_dimensions(payload)
    if jpeg is not None:
        return "jpg", "image/jpeg", *jpeg
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Only valid PNG and JPEG bitmap images are accepted",
    )


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_end = False
    while offset + 12 <= len(payload):
        size = int.from_bytes(payload[offset : offset + 4], "big")
        chunk_type = payload[offset + 4 : offset + 8]
        end = offset + 12 + size
        if end > len(payload):
            return None
        data = payload[offset + 8 : offset + 8 + size]
        expected_crc = int.from_bytes(payload[offset + 8 + size : end], "big")
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            return None
        if chunk_type == b"IHDR":
            if dimensions is not None or size != 13:
                return None
            width = int.from_bytes(data[:4], "big")
            height = int.from_bytes(data[4:8], "big")
            if width < 1 or height < 1:
                return None
            dimensions = (width, height)
        elif chunk_type == b"IEND":
            if size != 0 or end != len(payload):
                return None
            saw_end = True
            break
        offset = end
    return dimensions if saw_end else None


def _jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 4 or not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        return None
    offset = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(payload):
        if payload[offset] != 0xFF:
            return None
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            return None
        marker = payload[offset]
        offset += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(payload):
            return None
        segment_length = int.from_bytes(payload[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(payload):
            return None
        if marker in sof_markers:
            if segment_length < 7:
                return None
            height = int.from_bytes(payload[offset + 3 : offset + 5], "big")
            width = int.from_bytes(payload[offset + 5 : offset + 7], "big")
            return (width, height) if width > 0 and height > 0 else None
        if marker == 0xDA:  # scan data starts; SOF must have appeared before it
            return None
        offset += segment_length
    return None
