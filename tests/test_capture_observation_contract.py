"""A missing observation must not become a successful empty baseline."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from tests.conftest import ScriptedCapturer, create_org

from driftwatch.db import Database
from driftwatch.models import Site, Snapshot
from driftwatch.monitoring.capture import CaptureError
from driftwatch.monitoring.pipeline import run_check


@pytest.mark.parametrize("missing", ["", " \n\t"])
async def test_missing_capture_preserves_previous_healthy_snapshot(
    database: Database, missing: str
) -> None:
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(organization_id=org_id, url="https://example.test")
        session.add(site)
        await session.flush()
        with pytest.raises(CaptureError, match="no document HTML"):
            await run_check(session, site, capturer=ScriptedCapturer(html=missing))
        assert site.last_checked_at is None
        healthy = await run_check(
            session, site, capturer=ScriptedCapturer(html="<div>Basic 20 EUR</div>")
        )
        checked_at = site.last_checked_at
        with pytest.raises(CaptureError, match="no document HTML"):
            await run_check(session, site, capturer=ScriptedCapturer(html=missing))
        assert site.last_checked_at == checked_at
        snapshots = (await session.scalars(select(Snapshot))).all()
        assert len(snapshots) == 1 and snapshots[0].id == healthy.snapshot_id
