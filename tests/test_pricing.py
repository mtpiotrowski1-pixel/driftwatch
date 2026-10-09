"""The suggested-price algorithm: cost-from-tokens and the price build-up."""

from __future__ import annotations

from decimal import Decimal

from driftwatch.pricing import (
    PricingInputs,
    _decimal,
    _int,
    ai_cost_per_check,
    normalize_pricing_currency,
    suggested_price,
    suggested_price_cents,
)


def _inputs(**overrides: object) -> PricingInputs:
    base: dict[str, object] = {
        "base_fee": Decimal("10"),
        "per_site_fee": Decimal("1"),
        "cost_per_check": Decimal("0.001"),
        "margin": Decimal("5"),
        "unlimited_sites": 100,
        "unlimited_checks": 20_000,
        "currency": "USD",
        "avg_prompt_tokens": 1500,
        "avg_completion_tokens": 200,
        "input_price_per_1m": Decimal("0.15"),
        "output_price_per_1m": Decimal("0.60"),
        "model": "gpt-4o-mini",
    }
    base.update(overrides)
    return PricingInputs(**base)  # type: ignore[arg-type]


def test_ai_cost_per_check_follows_the_token_math() -> None:
    cost = ai_cost_per_check(
        input_price_per_1m=Decimal("0.15"),
        output_price_per_1m=Decimal("0.60"),
        avg_prompt_tokens=1500,
        avg_completion_tokens=200,
    )
    # 1500/1e6 * 0.15 + 200/1e6 * 0.60
    assert cost == Decimal("0.000345")


def test_suggested_price_sums_base_sites_and_ai() -> None:
    inputs = _inputs(cost_per_check=Decimal("0.001"))
    # base 10 + 5 sites * 1 + 1000 checks * 0.001 * margin 5 = 10 + 5 + 5
    assert suggested_price(5, 1000, inputs) == Decimal("20.00")


def test_unlimited_caps_are_priced_against_notional_values() -> None:
    inputs = _inputs(
        base_fee=Decimal("0"),
        per_site_fee=Decimal("1"),
        cost_per_check=Decimal("0"),
        unlimited_sites=100,
    )
    assert suggested_price(None, None, inputs) == Decimal("100.00")


def test_a_bigger_margin_raises_the_price() -> None:
    cheap = suggested_price(10, 1000, _inputs(margin=Decimal("2")))
    pricey = suggested_price(10, 1000, _inputs(margin=Decimal("8")))
    assert pricey > cheap


def test_suggested_price_cents_rounds_to_minor_units() -> None:
    inputs = _inputs(
        base_fee=Decimal("9.99"), per_site_fee=Decimal("0"), cost_per_check=Decimal("0")
    )
    assert suggested_price_cents(0, 0, inputs) == 999


def test_pricing_currency_is_restricted_to_supported_two_decimal_units() -> None:
    assert normalize_pricing_currency("pln") == "PLN"
    assert normalize_pricing_currency("JPY") == "USD"


def test_suggested_price_is_clamped_for_absurd_inputs() -> None:
    inputs = _inputs(margin=Decimal("1e30"), cost_per_check=Decimal("1"))
    # Must not raise; the price is capped instead of overflowing the rounding.
    assert suggested_price(1000, 1000, inputs) == Decimal(10) ** 12


def test_decimal_knob_rejects_non_finite_and_negative() -> None:
    fallback = Decimal("5")
    assert _decimal("3.5", fallback) == Decimal("3.5")
    assert _decimal("inf", fallback) == fallback
    assert _decimal("NaN", fallback) == fallback
    assert _decimal("-1", fallback) == fallback
    assert _decimal("", fallback) == fallback
    assert _decimal("nonsense", fallback) == fallback


def test_int_knob_honours_a_minimum() -> None:
    assert _int("5", 100, minimum=1) == 5
    assert _int("0", 100, minimum=1) == 100  # below the floor falls back
    assert _int("0", 100) == 0  # no floor by default
