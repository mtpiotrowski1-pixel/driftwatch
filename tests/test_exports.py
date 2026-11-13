"""XLSX export of changes: localized headers and values, formula neutralization."""

from __future__ import annotations

import io

import httpx
import pytest
from openpyxl import load_workbook

from tests.conftest import ScriptedCapturer, StubAnalyzer

_V1 = "<main><p>Basic plan costs 10 USD per month</p></main>"
_V2 = "<main><p>Basic plan costs 12 USD per month</p></main>"


@pytest.fixture
def analyzer() -> StubAnalyzer:
    return StubAnalyzer(headline='=HYPERLINK("https://attacker.example")', summary="@SUM(A1)")


async def _sheet(client: httpx.AsyncClient, url: str) -> tuple[str, list[str]]:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    assert sheet is not None
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    return sheet.title, headers


async def test_export_defaults_to_english(admin_client: httpx.AsyncClient) -> None:
    title, headers = await _sheet(admin_client, "/api/exports/changes.xlsx")
    assert title == "Changes"
    assert headers == [
        "Change",
        "Site",
        "URL",
        "Detected (UTC)",
        "Significant",
        "Headline",
        "Summary",
        "Notified",
    ]


async def test_export_renders_polish_headers(admin_client: httpx.AsyncClient) -> None:
    title, headers = await _sheet(admin_client, "/api/exports/changes.xlsx?lang=pl")
    assert title == "Zmiany"
    assert headers == [
        "Zmiana",
        "Strona",
        "URL",
        "Wykryto (UTC)",
        "Istotna",
        "Nagłówek",
        "Podsumowanie",
        "Powiadomiono",
    ]


async def test_export_unknown_language_falls_back_to_english(
    admin_client: httpx.AsyncClient,
) -> None:
    title, _ = await _sheet(admin_client, "/api/exports/changes.xlsx?lang=de")
    assert title == "Changes"


async def _export_one_change(client: httpx.AsyncClient, capturer: ScriptedCapturer) -> None:
    capturer.queue.extend([_V1, _V2])
    recipient = await client.post("/api/recipients", json={"email": "ops@example.com"})
    assert recipient.status_code == 201, recipient.text
    site = await client.post(
        "/api/sites",
        json={
            "url": "https://example.test/pricing",
            "name": "+cmd|' /C calc'!A0",
            "recipient_ids": [recipient.json()["id"]],
        },
    )
    assert site.status_code == 201, site.text
    for expected in ("baseline", "changed"):
        check = await client.post(f"/api/sites/{site.json()['id']}/check")
        assert check.json()["status"] == expected


@pytest.mark.parametrize(("language", "significant"), [("en", "yes"), ("pl", "tak")])
async def test_export_rows_are_localized_and_cannot_become_formulas(
    admin_client: httpx.AsyncClient, capturer: ScriptedCapturer, language: str, significant: str
) -> None:
    await _export_one_change(admin_client, capturer)

    response = await admin_client.get(f"/api/exports/changes.xlsx?lang={language}")
    assert response.status_code == 200, response.text
    sheet = load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    rows = list(sheet.iter_rows(min_row=2, values_only=True))

    assert len(rows) == 1
    _, site_name, url, _, significance, headline, summary, _ = rows[0]
    assert site_name == "'+cmd|' /C calc'!A0"
    assert url == "https://example.test/pricing"
    assert significance == significant
    assert headline == '\'=HYPERLINK("https://attacker.example")'
    assert summary == "'@SUM(A1)"
    assert all(cell.data_type != "f" for cell in sheet[2])
