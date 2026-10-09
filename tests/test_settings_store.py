"""Tests for the encrypted settings store and its typed accessors."""

from __future__ import annotations

from sqlalchemy import select
from tests.conftest import create_org

from driftwatch.db import Database
from driftwatch.enums import EmailChannelName, NotificationMode
from driftwatch.models import OrgSetting, Setting
from driftwatch.security.crypto import SecretBox
from driftwatch.settings_store import SettingsStore


async def test_secret_is_encrypted_at_rest_and_masked_in_public(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many({"openai_api_key": "sk-secret", "openai_model": "gpt-4o"})
        await session.commit()

    async with database.session() as session:
        store = SettingsStore(session, box)
        assert await store.get("openai_api_key") == "sk-secret"
        public = await store.public_values()
    assert public["openai_api_key"] == "********"
    assert public["openai_model"] == "gpt-4o"


async def test_masked_value_leaves_existing_secret_untouched(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many({"openai_api_key": "sk-original"})
        await session.commit()
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many({"openai_api_key": "********"})
        await session.commit()
    async with database.session() as session:
        store = SettingsStore(session, box)
        assert await store.get("openai_api_key") == "sk-original"


async def test_empty_instance_secret_removes_the_stored_credential(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many({"openai_api_key": "sk-original"})
        await session.flush()
        await store.set_many({"openai_api_key": ""})
        await session.commit()

    async with database.session() as session:
        store = SettingsStore(session, box)
        assert await store.get("openai_api_key") is None
        assert "openai_api_key" not in await store.public_values()
        assert await session.get(Setting, "openai_api_key") is None


async def test_secret_read_reencrypts_with_primary_rotation_key(database: Database) -> None:
    old = SecretBox("old-encryption-key")
    async with database.session() as session:
        await SettingsStore(session, old).set_many({"openai_api_key": "sk-rotate"})
        await session.commit()

    rotating = SecretBox("new-encryption-key", "old-encryption-key")
    async with database.session() as session:
        assert await SettingsStore(session, rotating).get("openai_api_key") == "sk-rotate"
        await session.commit()

    async with database.session() as session:
        stored = await session.get(Setting, "openai_api_key")
        assert stored is not None
        assert SecretBox("new-encryption-key").decrypt(stored.value) == "sk-rotate"
        assert old.decrypt(stored.value) is None


async def test_email_config_selects_channel_by_priority(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        assert (await store.email(default_from="x@y.z")).channel is EmailChannelName.LOG

        await store.set_many({"smtp_host": "smtp.example.com"})
        assert (await store.email(default_from="x@y.z")).channel is EmailChannelName.SMTP

        await store.set_many({"brevo_api_key": "brevo-key"})
        assert (await store.email(default_from="x@y.z")).channel is EmailChannelName.BREVO


async def test_email_provider_and_security_are_explicit(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many(
            {"email_provider": "smtp", "smtp_host": "smtp.example.com", "smtp_security": "ssl"}
        )
        config = await store.email(default_from="x@y.z")
        assert config.channel is EmailChannelName.SMTP
        assert config.smtp_security == "ssl"

        await store.set_many({"email_provider": "log"})
        assert (await store.email(default_from="x@y.z")).channel is EmailChannelName.LOG


async def test_email_language_defaults_and_org_override(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        store = SettingsStore(session, box)
        assert await store.email_language() == "en"
        # Unsupported stored values collapse to English rather than erroring.
        await store.set_many({"email_language": "nonsense"})
        assert await store.email_language() == "en"

        await SettingsStore(session, box, org_id=org_id).set_many({"email_language": "pl"})
        await session.flush()
        assert await SettingsStore(session, box, org_id=org_id).email_language() == "pl"
        # The instance layer is untouched by the org override.
        assert await store.email_language() == "en"


async def test_from_name_falls_back_to_brand_name(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        # Nothing configured: the stock product name.
        assert (await store.email(default_from="x@y.z")).from_name == "Driftwatch"
        # A configured brand signs the mail on a white-label deployment.
        await store.set_many({"brand_name": "Acme Watch"})
        assert (await store.email(default_from="x@y.z")).from_name == "Acme Watch"
        # An explicit sender name still wins over the brand.
        await store.set_many({"notification_from_name": "Alerts"})
        assert (await store.email(default_from="x@y.z")).from_name == "Alerts"


async def test_capture_pacing(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many(
            {
                "capture_min_interval_seconds": "2",
                "capture_jitter_ms": "500",
            }
        )
        assert await store.capture_pacing() == (2.0, 0.5)


async def test_typed_accessors_parse_values(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many(
            {
                "default_notification_mode": "always",
                "ignore_selectors": '[".ads", "#cookie"]',
                "openai_model": "gpt-4.1-mini",
            }
        )
        assert await store.default_notification_mode() is NotificationMode.ALWAYS
        assert await store.ignore_selectors() == [".ads", "#cookie"]
        assert (await store.openai(default_model="gpt-4o-mini")).model == "gpt-4.1-mini"


async def test_capture_timing_and_retention_override_defaults(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        # With nothing stored, both fall back to the supplied defaults.
        assert await store.capture_timing(default_timeout_seconds=30, default_settle_ms=750) == (
            30,
            750,
        )
        assert await store.snapshot_retention(default=20) == 20

        await store.set_many(
            {
                "capture_timeout_seconds": "12",
                "capture_settle_ms": "1500",
                "snapshot_retention": "5",
            }
        )
        assert await store.capture_timing(default_timeout_seconds=30, default_settle_ms=750) == (
            12.0,
            1500,
        )
        assert await store.snapshot_retention(default=20) == 5


async def test_invalid_notification_mode_falls_back(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        store = SettingsStore(session, box)
        await store.set_many({"default_notification_mode": "nonsense"})
        assert await store.default_notification_mode() is NotificationMode.ONLY_SIGNIFICANT


# --- Per-organization layering ------------------------------------------------


async def test_org_inherits_instance_default(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        await SettingsStore(session, box).set_many({"base_prompt": "instance rules"})
        await session.flush()
        org_store = SettingsStore(session, box, org_id=org_id)
        assert await org_store.get("base_prompt") == "instance rules"


async def test_org_override_wins_and_is_isolated(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_a = await create_org(session, "A")
        org_b = await create_org(session, "B")
        await SettingsStore(session, box).set_many({"base_prompt": "instance rules"})
        await SettingsStore(session, box, org_id=org_a).set_many({"base_prompt": "A rules"})
        await session.flush()

        assert await SettingsStore(session, box, org_id=org_a).get("base_prompt") == "A rules"
        # B never overrode it, so it inherits the instance default.
        b_store = SettingsStore(session, box, org_id=org_b)
        assert await b_store.get("base_prompt") == "instance rules"
        # The instance default is untouched by A's override.
        assert await SettingsStore(session, box).get("base_prompt") == "instance rules"


async def test_clearing_an_override_reverts_to_default(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        await SettingsStore(session, box).set_many({"base_prompt": "instance rules"})
        await SettingsStore(session, box, org_id=org_id).set_many({"base_prompt": "org rules"})
        await session.flush()
        assert await SettingsStore(session, box, org_id=org_id).get("base_prompt") == "org rules"

        await SettingsStore(session, box, org_id=org_id).set_many({"base_prompt": ""})
        await session.flush()
        assert (
            await SettingsStore(session, box, org_id=org_id).get("base_prompt") == "instance rules"
        )


async def test_instance_only_key_cannot_be_overridden(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        await SettingsStore(session, box).set_many({"openai_model": "platform-model"})
        await SettingsStore(session, box, org_id=org_id).set_many({"openai_model": "tenant-model"})
        await session.flush()
        org_store = SettingsStore(session, box, org_id=org_id)
        # The override is ignored: an org resolves an instance-only key to the default.
        assert await org_store.get("openai_model") == "platform-model"


async def test_platform_secret_cannot_be_overridden_by_an_org_store(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        await SettingsStore(session, box).set_many({"openai_api_key": "sk-platform"})
        await SettingsStore(session, box, org_id=org_id).set_many({"openai_api_key": "sk-org"})
        await session.flush()

        org_store = SettingsStore(session, box, org_id=org_id)
        assert await org_store.get("openai_api_key") == "sk-platform"
        row = (
            await session.execute(select(OrgSetting).where(OrgSetting.key == "openai_api_key"))
        ).scalar_one_or_none()
        assert row is None
        assert "openai_api_key" not in await org_store.public_values()


async def test_defaults_values_returns_instance_layer(database: Database) -> None:
    box = SecretBox("app-secret")
    async with database.session() as session:
        org_id = await create_org(session)
        await SettingsStore(session, box).set_many({"base_prompt": "instance rules"})
        await SettingsStore(session, box, org_id=org_id).set_many({"base_prompt": "org rules"})
        await session.flush()
        org_store = SettingsStore(session, box, org_id=org_id)
        # public_values is the effective view; defaults_values is what is inherited.
        assert (await org_store.public_values())["base_prompt"] == "org rules"
        assert (await org_store.defaults_values())["base_prompt"] == "instance rules"
