"""Stable public API errors and request correlation IDs."""

from __future__ import annotations

import re

import httpx
from fastapi import FastAPI, HTTPException

from driftwatch.api.error_contract import REQUEST_ID_HEADER, RequestIdMiddleware
from driftwatch.app import _register_exception_handlers
from driftwatch.exceptions import InvalidRequest

_GENERATED_ID = re.compile(r"[0-9a-f]{32}")


async def test_success_and_http_error_echo_safe_request_id(
    client: httpx.AsyncClient,
) -> None:
    request_id = "web-01HZY8J6QZ.trace_4"

    success = await client.get("/livez", headers={REQUEST_ID_HEADER: request_id})
    assert success.status_code == 200
    assert success.headers[REQUEST_ID_HEADER] == request_id

    rejected = await client.get("/api/sites", headers={REQUEST_ID_HEADER: request_id})
    assert rejected.status_code == 401
    assert rejected.headers[REQUEST_ID_HEADER] == request_id
    assert rejected.json() == {
        "detail": "Not authenticated",
        "error_code": "authentication_required",
        "request_id": request_id,
    }


async def test_invalid_or_duplicate_request_id_is_replaced(
    client: httpx.AsyncClient,
) -> None:
    invalid = await client.get(
        "/api/sites",
        headers={REQUEST_ID_HEADER: "not/allowed"},
    )
    duplicate = await client.get(
        "/api/sites",
        headers=[(REQUEST_ID_HEADER, "trace-one"), (REQUEST_ID_HEADER, "trace-two")],
    )

    for response in (invalid, duplicate):
        generated = response.headers[REQUEST_ID_HEADER]
        assert _GENERATED_ID.fullmatch(generated)
        assert response.json()["request_id"] == generated


async def test_validation_and_domain_errors_use_the_same_envelope(
    client: httpx.AsyncClient,
    admin_client: httpx.AsyncClient,
) -> None:
    validation = await client.post(
        "/api/auth/register",
        json={"email": "invalid", "password": "short"},
        headers={REQUEST_ID_HEADER: "validation-1"},
    )
    assert validation.status_code == 422
    assert isinstance(validation.json()["detail"], list)
    assert validation.json()["error_code"] == "validation_error"
    assert validation.json()["request_id"] == "validation-1"

    domain = await admin_client.post(
        "/api/sites",
        json={"url": "ftp://example.test"},
        headers={REQUEST_ID_HEADER: "domain-1"},
    )
    assert domain.status_code == 400
    assert domain.json() == {
        "detail": "URL must start with http:// or https://",
        "error_code": "invalid_request",
        "request_id": "domain-1",
    }


async def test_origin_rejection_uses_the_same_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example", REQUEST_ID_HEADER: "origin-1"},
    )

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == "origin-1"
    assert response.json() == {
        "detail": "Cross-origin request rejected",
        "error_code": "cross_origin_request",
        "request_id": "origin-1",
    }


async def test_unexpected_error_is_correlated_without_leaking_details() -> None:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    _register_exception_handlers(app)

    @app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(418, detail={"reason": "teapot"}, headers={"X-Test": "kept"})

    @app.get("/domain-error")
    async def domain_error() -> None:
        raise InvalidRequest("Expected failure")

    @app.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("database-password=must-not-leak")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        http_response = await test_client.get("/http-error", headers={REQUEST_ID_HEADER: "http-1"})
        domain_response = await test_client.get(
            "/domain-error", headers={REQUEST_ID_HEADER: "domain-2"}
        )
        unexpected_response = await test_client.get(
            "/unexpected", headers={REQUEST_ID_HEADER: "failure-1"}
        )

    assert http_response.status_code == 418
    assert http_response.headers["X-Test"] == "kept"
    assert http_response.json() == {
        "detail": {"reason": "teapot"},
        "error_code": "http_418",
        "request_id": "http-1",
    }
    assert domain_response.json()["error_code"] == "invalid_request"
    assert unexpected_response.status_code == 500
    assert unexpected_response.headers[REQUEST_ID_HEADER] == "failure-1"
    assert unexpected_response.json() == {
        "detail": "Internal server error",
        "error_code": "internal_server_error",
        "request_id": "failure-1",
    }
    assert "must-not-leak" not in unexpected_response.text
