"""Deployment-safety checks baked into Settings validation."""

from __future__ import annotations

import pytest

from driftwatch.config import Settings

_STRONG_KEY = "x" * 32
_PUBLIC_EXPOSURE = {"host": "0.0.0.0", "base_url": "https://driftwatch.example.com"}
_PUBLIC = {
    **_PUBLIC_EXPOSURE,
    "session_secret_key": "s" * 32,
    "encryption_key": "e" * 32,
}


def test_public_deploy_rejects_legacy_shared_secret_fallback() -> None:
    with pytest.raises(ValueError, match="explicit, distinct key material"):
        Settings(secret_key=_STRONG_KEY, **_PUBLIC_EXPOSURE)


def test_public_deploy_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="SESSION_SECRET_KEY"):
        Settings(**{**_PUBLIC, "session_secret_key": "too-short"})


def test_public_deploy_rejects_env_example_placeholder_secret() -> None:
    # The .env.example placeholder is 33 chars — long enough to pass the length
    # check — but publicly known, so an unedited copy must not boot exposed.
    with pytest.raises(ValueError, match="SESSION_SECRET_KEY"):
        Settings(
            **{
                **_PUBLIC,
                "session_secret_key": "change-me-to-a-long-random-string",
            }
        )


def test_public_deploy_accepts_distinct_explicit_keys() -> None:
    settings = Settings(**_PUBLIC)
    assert settings.is_local is False


def test_public_deploy_can_separate_session_and_encryption_keys() -> None:
    session_key = "s" * 32
    encryption_key = "e" * 32
    settings = Settings(
        secret_key="legacy-default-is-not-used",
        session_secret_key=session_key,
        encryption_key=encryption_key,
        **_PUBLIC_EXPOSURE,
    )

    assert settings.token_secrets == (session_key,)
    assert settings.encryption_keys == (encryption_key,)


def test_public_deploy_validates_previous_rotation_keys() -> None:
    with pytest.raises(ValueError, match="previous key"):
        Settings(
            session_secret_key=_STRONG_KEY,
            encryption_key="e" * 32,
            encryption_key_previous="too-short",
            **_PUBLIC_EXPOSURE,
        )


def test_public_deploy_rejects_overlapping_primary_key_domains() -> None:
    with pytest.raises(ValueError, match="fully distinct"):
        Settings(
            session_secret_key=_STRONG_KEY,
            encryption_key=_STRONG_KEY,
            **_PUBLIC_EXPOSURE,
        )


def test_public_deploy_rejects_overlap_in_rotation_rings() -> None:
    with pytest.raises(ValueError, match="fully distinct"):
        Settings(
            session_secret_key="s" * 32,
            session_secret_key_previous="shared-rotation-key-material-0123456789",
            encryption_key="e" * 32,
            encryption_key_previous="shared-rotation-key-material-0123456789",
            **_PUBLIC_EXPOSURE,
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://public.example.com",
        "https://user:password@public.example.com",
        "https://public.example.com/app",
        "https://public.example.com?tenant=1",
        "https://public.example.com/#fragment",
        "https://public.example.com:0",
        "https://0.0.0.0:8000",
    ],
)
def test_base_url_must_be_a_safe_application_origin(base_url: str) -> None:
    with pytest.raises(ValueError, match="DRIFTWATCH_BASE_URL"):
        Settings(**{**_PUBLIC, "base_url": base_url})


def test_origins_are_normalized_and_public_trusted_origins_require_https() -> None:
    settings = Settings(
        base_url="http://LOCALHOST:8000/",
        trusted_origins=["https://CONSOLE.example.com/", "http://admin.localhost:3000"],
    )

    assert settings.base_url == "http://localhost:8000"
    assert settings.trusted_origins == [
        "https://console.example.com",
        "http://admin.localhost:3000",
    ]

    with pytest.raises(ValueError, match="TRUSTED_ORIGINS"):
        Settings(trusted_origins=["http://console.example.com"])


def test_local_deploy_allows_weak_secret() -> None:
    # A loopback bind + loopback URL is a safe local install; the weak default is
    # permitted there so a dev box works without ceremony.
    settings = Settings(
        secret_key="dev-insecure-change-me", host="127.0.0.1", base_url="http://localhost:8000"
    )
    assert settings.is_local is True


def test_public_registration_is_closed_by_default() -> None:
    assert Settings().public_registration_enabled is False


def test_self_serve_billing_rejects_unverified_public_registration() -> None:
    with pytest.raises(ValueError, match="email ownership verification"):
        Settings(
            billing_provider="stripe",
            public_registration_enabled=True,
            billing_self_serve_enabled=True,
            billing_legal_gate_enabled=True,
            billing_terms_version="terms-1",
            billing_privacy_version="privacy-1",
            stripe_secret_key="sk_test_1234567890",
            stripe_webhook_secret="whsec_1234567890",
            stripe_api_version="2025-06-30.basil",
        )


def test_self_serve_billing_requires_versioned_legal_documents() -> None:
    with pytest.raises(ValueError, match="approved SHA-256 digests"):
        Settings(
            billing_provider="stripe",
            billing_self_serve_enabled=True,
            billing_legal_gate_enabled=True,
            billing_terms_version="terms-1",
            billing_privacy_version="privacy-1",
            stripe_secret_key="sk_test_1234567890",
            stripe_webhook_secret="whsec_1234567890",
            stripe_api_version="2025-06-30.basil",
        )


def test_self_serve_billing_is_ready_with_public_registration_closed() -> None:
    settings = Settings(
        billing_provider="stripe",
        public_registration_enabled=False,
        billing_self_serve_enabled=True,
        billing_legal_gate_enabled=True,
        billing_terms_version="terms-1",
        billing_privacy_version="privacy-1",
        billing_terms_url="https://legal.example.test/terms-1",
        billing_privacy_url="https://legal.example.test/privacy-1",
        billing_terms_sha256="a" * 64,
        billing_privacy_sha256="b" * 64,
        stripe_secret_key="sk_test_1234567890",
        stripe_webhook_secret="whsec_1234567890",
    )

    assert settings.billing_self_serve_ready is True
    assert settings.public_registration_enabled is False


def test_billing_legal_document_urls_must_use_https() -> None:
    with pytest.raises(ValueError, match="BILLING_TERMS_URL"):
        Settings(billing_terms_url="http://legal.example.test/terms")


def test_stripe_live_mode_rejects_test_key() -> None:
    with pytest.raises(ValueError, match="live secret"):
        Settings(
            billing_provider="stripe",
            stripe_secret_key="sk_test_1234567890",
            stripe_webhook_secret="whsec_1234567890",
            stripe_api_version="2025-06-30.basil",
            stripe_livemode=True,
        )


@pytest.mark.parametrize("api_key", ["rk_test_1234567890", "secret_1234567890"])
def test_stripe_test_mode_rejects_non_test_secret_key_prefix(api_key: str) -> None:
    with pytest.raises(ValueError, match="sk_test_"):
        Settings(
            billing_provider="stripe",
            stripe_secret_key=api_key,
            stripe_webhook_secret="whsec_1234567890",
        )


def test_stripe_rejects_non_webhook_secret_prefix() -> None:
    with pytest.raises(ValueError, match="whsec_"):
        Settings(
            billing_provider="stripe",
            stripe_secret_key="sk_test_1234567890",
            stripe_webhook_secret="secret_1234567890",
        )


def test_stripe_rejects_an_api_version_not_supported_by_this_release() -> None:
    with pytest.raises(ValueError, match="exactly match"):
        Settings(
            billing_provider="stripe",
            stripe_secret_key="sk_test_1234567890",
            stripe_webhook_secret="whsec_1234567890",
            stripe_api_version="2025-03-31.basil",
        )


def test_stripe_live_mode_pins_the_official_api_origin() -> None:
    with pytest.raises(ValueError, match="official"):
        Settings(
            billing_provider="stripe",
            stripe_secret_key="sk_live_1234567890",
            stripe_webhook_secret="whsec_1234567890",
            stripe_livemode=True,
            stripe_api_base_url="https://stripe-proxy.example.test",
        )

    configured = Settings(
        billing_provider="stripe",
        stripe_secret_key="sk_live_1234567890",
        stripe_webhook_secret="whsec_1234567890",
        stripe_livemode=True,
        stripe_api_base_url="https://API.STRIPE.COM/",
    )
    assert configured.stripe_api_base_url == "https://api.stripe.com"
