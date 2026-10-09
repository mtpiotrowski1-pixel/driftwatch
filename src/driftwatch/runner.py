"""Conduct a full check for one site: capture, analyze, notify — and recover.

This is the single composition point where the pure pipeline meets settings and
email delivery. The scheduler and the "run now" API call :meth:`SiteRunner.run`;
the scheduler's retry pass and the manual retry endpoint call
:meth:`SiteRunner.reprocess_change`, which resumes a change without re-capturing
and reuses an existing AI verdict so a delivery retry never re-bills the model.
Analyzer and channel are built from current settings on each run; tests inject
fakes through the constructor.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.enums import AlertCode, AnalysisMode, AnalysisStatus, NotificationMode
from driftwatch.exceptions import AccessDenied, NotFoundError, PlanLimitReached
from driftwatch.localization import tr
from driftwatch.models import AIUsage, ChangeEvent, Organization, Project, Recipient, Site
from driftwatch.monitoring.analysis_input import prepare_input
from driftwatch.monitoring.analysis_ownership import (
    ANALYSIS_TIMEOUT_SECONDS,
    AnalysisOwnershipLost,
    claim_analysis,
    release_analysis,
)
from driftwatch.monitoring.analyzer import (
    Analysis,
    AnalysisError,
    ChangeAnalyzer,
    OpenAIChangeAnalyzer,
)
from driftwatch.monitoring.capture import (
    CaptureError,
    CaptureTiming,
    PageCapturer,
    SupportsCaptureTiming,
)
from driftwatch.monitoring.linked_assets import LinkedDocumentChecker
from driftwatch.monitoring.pipeline import (
    CheckStatus,
    DocumentChecker,
    analyze_change,
    capture_and_store,
    clear_retry_state,
    record_analysis_failure,
    resolve_notification_mode,
    run_check,
    should_notify,
)
from driftwatch.monitoring.prompts import (
    ResolvedRules,
    build_system_prompt,
    resolve_importance_rules,
)
from driftwatch.monitoring.usage import configured_prices
from driftwatch.notifications.dispatch import (
    dispatch_change,
    resolve_recipients,
    send_site_alert,
    skipped_delivery_log,
)
from driftwatch.notifications.email import (
    EmailChannel,
    default_sender_email,
)
from driftwatch.notifications.email import (
    build_channel as build_channel,
)
from driftwatch.notifications.render import render_site_alert_email
from driftwatch.quota import reserve_ai_check
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore

logger = logging.getLogger(__name__)

_ALERT_THROTTLE = timedelta(hours=6)
_MAX_TECHNICAL_ALERT_RECIPIENTS = 50
_ALERT_TITLE_KEYS: dict[AlertCode, str] = {
    AlertCode.SELECTOR_MISSING: "alert.selector_missing",
    AlertCode.BLOCKED: "alert.blocked",
    AlertCode.CAPTURE_FAILED: "alert.capture_failed",
}


@dataclass(slots=True)
class RunResult:
    site_id: int
    status: CheckStatus
    change_id: int | None = None
    significant: bool | None = None
    notified: bool = False
    recipients: int = 0
    ai_error: str | None = None
    capture_error: str | None = None
    notification_mode: NotificationMode | None = None


class SiteRunner:
    def __init__(
        self,
        db: Database,
        capturer: PageCapturer,
        settings: Settings,
        *,
        analyzer: ChangeAnalyzer | None = None,
        channel: EmailChannel | None = None,
        document_checker: DocumentChecker | None = None,
    ) -> None:
        self._db = db
        self._capturer = capturer
        self._settings = settings
        self._analyzer_override = analyzer
        self._channel_override = channel
        # Applied only when the organization enables watch_linked_documents;
        # tests inject a checker wired to a mock transport.
        self._document_checker = document_checker or LinkedDocumentChecker()
        self._box = SecretBox(*settings.encryption_keys)

    async def run(self, site_id: int, *, analyze: bool = True) -> RunResult:
        async with self._db.session() as session:
            site = await self._require_active_site(session, site_id)

            store = SettingsStore(session, self._box, org_id=site.organization_id)
            timing = await self._capture_timing(store)
            ignore = [*await store.ignore_selectors(), *(site.ignore_selectors or [])]
            checker = self._document_checker if await store.watch_linked_documents() else None
            try:
                outcome = await run_check(
                    session,
                    site,
                    capturer=self._capturer,
                    secret_box=self._box,
                    ignore_selectors=ignore,
                    document_checker=checker,
                    timing=timing,
                )
            except CaptureError as exc:
                await self._raise_capture_alert(session, store, site, exc)
                await session.commit()
                return RunResult(site_id, CheckStatus.UNCHANGED, capture_error=str(exc))

            _clear_site_alert(site)
            result = RunResult(site_id, outcome.status, change_id=outcome.change_id)
            if not analyze and outcome.change_id is not None:
                change = await session.get(ChangeEvent, outcome.change_id)
                assert change is not None
                change.analysis_status = AnalysisStatus.NOT_REQUESTED
            if analyze and outcome.status is CheckStatus.CHANGED and outcome.change_id is not None:
                change = await session.get(ChangeEvent, outcome.change_id)
                assert change is not None
                project = await self._project_of(session, site)
                await self._analyze_and_notify(session, store, site, project, change, result)

            await session.commit()
            return result

    async def snapshot(self, site_id: int) -> RunResult:
        async with self._db.session() as session:
            site = await self._require_active_site(session, site_id)
            store = SettingsStore(session, self._box, org_id=site.organization_id)
            timing = await self._capture_timing(store)
            ignore = [*await store.ignore_selectors(), *(site.ignore_selectors or [])]
            try:
                await capture_and_store(
                    session,
                    site,
                    capturer=self._capturer,
                    secret_box=self._box,
                    ignore_selectors=ignore,
                    timing=timing,
                )
            except CaptureError as exc:
                await self._raise_capture_alert(session, store, site, exc)
                await session.commit()
                return RunResult(site_id, CheckStatus.UNCHANGED, capture_error=str(exc))
            _clear_site_alert(site)
            await session.commit()
            return RunResult(site_id, CheckStatus.BASELINE)

    async def reprocess_change(self, change_id: int, *, force_delivery: bool = False) -> RunResult:
        async with self._db.session() as session:
            change = await session.get(ChangeEvent, change_id)
            if change is None:
                raise NotFoundError(f"change {change_id} not found")
            site = await session.get(Site, change.site_id)
            assert site is not None
            await self._require_active_organization(session, site.organization_id)
            store = SettingsStore(session, self._box, org_id=site.organization_id)
            project = await self._project_of(session, site)
            result = RunResult(site.id, CheckStatus.CHANGED, change_id=change.id)

            if change.significant is None or change.ai_error:
                await self._analyze_and_notify(
                    session,
                    store,
                    site,
                    project,
                    change,
                    result,
                    force_delivery=force_delivery,
                )
            else:
                result.significant = change.significant
                mode = resolve_notification_mode(
                    site, project, await store.default_notification_mode()
                )
                result.notification_mode = mode
                if should_notify(significant=change.significant, mode=mode):
                    await self._deliver(
                        session,
                        store,
                        site,
                        change,
                        result,
                        force=force_delivery,
                    )
                else:
                    clear_retry_state(change)

            await session.commit()
            return result

    async def analyze_only(self, change_id: int) -> RunResult:
        """Re-run AI analysis for a change and store the verdict — never emails."""
        async with self._db.session() as session:
            change = await session.get(ChangeEvent, change_id)
            if change is None:
                raise NotFoundError(f"change {change_id} not found")
            site = await session.get(Site, change.site_id)
            assert site is not None
            await self._require_active_organization(session, site.organization_id)
            store = SettingsStore(session, self._box, org_id=site.organization_id)
            project = await self._project_of(session, site)
            result = RunResult(site.id, CheckStatus.CHANGED, change_id=change.id)
            await self._run_analysis(session, store, site, project, change, result, force=True)
            await session.commit()
            return result

    async def analyze_preview(self, change_id: int, rules_text: str) -> Analysis:
        """Dry-run draft importance rules against a past change.

        The verdict is returned but never written to the change, so rules can be
        iterated without rewriting history. The call still bills the model, so it
        records an ``AIUsage`` row tagged as a preview and respects the plan's
        monthly AI quota. Raises
        :class:`AnalysisError` on analyzer failure."""
        async with self._db.session() as session:
            change = await session.get(ChangeEvent, change_id)
            if change is None:
                raise NotFoundError(f"change {change_id} not found")
            site = await session.get(Site, change.site_id)
            assert site is not None
            await self._require_active_organization(session, site.organization_id)

            store = SettingsStore(session, self._box, org_id=site.organization_id)
            system_prompt = build_system_prompt(
                ResolvedRules("draft", rules_text.strip()), base_prompt=await store.base_prompt()
            )
            openai_config = await store.openai(
                default_model=self._settings.openai_model, env_key=self._settings.openai_api_key
            )
            analyzer = self._analyzer_override or OpenAIChangeAnalyzer(
                openai_config.api_key,
                max_diff_chars=self._settings.max_diff_chars_for_ai,
                price_override=await _price_override(store, openai_config.model),
            )
            await reserve_ai_check(session, site.organization_id)
            await session.commit()
            prepared = prepare_input(
                diff_text=change.diff_text,
                url=site.url,
                system_prompt=system_prompt,
                model=openai_config.model,
                max_chars=self._settings.max_diff_chars_for_ai,
            )
            async with asyncio.timeout(ANALYSIS_TIMEOUT_SECONDS):
                analysis = await analyzer.analyze(
                    diff_text=prepared.diff_text,
                    url=site.url,
                    system_prompt=system_prompt,
                    model=openai_config.model,
                )
            session.add(
                AIUsage(
                    organization_id=site.organization_id,
                    site_id=site.id,
                    change_id=change.id,
                    model=analysis.cost.model,
                    prompt_tokens=analysis.cost.usage.prompt_tokens,
                    completion_tokens=analysis.cost.usage.completion_tokens,
                    total_tokens=analysis.cost.usage.total_tokens,
                    cost_usd=analysis.cost.cost_usd,
                    pricing_source=analysis.cost.pricing_source,
                    purpose="preview",
                )
            )
            await session.commit()
            return analysis

    async def _run_analysis(
        self,
        session: AsyncSession,
        store: SettingsStore,
        site: Site,
        project: Project | None,
        change: ChangeEvent,
        result: RunResult,
        *,
        force: bool = False,
    ) -> bool:
        token = await claim_analysis(session, change.id, now=datetime.now(UTC), force=force)
        if token is None:
            await session.refresh(change)
            result.significant = change.significant
            result.ai_error = "Analysis already in progress or completed"
            return False
        await session.refresh(change)
        try:
            await reserve_ai_check(session, site.organization_id)
        except PlanLimitReached:
            logger.info(
                "org %s reached its monthly AI limit; skipping analysis of site %s",
                site.organization_id,
                site.id,
            )
            error = "Monthly AI analysis limit reached for this plan"
            await release_analysis(
                session,
                change.id,
                token,
                now=datetime.now(UTC),
                status=AnalysisStatus.QUOTA_BLOCKED,
                error=error,
                next_retry_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            await session.refresh(change)
            result.ai_error = error
            return False

        rules = resolve_importance_rules(
            site_prompt=site.prompt,
            project_prompt=project.prompt if project else None,
            global_rules=await store.importance_rules(),
        )
        system_prompt = build_system_prompt(rules, base_prompt=await store.base_prompt())
        openai_config = await store.openai(
            default_model=self._settings.openai_model, env_key=self._settings.openai_api_key
        )
        # Commit the atomic reservation before the external side effect. The
        # retry marker makes a process crash during the call recoverable instead
        # of leaving a silent, permanently unanalyzed change.
        await session.commit()
        try:
            analyzer = self._analyzer_override or OpenAIChangeAnalyzer(
                openai_config.api_key,
                max_diff_chars=self._settings.max_diff_chars_for_ai,
                price_override=await _price_override(store, openai_config.model),
            )
            async with asyncio.timeout(ANALYSIS_TIMEOUT_SECONDS):
                analysis = await analyze_change(
                    session,
                    change,
                    site,
                    analyzer=analyzer,
                    system_prompt=system_prompt,
                    model=openai_config.model,
                    lease_token=token,
                    rules_source=rules.source,
                    max_diff_chars=self._settings.max_diff_chars_for_ai,
                )
        except AnalysisOwnershipLost as exc:
            result.ai_error = str(exc)
            return False
        except (AnalysisError, TimeoutError) as exc:
            error = str(exc) if isinstance(exc, AnalysisError) else "AI analysis timed out"
            logger.info("analysis deferred for site %s: %s", site.id, exc)
            if await release_analysis(
                session,
                change.id,
                token,
                now=datetime.now(UTC),
                status=AnalysisStatus.ERROR,
                error=error,
            ):
                await session.refresh(change)
                record_analysis_failure(change, error)
            result.ai_error = error
            return False
        change.next_retry_at = None
        change.retry_status = None
        result.significant = analysis.significant
        return True

    async def _require_active_site(self, session: AsyncSession, site_id: int) -> Site:
        site = await session.get(Site, site_id)
        if site is None:
            raise NotFoundError(f"site {site_id} not found")
        await self._require_active_organization(session, site.organization_id)
        return site

    @staticmethod
    async def _require_active_organization(session: AsyncSession, org_id: int) -> None:
        organization = await session.get(Organization, org_id)
        if organization is None or not organization.is_active:
            raise AccessDenied("This organization is suspended or no longer exists")

    async def _analyze_and_notify(
        self,
        session: AsyncSession,
        store: SettingsStore,
        site: Site,
        project: Project | None,
        change: ChangeEvent,
        result: RunResult,
        *,
        force_delivery: bool = False,
    ) -> None:
        # Both notification modes deliver on some verdict, so with no recipients
        # and no webhook the analysis could only produce an undeliverable result:
        # skip the AI spend entirely and leave an audited SKIPPED row. Explicit
        # re-analysis (:meth:`analyze_only`) still works without recipients.
        if await store.webhook() is None and not await resolve_recipients(session, site):
            logger.info(
                "site %s resolves no recipients and has no webhook; skipping analysis", site.id
            )
            session.add(skipped_delivery_log(change.id))
            change.analysis_status = AnalysisStatus.SKIPPED_NO_DELIVERY
            clear_retry_state(change)
            return

        if site.analysis_mode == AnalysisMode.DISABLED:
            change.analysis_status = AnalysisStatus.DISABLED
            language = await store.email_language()
            change.headline = "Zmiana treści" if language == "pl" else "Content changed"
            change.summary = (
                "Wykryto zmianę treści. Analiza AI jest wyłączona; szczegóły zawiera diff."
                if language == "pl"
                else "Content changed. AI analysis is disabled; review the diff for details."
            )
            result.notification_mode = NotificationMode.ALWAYS
            await self._deliver(session, store, site, change, result, force=force_delivery)
            return

        if not await self._run_analysis(session, store, site, project, change, result):
            return

        mode = resolve_notification_mode(site, project, await store.default_notification_mode())
        result.notification_mode = mode
        if not should_notify(significant=bool(result.significant), mode=mode):
            clear_retry_state(change)
            return

        await self._deliver(
            session,
            store,
            site,
            change,
            result,
            force=force_delivery,
        )

    async def _deliver(
        self,
        session: AsyncSession,
        store: SettingsStore,
        site: Site,
        change: ChangeEvent,
        result: RunResult,
        *,
        force: bool = False,
    ) -> None:
        channel = self._channel_override or build_channel(
            await store.email(default_from=self._fallback_from())
        )
        logs = await dispatch_change(
            session,
            change,
            site,
            channel=channel,
            app_base_url=self._settings.base_url,
            subject_template=await store.email_subject_template(),
            intro=await store.email_body_intro(),
            webhook=await store.webhook(),
            today=datetime.now(self._settings.timezone).date(),
            language=await store.email_language(),
            secret_box=self._box,
            force=force,
        )
        result.recipients = len(logs)
        if change.notified_at is not None:
            result.notified = True

    async def _raise_capture_alert(
        self, session: AsyncSession, store: SettingsStore, site: Site, exc: CaptureError
    ) -> None:
        code = exc.code
        now = datetime.now(UTC)
        last_at = site.last_alert_at
        if last_at is not None and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=UTC)
        throttled = (
            site.last_alert_code == code and last_at is not None and now - last_at < _ALERT_THROTTLE
        )
        if site.last_alert_code != code:
            site.last_alert_at = None
        site.last_alert_code = code
        site.last_alert_detail = str(exc)
        site.consecutive_failure_count = (site.consecutive_failure_count or 0) + 1

        # Crossing the failure threshold sends one stronger "site appears down"
        # email that bypasses the normal throttle exactly once — below and above
        # the threshold the regular per-code throttle applies unchanged.
        threshold = await store.site_down_failure_threshold()
        escalate = site.consecutive_failure_count == threshold
        if throttled and not escalate:
            return

        recipients = await self._alert_recipients(session, store, site)
        if not recipients:
            return
        language = await store.email_language()
        if escalate:
            title = tr(language, "alert.site_down")
            detail = tr(
                language,
                "alert.site_down_detail",
                count=str(site.consecutive_failure_count),
                detail=str(exc),
            )
        else:
            title = tr(language, _ALERT_TITLE_KEYS.get(code, "alert.generic"))
            detail = str(exc)
        email = render_site_alert_email(
            site_label=site.name or site.url,
            site_url=site.url,
            title=title,
            detail=detail,
            details_url=f"{self._settings.base_url.rstrip('/')}/sites/{site.id}",
            detected_at=now.strftime("%Y-%m-%d %H:%M UTC"),
            language=language,
        )
        channel = self._channel_override or build_channel(
            await store.email(default_from=self._fallback_from())
        )
        if await send_site_alert(channel, email, recipients):
            site.last_alert_at = now

    async def _alert_recipients(
        self, session: AsyncSession, store: SettingsStore, site: Site
    ) -> list[str]:
        ids = await store.technical_alert_recipient_ids()
        if ids:
            # Settings written before API validation existed may contain foreign,
            # duplicate, invalid, or excessively large ID lists. Background jobs
            # use an unscoped session, so enforce the tenant boundary again here.
            selected_ids: list[int] = []
            seen_ids: set[int] = set()
            for recipient_id in ids:
                if recipient_id <= 0 or recipient_id in seen_ids:
                    continue
                seen_ids.add(recipient_id)
                selected_ids.append(recipient_id)
                if len(selected_ids) == _MAX_TECHNICAL_ALERT_RECIPIENTS:
                    break
            rows = (
                await session.execute(
                    select(Recipient).where(
                        Recipient.id.in_(selected_ids),
                        Recipient.organization_id == site.organization_id,
                        Recipient.active.is_(True),
                    )
                )
            ).scalars()
            emails_by_id = {row.id: row.email for row in rows}
            recipients: list[str] = []
            seen_addresses: set[str] = set()
            for recipient_id in selected_ids:
                email = emails_by_id.get(recipient_id)
                if email is None or email.casefold() in seen_addresses:
                    continue
                seen_addresses.add(email.casefold())
                recipients.append(email)
            return recipients
        return [recipient.email for recipient in await resolve_recipients(session, site)]

    async def _capture_timing(self, store: SettingsStore) -> CaptureTiming | None:
        """Resolve timing for this request without changing another tenant's capture."""
        if not isinstance(self._capturer, SupportsCaptureTiming):
            return None
        timeout_seconds, settle_ms = await store.capture_timing(
            default_timeout_seconds=self._settings.capture_timeout_seconds,
            default_settle_ms=self._settings.capture_settle_ms,
        )
        return CaptureTiming(timeout_seconds=timeout_seconds, settle_ms=settle_ms)

    @staticmethod
    async def _project_of(session: AsyncSession, site: Site) -> Project | None:
        return await session.get(Project, site.project_id) if site.project_id else None

    def _fallback_from(self) -> str:
        return default_sender_email(self._settings.base_url)


def _clear_site_alert(site: Site) -> None:
    """A successful capture resolves any operational alert and the failure streak."""
    if site.last_alert_code is not None:
        site.last_alert_code = None
        site.last_alert_at = None
        site.last_alert_detail = None
    if site.consecutive_failure_count:
        site.consecutive_failure_count = 0


async def _price_override(store: SettingsStore, model: str) -> tuple[float, float] | None:
    input_raw = await store.get("openai_price_input_per_1m")
    output_raw = await store.get("openai_price_output_per_1m")
    if not (input_raw or output_raw):
        return None
    prices = configured_prices(model, input_raw, output_raw)
    if prices is None:
        raise AnalysisError(
            "Token price overrides are invalid or incomplete for the configured model"
        )
    return prices
