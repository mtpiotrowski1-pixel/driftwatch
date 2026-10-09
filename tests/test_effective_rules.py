"""Effective-rules endpoints resolve the site -> project -> global -> default chain."""

from __future__ import annotations

import httpx

from driftwatch.monitoring.prompts import DEFAULT_IMPORTANCE_RULES


async def test_inherited_rules_default_then_global(admin_client: httpx.AsyncClient) -> None:
    fresh = await admin_client.get("/api/sites/effective-rules")
    assert fresh.status_code == 200
    assert fresh.json() == {"source": "default", "text": DEFAULT_IMPORTANCE_RULES}

    await admin_client.put("/api/settings", json={"importance_rules": "Global rules text"})
    with_global = (await admin_client.get("/api/sites/effective-rules")).json()
    assert with_global == {"source": "global", "text": "Global rules text"}


async def test_project_rules_own_prompt_else_global(admin_client: httpx.AsyncClient) -> None:
    project = await admin_client.post(
        "/api/projects", json={"name": "Press", "prompt": "Project rules text"}
    )
    project_id = project.json()["id"]

    own = (await admin_client.get(f"/api/projects/{project_id}/effective-rules")).json()
    assert own == {"source": "project", "text": "Project rules text"}

    await admin_client.patch(f"/api/projects/{project_id}", json={"prompt": None})
    await admin_client.put("/api/settings", json={"importance_rules": "Global rules text"})
    inherited = (await admin_client.get(f"/api/projects/{project_id}/effective-rules")).json()
    assert inherited == {"source": "global", "text": "Global rules text"}


async def test_site_rules_resolve_through_every_level(admin_client: httpx.AsyncClient) -> None:
    project = await admin_client.post(
        "/api/projects", json={"name": "Press", "prompt": "Project rules text"}
    )
    project_id = project.json()["id"]
    site = await admin_client.post(
        "/api/sites",
        json={
            "url": "https://example.test",
            "project_id": project_id,
            "prompt": "Site rules text",
        },
    )
    site_id = site.json()["id"]
    url = f"/api/sites/{site_id}/effective-rules"

    assert (await admin_client.get(url)).json() == {"source": "site", "text": "Site rules text"}

    await admin_client.patch(f"/api/sites/{site_id}", json={"prompt": None})
    assert (await admin_client.get(url)).json() == {
        "source": "project",
        "text": "Project rules text",
    }

    await admin_client.patch(f"/api/projects/{project_id}", json={"prompt": None})
    assert (await admin_client.get(url)).json()["source"] == "default"


async def test_effective_rules_404_for_unknown_ids(admin_client: httpx.AsyncClient) -> None:
    assert (await admin_client.get("/api/sites/9999/effective-rules")).status_code == 404
    assert (await admin_client.get("/api/projects/9999/effective-rules")).status_code == 404
