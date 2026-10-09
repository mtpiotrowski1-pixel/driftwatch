"""Public API contracts that protect validation, scope, and historical access."""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from driftwatch.schemas import PlanUpdate, ProjectUpdate, RecipientUpdate, SiteUpdate, UserUpdate
from driftwatch.security.origins import http_origin


@pytest.mark.parametrize("field", ["url", "enabled", "check_interval_minutes", "ignore_selectors"])
async def test_patch_null_cannot_break_site(admin_client: httpx.AsyncClient, field: str) -> None:
    created = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    site_id = created.json()["id"]
    invalid = await admin_client.patch(f"/api/sites/{site_id}", json={field: None})
    assert invalid.status_code == 422
    assert (await admin_client.get(f"/api/sites/{site_id}")).json()[field] == created.json()[field]
    cleared = await admin_client.patch(f"/api/sites/{site_id}", json={"name": None})
    assert cleared.status_code == 200
    assert cleared.json()["name"] is None


def test_patch_null_semantics_are_explicit() -> None:
    assert SiteUpdate().model_dump(exclude_unset=True) == {}
    assert ProjectUpdate(prompt=None).model_dump(exclude_unset=True) == {"prompt": None}
    for model, payload in [(ProjectUpdate, {"name": None}), (UserUpdate, {"is_active": None})]:
        with pytest.raises(ValidationError, match="cannot be null"):
            model.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["key", "name", "currency", "is_active", "is_self_serve", "sort_order"]
)
def test_plan_patch_rejects_null_only_for_required_fields(field: str) -> None:
    assert PlanUpdate().model_dump(exclude_unset=True) == {}
    assert PlanUpdate(max_sites=None).model_dump(exclude_unset=True) == {"max_sites": None}
    with pytest.raises(ValidationError, match="cannot be null"):
        PlanUpdate.model_validate({field: None})


async def test_recipient_patch_omitted_value_and_null_contract(
    admin_client: httpx.AsyncClient,
) -> None:
    created = await admin_client.post(
        "/api/recipients", json={"email": "reviewed@example.com", "name": "Reviewer"}
    )
    recipient_id = created.json()["id"]
    omitted = await admin_client.patch(f"/api/recipients/{recipient_id}", json={})
    assert omitted.status_code == 200 and omitted.json()["active"] is True
    invalid = await admin_client.patch(f"/api/recipients/{recipient_id}", json={"active": None})
    assert invalid.status_code == 422
    disabled = await admin_client.patch(
        f"/api/recipients/{recipient_id}", json={"active": False, "name": None}
    )
    assert disabled.status_code == 200 and disabled.json()["active"] is False
    assert disabled.json()["name"] is None
    assert RecipientUpdate().model_dump(exclude_unset=True) == {}


async def test_fill_secret_is_bound_to_origin(admin_client: httpx.AsyncClient) -> None:
    secret = "synthetic-origin-scoped-value"
    steps = [{"action": "fill", "selector": "#token", "secret_value": secret}]
    created = await admin_client.post(
        "/api/sites", json={"url": "https://example.test/login", "interaction_steps": steps}
    )
    site_id = created.json()["id"]
    reference = created.json()["interaction_steps"][0]["secret_ref"]
    retained = [{"action": "fill", "selector": "#token", "secret_ref": reference}]
    same_origin = await admin_client.patch(
        f"/api/sites/{site_id}",
        json={"url": "https://example.test:443/next", "interaction_steps": retained},
    )
    assert same_origin.status_code == 200, same_origin.text
    for payload in [
        {"url": "https://other.test/login"},
        {"url": "https://other.test/login", "interaction_steps": retained},
    ]:
        refused = await admin_client.patch(f"/api/sites/{site_id}", json=payload)
        assert refused.status_code == 400, refused.text
        assert secret not in refused.text
    assert (
        (await admin_client.get(f"/api/sites/{site_id}"))
        .json()["url"]
        .startswith("https://example.test")
    )
    reentered = await admin_client.patch(
        f"/api/sites/{site_id}",
        json={"url": "https://other.test/login", "interaction_steps": steps},
    )
    assert reentered.status_code == 200, reentered.text
    assert reentered.json()["interaction_steps"][0]["secret_ref"] != reference


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.test:443/path", "https://example.test"),
        ("http://example.test:8000/path", "http://example.test:8000"),
        ("https://[2001:db8::1]:443/path", "https://[2001:db8::1]"),
    ],
)
def test_origin_canonicalization(url: str, expected: str) -> None:
    assert http_origin(url) == expected
