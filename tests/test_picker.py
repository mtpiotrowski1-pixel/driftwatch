"""Tests for browser-channel detection, step normalization, and the picker API."""

from __future__ import annotations

import httpx
import pytest

from driftwatch.monitoring.browser import BrowserChannel, detection_order, parse_channel
from driftwatch.monitoring.picker import _OVERLAY_PATH, normalize_step
from tests.conftest import FakePicker


def test_detection_order_auto_prefers_edge_then_chrome_then_bundled() -> None:
    assert detection_order(BrowserChannel.AUTO) == [
        BrowserChannel.MSEDGE,
        BrowserChannel.CHROME,
        BrowserChannel.CHROMIUM,
    ]


def test_detection_order_respects_forced_channel() -> None:
    assert detection_order(BrowserChannel.CHROME) == [BrowserChannel.CHROME]


def test_parse_channel_falls_back_to_auto_on_garbage() -> None:
    assert parse_channel("msedge") is BrowserChannel.MSEDGE
    assert parse_channel("nonsense") is BrowserChannel.AUTO
    assert parse_channel(None) is BrowserChannel.AUTO


def test_normalize_step_maps_overlay_shape_to_interaction_step() -> None:
    typed = normalize_step({"type": "type", "selector": "#q", "text": "hello", "delay_ms": 500})
    assert typed == {"action": "fill", "selector": "#q", "timeout_ms": 10_000}
    assert "hello" not in repr(typed)

    clicked = normalize_step({"type": "click", "selector": "#go"})
    assert clicked == {"action": "click", "selector": "#go", "timeout_ms": 10_000}


def test_overlay_never_records_password_fields() -> None:
    script = _OVERLAY_PATH.read_text(encoding="utf-8")
    assert '"password"' in script
    assert 'autocomplete === "current-password"' in script
    assert 'autocomplete === "new-password"' in script
    assert "text: finalValue" not in script


async def test_picker_capabilities(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/picker/capabilities")
    assert response.status_code == 200
    assert response.json()["available"] is True


async def test_picker_session_round_trip(admin_client: httpx.AsyncClient) -> None:
    started = await admin_client.post(
        "/api/picker/sessions", json={"url": "https://example.com", "mode": "select"}
    )
    assert started.status_code == 201
    session_id = started.json()["session_id"]

    status_response = await admin_client.get(f"/api/picker/sessions/{session_id}")
    assert status_response.json()["state"] == "saved"

    result = await admin_client.get(f"/api/picker/sessions/{session_id}/result")
    assert result.json()["css_selector"] == "main .price"

    assert (await admin_client.delete(f"/api/picker/sessions/{session_id}")).status_code == 204


async def test_picker_rejects_unsafe_url(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/picker/sessions", json={"url": "http://127.0.0.1/admin", "mode": "select"}
    )
    assert response.status_code == 400


async def test_picker_unavailable_returns_503(
    admin_client: httpx.AsyncClient, picker: FakePicker
) -> None:
    picker.available = False
    response = await admin_client.post(
        "/api/picker/sessions", json={"url": "https://example.com", "mode": "select"}
    )
    assert response.status_code == 503


async def test_picker_requires_edit_access(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    )
    await client.post(
        "/api/auth/register", json={"email": "member@example.com", "password": "password123"}
    )  # session is now the member, who holds no edit grants
    response = await client.post(
        "/api/picker/sessions", json={"url": "https://example.com", "mode": "select"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("mode", ["select", "record"])
async def test_picker_accepts_both_modes(admin_client: httpx.AsyncClient, mode: str) -> None:
    response = await admin_client.post(
        "/api/picker/sessions", json={"url": "https://example.com", "mode": mode}
    )
    assert response.status_code == 201
    assert response.json()["mode"] == mode
