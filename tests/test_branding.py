"""Branding settings: the public endpoint, instance-vs-org isolation, and the
validation that keeps operator/admin-supplied values safe in HTML and CSS."""

from __future__ import annotations

import base64
import hashlib

import httpx
import pytest

from driftwatch.db import Database
from driftwatch.models import Setting

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def _register_org_admin(client: httpx.AsyncClient, email: str, org: str) -> None:
    """Register a self-serve org-admin (own organization, never the operator).
    Replaces the client's session cookie with the new account's."""
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "organization_name": org},
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_superadmin"] is False


async def test_public_branding_needs_no_auth_and_is_blank_by_default(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/branding")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "brand_name",
        "logo_url",
        "accent_color",
        "tagline",
        "hero_title",
        "hero_subtitle",
        "hero_background_url",
    }
    assert all(value == "" for value in body.values())


async def test_operator_instance_branding_surfaces_publicly(
    admin_client: httpx.AsyncClient,
) -> None:
    saved = await admin_client.put(
        "/api/settings",
        json={
            "brand_name": "Acme Watch",
            "brand_accent_color": "#11b981",
            "landing_hero_title": "Catch every change",
            "landing_tagline": "Monitoring, minus the noise",
        },
    )
    assert saved.status_code == 200

    branding = (await admin_client.get("/api/branding")).json()
    assert branding["brand_name"] == "Acme Watch"
    assert branding["accent_color"] == "#11b981"
    assert branding["hero_title"] == "Catch every change"
    assert branding["tagline"] == "Monitoring, minus the noise"


async def test_org_branding_is_scoped_to_its_members_not_the_public_landing(
    admin_client: httpx.AsyncClient,
) -> None:
    # Operator sets the instance brand the public landing shows.
    await admin_client.put(
        "/api/settings", json={"brand_name": "Acme Platform", "landing_hero_title": "Watch it all"}
    )

    # A tenant admin brands their own workspace and tries to set a landing-only key.
    await _register_org_admin(admin_client, "tenant@example.com", "Tenant Co")
    tenant_saved = await admin_client.put(
        "/api/settings",
        json={"brand_name": "Tenant Brand"},
    )
    assert tenant_saved.status_code == 200, tenant_saved.text
    tenant_view = tenant_saved.json()
    # The org override applies to the tenant's own effective view...
    assert tenant_view["brand_name"] == "Tenant Brand"
    # ...but a tenant cannot even submit the instance-only landing key.
    rejected = await admin_client.put(
        "/api/settings",
        json={"landing_hero_title": "Hijacked"},
    )
    assert rejected.status_code == 400

    # A signed-in member of the tenant sees their own org's brand.
    member_branding = (await admin_client.get("/api/branding/workspace")).json()
    assert member_branding["brand_name"] == "Tenant Brand"
    # landing_* is never per-org, so it stays the operator's instance value.
    assert member_branding["hero_title"] == "Watch it all"

    # The anonymous public landing reflects only the operator's instance brand.
    admin_client.cookies.clear()
    public = (await admin_client.get("/api/branding")).json()
    assert public["brand_name"] == "Acme Platform"
    assert public["hero_title"] == "Watch it all"


@pytest.mark.parametrize(
    "payload",
    [
        {"brand_accent_color": "blue"},
        {"brand_accent_color": "#12g"},
        {"brand_logo_url": "javascript:alert(1)"},
        {"brand_logo_url": "https://cdn.test/logo.png?x=a) ; }"},
        {"landing_hero_background_url": "data:text/html,<script>"},
    ],
)
async def test_branding_rejects_unsafe_values(
    admin_client: httpx.AsyncClient, payload: dict[str, str]
) -> None:
    response = await admin_client.put("/api/settings", json=payload)
    assert response.status_code == 422


async def test_branding_accepts_safe_values(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.put(
        "/api/settings",
        json={
            "brand_accent_color": "#abc",
        },
    )
    assert response.status_code == 200


async def test_branding_bitmap_upload_is_same_origin_and_deletable(
    admin_client: httpx.AsyncClient,
) -> None:
    uploaded = await admin_client.post(
        "/api/branding/assets/logo",
        content=_PNG_1X1,
        headers={"Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text
    version = hashlib.sha256(_PNG_1X1).hexdigest()[:12]
    assert uploaded.json() == {
        "url": f"/api/branding/assets/instance/logo.png?v={version}",
        "media_type": "image/png",
    }

    branding = (await admin_client.get("/api/branding")).json()
    assert branding["logo_url"] == uploaded.json()["url"]
    image = await admin_client.get(branding["logo_url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert image.content == _PNG_1X1

    unversioned = await admin_client.get("/api/branding/assets/instance/logo.png")
    assert unversioned.headers["cache-control"] == "public, max-age=60, must-revalidate"

    deleted = await admin_client.delete("/api/branding/assets/logo")
    assert deleted.status_code == 204
    assert (await admin_client.get("/api/branding")).json()["logo_url"] == ""
    assert (await admin_client.get(uploaded.json()["url"])).status_code == 404


async def test_branding_upload_rejects_active_or_malformed_content(
    admin_client: httpx.AsyncClient,
) -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    response = await admin_client.post(
        "/api/branding/assets/logo",
        content=svg,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422
    assert "PNG and JPEG" in response.json()["detail"]

    truncated_png = _PNG_1X1[:-4]
    response = await admin_client.post(
        "/api/branding/assets/logo",
        content=truncated_png,
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 422


async def test_tenant_logo_is_scoped_and_tenant_cannot_replace_public_hero(
    admin_client: httpx.AsyncClient,
) -> None:
    await _register_org_admin(admin_client, "tenant-assets@example.com", "Tenant Assets")
    me = (await admin_client.get("/api/auth/me")).json()

    logo = await admin_client.post(
        "/api/branding/assets/logo",
        content=_PNG_1X1,
        headers={"Content-Type": "image/png"},
    )
    assert logo.status_code == 200, logo.text
    version = hashlib.sha256(_PNG_1X1).hexdigest()[:12]
    assert (
        logo.json()["url"]
        == f"/api/branding/assets/org-{me['organization_id']}/logo.png?v={version}"
    )
    workspace = await admin_client.get("/api/branding/workspace")
    assert workspace.json()["logo_url"] == logo.json()["url"]

    hero = await admin_client.post(
        "/api/branding/assets/hero",
        content=_PNG_1X1,
        headers={"Content-Type": "image/png"},
    )
    assert hero.status_code == 403


async def test_branding_upload_authentication_precedes_body_consumption(
    client: httpx.AsyncClient,
) -> None:
    class UnreadableBody(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("anonymous branding body must not be consumed")
            yield b""  # pragma: no cover

    response = await client.post(
        "/api/branding/assets/logo",
        content=UnreadableBody(),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 401


async def test_legacy_remote_branding_url_is_never_emitted(
    admin_client: httpx.AsyncClient,
    database: Database,
) -> None:
    async with database.session() as session:
        session.add(Setting(key="brand_logo_url", value="https://cdn.test/legacy-logo.png"))
        await session.commit()
    assert (await admin_client.get("/api/branding")).json()["logo_url"] == ""
