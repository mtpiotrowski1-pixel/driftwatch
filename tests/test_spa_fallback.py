"""The SPA catch-all must serve the client app for browser routes, yet never
shadow the API: an unknown /api path is a 404, not a 200 page of HTML."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import driftwatch.app as app_module


@pytest.mark.parametrize("frontend_bundle", [True], indirect=True)
async def test_unknown_api_path_is_a_clean_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    # JSON, not the SPA shell — an API client must not receive a 200 HTML page.
    assert "text/html" not in response.headers.get("content-type", "")


@pytest.mark.parametrize("frontend_bundle", [True], indirect=True)
async def test_client_route_falls_back_to_the_spa_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert response.text == "<!doctype html><html><body>Owned test frontend</body></html>"


async def test_api_only_runtime_does_not_serve_spa(client: httpx.AsyncClient) -> None:
    response = await client.get("/dashboard")

    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]


@pytest.mark.parametrize("frontend_bundle", [True], indirect=True)
async def test_real_api_route_keeps_its_own_status(client: httpx.AsyncClient) -> None:
    # The /api guard must only catch unmatched paths; a real but unauthenticated
    # route still answers 401, proving the guard does not shadow live endpoints.
    response = await client.get("/api/sites")

    assert response.status_code == 401


async def test_installed_runtime_serves_spa_and_corresponding_source(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    dist = runtime_root / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>runtime bundle</body></html>", encoding="utf-8")
    source_archive = b"corresponding source archive"
    (dist / "driftwatch-source.tar.gz").write_bytes(source_archive)

    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path / "installed-package-root")
    monkeypatch.chdir(runtime_root)
    app = FastAPI()
    app_module._mount_spa(app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        landing = await client.get("/")
        source = await client.get("/driftwatch-source.tar.gz")

    assert landing.status_code == 200
    assert landing.text == "<html><body>runtime bundle</body></html>"
    assert source.status_code == 200
    assert source.content == source_archive
    assert source.headers["content-type"] == "application/x-tar"
