"""The per-site check, expressed over a database session.

``run_check`` captures the page and decides whether content changed, persisting
a snapshot and a :class:`ChangeEvent` only when it did. ``analyze_change`` then
asks the analyzer for a verdict and records token usage. Neither step sends
email; the runner composes them with delivery. Keeping this layer free of
settings lookups and SMTP makes the whole decision path unit-testable against an
in-memory database with faked capture and analysis.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.enums import AnalysisStatus, NotificationMode, RetryStatus
from driftwatch.models import AIUsage, AnalysisRun, ChangeEvent, Project, Site, Snapshot
from driftwatch.monitoring.analysis_input import prepare_input
from driftwatch.monitoring.analysis_ownership import AnalysisOwnershipLost, release_analysis
from driftwatch.monitoring.analyzer import Analysis, ChangeAnalyzer
from driftwatch.monitoring.capture import (
    CapturedPage,
    CaptureError,
    CaptureTiming,
    PageCapturer,
    capture_with_retry,
)
from driftwatch.monitoring.cleaner import clean_dom
from driftwatch.monitoring.differ import html_diff
from driftwatch.monitoring.extractor import (
    BlockDiff,
    ContentBlock,
    canonical_text,
    diff_blocks,
    extract_blocks,
    format_for_ai,
)
from driftwatch.security.crypto import SecretBox
from driftwatch.security.interaction_secrets import (
    InteractionSecretUnavailable,
    redact_captured_html,
    redact_resolved_step_values,
    resolve_site_interaction_steps,
)


class DocumentChecker(Protocol):
    """Optional check-pipeline hook probing linked documents for in-place
    changes; returns synthetic blocks to report as added content."""

    async def __call__(
        self, session: AsyncSession, site: Site, blocks: list[ContentBlock]
    ) -> list[ContentBlock]: ...


class CheckStatus(StrEnum):
    BASELINE = "baseline"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    status: CheckStatus
    snapshot_id: int | None = None
    change_id: int | None = None


async def run_check(
    session: AsyncSession,
    site: Site,
    *,
    capturer: PageCapturer,
    secret_box: SecretBox | None = None,
    ignore_selectors: list[str] | None = None,
    document_checker: DocumentChecker | None = None,
    timing: CaptureTiming | None = None,
) -> CheckOutcome:
    cleaned_html, new_blocks = await _capture(
        session, site, capturer, secret_box, ignore_selectors, timing
    )
    new_text = canonical_text(new_blocks)
    previous = await _latest_snapshot(session, site.id)
    site.last_checked_at = datetime.now(UTC)

    # Probe linked documents even on a baseline so their fingerprints are
    # seeded; from then on an in-place replacement surfaces as an added block.
    doc_blocks: list[ContentBlock] = []
    if document_checker is not None:
        doc_blocks = await document_checker(session, site, new_blocks)

    if previous is None:
        snapshot = await _store_snapshot(session, site.id, cleaned_html, new_text)
        return CheckOutcome(CheckStatus.BASELINE, snapshot_id=snapshot.id)

    previous_blocks = await asyncio.to_thread(extract_blocks, previous.content_html)
    page_diff = diff_blocks(previous_blocks, new_blocks)
    added = [*page_diff.added, *doc_blocks]
    if not added and not page_diff.removed:
        return CheckOutcome(CheckStatus.UNCHANGED, snapshot_id=previous.id)

    # A linked document can change while the page itself is identical; there is
    # no new page content to store then, so the previous snapshot is reused.
    if page_diff.has_changes:
        snapshot = await _store_snapshot(session, site.id, cleaned_html, new_text)
    else:
        snapshot = previous
    diff = BlockDiff(added=added, removed=page_diff.removed)
    # The synthetic document lines join the display diff but never the stored
    # snapshot text, so they cannot echo as removals on the next check.
    display_text = "\n".join([new_text, *(block.render() for block in doc_blocks)])
    diff_html = await asyncio.to_thread(html_diff, canonical_text(previous_blocks), display_text)
    change = ChangeEvent(
        site_id=site.id,
        old_snapshot_id=previous.id,
        new_snapshot_id=snapshot.id,
        diff_text=format_for_ai(diff),
        diff_html=diff_html,
        analysis_status=AnalysisStatus.PENDING,
    )
    session.add(change)
    await session.flush()
    return CheckOutcome(CheckStatus.CHANGED, snapshot_id=snapshot.id, change_id=change.id)


async def analyze_change(
    session: AsyncSession,
    change: ChangeEvent,
    site: Site,
    *,
    analyzer: ChangeAnalyzer,
    system_prompt: str,
    model: str,
    lease_token: str | None = None,
    rules_source: str = "unknown",
    max_diff_chars: int = 16_000,
) -> Analysis:
    """Run analysis and persist the verdict and usage. Raises ``AnalysisError``."""
    prepared = prepare_input(
        diff_text=change.diff_text,
        url=site.url,
        system_prompt=system_prompt,
        model=model,
        max_chars=max_diff_chars,
    )
    analysis = await analyzer.analyze(
        diff_text=prepared.diff_text,
        url=site.url,
        system_prompt=system_prompt,
        model=model,
    )
    # A returned provider response consumed tokens even if its analysis lease
    # has since expired. Preserve that usage without accepting a stale verdict.
    usage = AIUsage(
        organization_id=site.organization_id,
        site_id=site.id,
        change_id=change.id,
        model=analysis.cost.model,
        prompt_tokens=analysis.cost.usage.prompt_tokens,
        completion_tokens=analysis.cost.usage.completion_tokens,
        total_tokens=analysis.cost.usage.total_tokens,
        cost_usd=analysis.cost.cost_usd,
        pricing_source=analysis.cost.pricing_source,
        purpose="change",
    )
    session.add(usage)
    await session.flush()
    if lease_token is not None:
        if not await release_analysis(
            session, change.id, lease_token, now=datetime.now(UTC), status=AnalysisStatus.SUCCEEDED
        ):
            usage.purpose = "discarded"
            raise AnalysisOwnershipLost("Analysis ownership expired; the late result was discarded")
        await session.refresh(change)
    change.analysis_status = AnalysisStatus.SUCCEEDED
    change.significant = analysis.significant
    change.headline = analysis.headline
    change.summary = analysis.summary
    change.ai_error = None
    # Append-only history: a re-analysis overwrites the fields above, so each
    # successful run is also logged to keep the previous verdicts visible.
    session.add(
        AnalysisRun(
            change_id=change.id,
            significant=analysis.significant,
            headline=analysis.headline,
            summary=analysis.summary,
            model=model,
            rules_source=rules_source,
            rules_version=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            system_prompt=system_prompt,
            input_sha256=prepared.sha256,
            input_truncated=prepared.truncated,
            usage_id=usage.id,
        )
    )
    return analysis


# Backoff schedule for automatic retries; running out flips the change to the
# action-required queue for a human to look at.
_RETRY_BACKOFF_MINUTES: tuple[int, ...] = (5, 15, 60, 240)


def _plan_next_retry(attempt: int) -> datetime | None:
    if attempt > len(_RETRY_BACKOFF_MINUTES):
        return None
    return datetime.now(UTC) + timedelta(minutes=_RETRY_BACKOFF_MINUTES[attempt - 1])


def record_analysis_failure(change: ChangeEvent, error: str) -> None:
    change.analysis_status = AnalysisStatus.ERROR
    change.ai_error = error
    change.ai_retry_count += 1
    change.next_retry_at = _plan_next_retry(change.ai_retry_count)
    change.retry_status = None if change.next_retry_at else RetryStatus.REQUIRES_ACTION


def clear_retry_state(change: ChangeEvent) -> None:
    """Mark a change fully resolved: no pending analysis or delivery.

    The retry sweep (``find_changes_to_retry``) selects on a lingering
    ``ai_error``/``notification_error``, so those must be cleared here too;
    otherwise a resolved change keeps matching the query and, with no
    ``next_retry_at``, is treated as due on every tick — an endless loop.
    """
    change.next_retry_at = None
    change.retry_status = None
    change.ai_error = None
    change.notification_error = None


def resolve_notification_mode(
    site: Site, project: Project | None, default: NotificationMode
) -> NotificationMode:
    chosen = site.notification_mode or (project.notification_mode if project else None) or default
    return _coerce_mode(chosen)


def should_notify(*, significant: bool, mode: NotificationMode) -> bool:
    # ``mode`` may arrive as a plain string from the database, so compare by value.
    return _coerce_mode(mode) is NotificationMode.ALWAYS or significant


def _coerce_mode(value: NotificationMode | str) -> NotificationMode:
    try:
        return NotificationMode(value)
    except ValueError:
        return NotificationMode.ONLY_SIGNIFICANT


async def _capture(
    session: AsyncSession,
    site: Site,
    capturer: PageCapturer,
    secret_box: SecretBox | None,
    ignore_selectors: list[str] | None,
    timing: CaptureTiming | None = None,
) -> tuple[str, list[ContentBlock]]:
    try:
        interaction_steps = await resolve_site_interaction_steps(session, secret_box, site)
    except InteractionSecretUnavailable as exc:
        raise CaptureError(str(exc)) from exc
    try:
        captured = await capture_with_retry(
            capturer,
            url=site.url,
            css_selector=site.css_selector,
            interaction_steps=interaction_steps,
            timing=timing,
        )
    except CaptureError as exc:
        # A browser or injected capture adapter may repeat call arguments in an
        # exception. Scrub the ephemeral values before the runner persists the
        # detail or exposes it through the site API.
        exc.args = (redact_resolved_step_values(str(exc), interaction_steps),)
        raise
    raw_html = captured.html if isinstance(captured, CapturedPage) else captured
    if not raw_html.strip():
        raise CaptureError("Capture returned no document HTML")
    base_url = captured.base_url if isinstance(captured, CapturedPage) else site.url
    raw_html = redact_resolved_step_values(raw_html, interaction_steps)
    # Parsing and cleaning a full page is CPU-bound; keep it off the event loop.
    cleaned = await asyncio.to_thread(
        clean_dom, raw_html, ignore_selectors=ignore_selectors, base_url=base_url
    )
    cleaned = await asyncio.to_thread(redact_captured_html, cleaned, interaction_steps)
    blocks = await asyncio.to_thread(extract_blocks, cleaned)
    return cleaned, blocks


async def capture_and_store(
    session: AsyncSession,
    site: Site,
    *,
    capturer: PageCapturer,
    secret_box: SecretBox | None = None,
    ignore_selectors: list[str] | None = None,
    timing: CaptureTiming | None = None,
) -> int:
    """Capture the page now and store it as a fresh snapshot, unconditionally."""
    cleaned_html, blocks = await _capture(
        session, site, capturer, secret_box, ignore_selectors, timing
    )
    snapshot = await _store_snapshot(session, site.id, cleaned_html, canonical_text(blocks))
    site.last_checked_at = datetime.now(UTC)
    return snapshot.id


async def _store_snapshot(
    session: AsyncSession, site_id: int, content_html: str, content_text: str
) -> Snapshot:
    snapshot = Snapshot(site_id=site_id, content_html=content_html, content_text=content_text)
    session.add(snapshot)
    await session.flush()
    return snapshot


async def _latest_snapshot(session: AsyncSession, site_id: int) -> Snapshot | None:
    stmt = select(Snapshot).where(Snapshot.site_id == site_id).order_by(Snapshot.id.desc()).limit(1)
    return (await session.execute(stmt)).scalars().first()
