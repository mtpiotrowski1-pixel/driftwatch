"""Oversized declared and chunked bodies are rejected before endpoint parsing."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from driftwatch.api.request_limits import (
    BRANDING_BODY_BYTES,
    DEFAULT_API_BODY_BYTES,
    RESTORE_BODY_BYTES,
    request_body_limit,
)


async def test_declared_oversized_api_body_uses_stable_error_contract(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/auth/login",
        content=b"{}",
        headers={"Content-Length": str(DEFAULT_API_BODY_BYTES + 1)},
    )

    assert response.status_code == 413, response.text
    assert response.json()["error_code"] == "payload_too_large"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


async def test_chunked_oversized_api_body_is_stopped_while_streaming(
    client: httpx.AsyncClient,
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"email":"'
        chunk = b"x" * (512 * 1024)
        for _ in range(5):
            yield chunk
        yield b'@example.com","password":"password123"}'

    response = await client.post(
        "/api/auth/login",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413, response.text
    assert response.json()["error_code"] == "payload_too_large"


def test_upload_endpoints_have_explicit_larger_but_bounded_budgets() -> None:
    assert request_body_limit("/api/sites") == DEFAULT_API_BODY_BYTES
    assert request_body_limit("/api/branding/assets/logo") == BRANDING_BODY_BYTES
    assert request_body_limit("/api/branding/assets/hero") == BRANDING_BODY_BYTES
    assert request_body_limit("/api/admin/restore") == RESTORE_BODY_BYTES
