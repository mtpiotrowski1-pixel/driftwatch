"""Provenance, stale-response accounting and honestly unknown prices."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from tests.conftest import create_org

from driftwatch.db import Database
from driftwatch.models import AIUsage, AnalysisRun, ChangeEvent, Site, Snapshot
from driftwatch.monitoring.analysis_ownership import AnalysisOwnershipLost
from driftwatch.monitoring.analyzer import Analysis
from driftwatch.monitoring.pipeline import analyze_change
from driftwatch.monitoring.usage import TokenUsage, configured_prices, estimate_cost


class InspectingAnalyzer:
    def __init__(self) -> None:
        self.inputs: list[dict[str, str]] = []

    async def analyze(
        self, *, diff_text: str, url: str, system_prompt: str, model: str
    ) -> Analysis:
        self.inputs.append(
            {"diff_text": diff_text, "url": url, "system_prompt": system_prompt, "model": model}
        )
        return Analysis(
            True,
            "Price changed",
            "A product price changed",
            estimate_cost(model, TokenUsage(100, 20)),
        )


async def _seed(database: Database) -> tuple[int, int]:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(
            organization_id=org_id, url="https://example.test/prices", prompt="Watch prices"
        )
        session.add(site)
        await session.flush()
        snapshot = Snapshot(
            site_id=site.id, content_html="<p>Basic 20 EUR</p>", content_text="Basic 20 EUR"
        )
        session.add(snapshot)
        await session.flush()
        change = ChangeEvent(
            site_id=site.id, new_snapshot_id=snapshot.id, diff_text="Basic 20 EUR\n" * 100
        )
        session.add(change)
        await session.commit()
        return site.id, change.id


async def test_history_covers_actual_capped_input_and_preserves_previous_rules(
    database: Database,
) -> None:
    site_id, change_id = await _seed(database)
    analyzer = InspectingAnalyzer()
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        for prompt in ("Watch prices", "Only watch availability"):
            site.prompt = prompt
            await analyze_change(
                session,
                change,
                site,
                analyzer=analyzer,
                system_prompt=prompt,
                model="gpt-4o-mini",
                rules_source="site",
                max_diff_chars=128,
            )
        await session.commit()
    async with database.session() as session:
        runs = (await session.scalars(select(AnalysisRun).order_by(AnalysisRun.id))).all()
        assert [run.system_prompt for run in runs] == ["Watch prices", "Only watch availability"]
        assert len({run.rules_version for run in runs}) == 2
        assert all(run.rules_source == "site" and run.input_truncated for run in runs)
        for run, sent in zip(runs, analyzer.inputs, strict=True):
            assert len(sent["diff_text"]) == 128
            assert sent["diff_text"].endswith("[... diff truncated ...]")
            encoded = json.dumps(
                {
                    "version": 1,
                    "model": sent["model"],
                    "system": sent["system_prompt"],
                    "user": f"URL: {sent['url']}\n\nChanges:\n{sent['diff_text']}",
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            assert run.input_sha256 == hashlib.sha256(encoded).hexdigest()
            assert run.rules_version == hashlib.sha256(sent["system_prompt"].encode()).hexdigest()
            usage = await session.get(AIUsage, run.usage_id)
            assert usage is not None and usage.model == run.model


async def test_stale_analysis_cannot_overwrite_verdict_but_records_returned_usage(
    database: Database,
) -> None:
    site_id, change_id = await _seed(database)
    async with database.session() as session:
        site = await session.get(Site, site_id)
        change = await session.get(ChangeEvent, change_id)
        assert site is not None and change is not None
        change.significant = False
        change.headline = "Accepted newer verdict"
        change.analysis_lease_token = "newer-owner"
        change.analysis_lease_expires_at = datetime.now(UTC) + timedelta(seconds=120)
        await session.commit()
        with pytest.raises(AnalysisOwnershipLost):
            await analyze_change(
                session,
                change,
                site,
                analyzer=InspectingAnalyzer(),
                system_prompt="Watch prices",
                model="gpt-4o-mini",
                lease_token="expired-owner",
            )
        await session.commit()
    async with database.session() as session:
        change = await session.get(ChangeEvent, change_id)
        assert change is not None and change.headline == "Accepted newer verdict"
        assert change.significant is False and change.analysis_lease_token == "newer-owner"
        assert not (await session.scalars(select(AnalysisRun))).all()
        usage = (await session.scalars(select(AIUsage))).one()
        assert usage.purpose == "discarded" and usage.total_tokens == 120
        assert usage.cost_usd is not None and usage.cost_usd > 0


async def test_unknown_cost_propagates_to_summary_and_buckets(
    admin_client: httpx.AsyncClient, database: Database
) -> None:
    response = await admin_client.post("/api/sites", json={"url": "https://example.test"})
    assert response.status_code == 201
    site_id = response.json()["id"]
    async with database.session() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        session.add_all(
            [
                AIUsage(
                    organization_id=site.organization_id,
                    site_id=site_id,
                    model="future-model",
                    cost_usd=None,
                    total_tokens=30,
                ),
                AIUsage(
                    organization_id=site.organization_id,
                    site_id=site_id,
                    model="known-model",
                    cost_usd=0.3,
                    total_tokens=10,
                ),
            ]
        )
        await session.commit()
    response = await admin_client.get("/api/usage/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["calls"] == 2 and body["total_tokens"] == 40
    assert body["total_cost_usd"] is None
    assert body["known_cost_usd"] == 0.3 and body["unknown_cost_calls"] == 1
    unknown = next(row for row in body["by_model"] if row["model"] == "future-model")
    assert unknown["cost_usd"] is None and unknown["unknown_cost_calls"] == 1
    for key in ("by_month", "by_site"):
        assert body[key][0]["cost_usd"] is None
        assert body[key][0]["known_cost_usd"] == 0.3


def test_unknown_price_missing_usage_and_valid_operator_override_are_distinct() -> None:
    assert estimate_cost("future-model", TokenUsage(1_000_000)).cost_usd is None
    assert estimate_cost("gpt-4o-mini", TokenUsage(reported=False)).cost_usd is None
    overridden = estimate_cost(
        "future-model", TokenUsage(1_000_000, 1_000_000), price_override=(2.0, 8.0)
    )
    assert overridden.cost_usd == 10.0 and overridden.pricing_source == "override"
    assert configured_prices("future-model", "2", None) is None
    assert configured_prices("future-model", "nan", "8") is None
    assert configured_prices("future-model", "2", "8") == (2, 8)
    assert configured_prices("gpt-4o-mini", "0", None) == (0, 0.60)
