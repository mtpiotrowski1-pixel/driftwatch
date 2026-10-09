"""Localized server-sent artifacts: the en/pl catalog, email rendering in
Polish, and the org-overridable email_language reaching the runner's mail."""

from __future__ import annotations

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.localization import _STRINGS, normalize_language, tr
from driftwatch.models import Recipient, Site, site_recipients
from driftwatch.notifications.render import (
    render_account_invite_email,
    render_change_email,
    render_password_reset_email,
    render_site_alert_email,
)
from driftwatch.runner import SiteRunner
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore
from tests.conftest import RecordingChannel, ScriptedCapturer, StubAnalyzer, create_org

_V1 = "<html><body><h1>Prices</h1><p>The widget costs 10 USD today</p></body></html>"
_V2 = "<html><body><h1>Prices</h1><p>The widget costs 12 USD today</p></body></html>"


def test_normalize_language_collapses_unknown_values() -> None:
    assert normalize_language("pl") == "pl"
    assert normalize_language(" PL ") == "pl"
    assert normalize_language("de") == "en"
    assert normalize_language(None) == "en"
    assert normalize_language("") == "en"


def test_catalogs_cover_the_same_keys() -> None:
    # A key added to one language must be added to the other, or PL silently
    # falls back to English for that string.
    assert set(_STRINGS["en"]) == set(_STRINGS["pl"])


def test_tr_falls_back_to_english_for_unknown_language() -> None:
    assert tr("de", "badge.change") == "Change detected"


def test_change_email_renders_in_polish() -> None:
    email = render_change_email(
        site_label="Cennik",
        site_url="https://example.com/cennik",
        headline="Cena wzrosła",
        summary="Z 10 na 12",
        significant=True,
        details_url="https://app.example/sites/1",
        detected_at="2026-07-04 10:00 UTC",
        language="pl",
    )
    assert email.text_body.startswith("Istotna zmiana")
    assert "Zobacz zmianę" in email.html_body
    assert "wykryto 2026-07-04 10:00 UTC" in email.text_body


def test_subject_template_severity_is_localized() -> None:
    email = render_change_email(
        site_label="Cennik",
        site_url="https://example.com",
        headline="",
        summary="",
        significant=True,
        details_url="https://app.example/sites/1",
        detected_at="now",
        subject_template="{site}: zmiana {severity}",
        language="pl",
    )
    assert email.subject == "Cennik: zmiana istotna"


def test_alert_email_renders_in_polish() -> None:
    email = render_site_alert_email(
        site_label="Cennik",
        site_url="https://example.com",
        title=tr("pl", "alert.blocked"),
        detail="HTTP 403",
        details_url="https://app.example/sites/1",
        detected_at="now",
        language="pl",
    )
    assert email.subject.startswith("Problem z monitorowaniem — Cennik")
    assert "Wymagana reakcja" in email.html_body


def test_reset_email_renders_in_polish() -> None:
    email = render_password_reset_email(
        reset_url="https://app.example/reset-password#token=t",
        valid_minutes=30,
        brand_name="Acme",
        language="pl",
    )
    assert email.subject == "Zresetuj hasło do Acme"
    assert "zignoruj tę wiadomość" in email.text_body
    assert "30 minut" in email.text_body


def test_account_invitation_renders_in_polish() -> None:
    email = render_account_invite_email(
        setup_url="https://app.example/reset-password#token=t",
        valid_hours=24,
        brand_name="Acme",
        language="pl",
    )
    assert email.subject == "Skonfiguruj konto w Acme"
    assert "jednorazowego linku" in email.text_body
    assert "24 godzin" in email.text_body
    assert "Ustaw hasło" in email.html_body


async def test_runner_mails_in_the_organizations_language(
    database: Database, settings: Settings, channel: RecordingChannel
) -> None:
    # An org that overrides email_language=pl gets Polish notification chrome
    # end to end: settings store -> runner -> dispatch -> rendered envelope.
    box = SecretBox(settings.secret_key)
    async with database.session() as session:
        org_id = await create_org(session)
        site = Site(url="https://example.test/pricing", name="Cennik", organization_id=org_id)
        recipient = Recipient(email="watch@example.com", active=True, organization_id=org_id)
        session.add_all([site, recipient])
        await session.flush()
        await session.execute(
            site_recipients.insert(), [{"site_id": site.id, "recipient_id": recipient.id}]
        )
        await SettingsStore(session, box, org_id=org_id).set_many({"email_language": "pl"})
        await session.commit()
        site_id = site.id

    runner = SiteRunner(
        database,
        ScriptedCapturer(queue=[_V1, _V2]),
        settings,
        analyzer=StubAnalyzer(significant=True),
        channel=channel,
    )
    await runner.run(site_id)  # baseline
    result = await runner.run(site_id)  # change -> notify

    assert result.notified is True
    assert channel.sent, "expected a delivered envelope"
    assert channel.sent[0].text_body.startswith("Istotna zmiana")
