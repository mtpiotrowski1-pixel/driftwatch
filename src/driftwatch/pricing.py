"""Suggested-price algorithm for subscription plans.

A plan's monthly price should at least cover what its included usage costs the
platform, plus a margin. The cost that actually scales is AI analysis (OpenAI
tokens); monitored sites add a small flat amount. So:

    price = base_fee + per_site_fee * sites + cost_per_check * checks * margin

``cost_per_check`` is derived from the configured token prices and the real
average token use, and unlimited tiers are priced against notional caps so the
number stays finite. The operator tunes the knobs and may override the
suggestion per plan; this only proposes a sensible starting point.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from driftwatch.exceptions import InvalidRequest
from driftwatch.models import AIUsage
from driftwatch.monitoring.usage import configured_prices
from driftwatch.settings_store import SettingsStore

DEFAULT_BASE_FEE = Decimal("9")
DEFAULT_PER_SITE_FEE = Decimal("0.5")
DEFAULT_AI_MARGIN = Decimal("5")
DEFAULT_UNLIMITED_SITES = 100
DEFAULT_UNLIMITED_CHECKS = 20_000
DEFAULT_CURRENCY = "USD"
SUPPORTED_PRICING_CURRENCIES = frozenset({"USD", "EUR", "GBP", "PLN"})
DEFAULT_AVG_PROMPT_TOKENS = 1500
DEFAULT_AVG_COMPLETION_TOKENS = 200

# Knob settings live on the instance defaults layer; the operator edits them once.
PRICING_KEYS: frozenset[str] = frozenset(
    {
        "pricing_base_fee",
        "pricing_per_site_fee",
        "pricing_ai_margin",
        "pricing_unlimited_sites",
        "pricing_unlimited_checks",
        "pricing_currency",
    }
)

_CENT = Decimal("0.01")
_MILLION = Decimal(1_000_000)
# A sane ceiling so an absurd knob or cap can't produce a Decimal too large to
# round to cents (which would raise). Nothing real prices above a trillion.
_MAX_PRICE = Decimal(10) ** 12


@dataclass(frozen=True, slots=True)
class PricingInputs:
    base_fee: Decimal
    per_site_fee: Decimal
    cost_per_check: Decimal
    margin: Decimal
    unlimited_sites: int
    unlimited_checks: int
    currency: str
    # Surfaced so the operator can see what the algorithm assumed.
    avg_prompt_tokens: int
    avg_completion_tokens: int
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    model: str


def ai_cost_per_check(
    *,
    input_price_per_1m: Decimal,
    output_price_per_1m: Decimal,
    avg_prompt_tokens: int,
    avg_completion_tokens: int,
) -> Decimal:
    """Raw OpenAI cost of one analysis at the given token prices and average use."""
    return (
        Decimal(avg_prompt_tokens) / _MILLION * input_price_per_1m
        + Decimal(avg_completion_tokens) / _MILLION * output_price_per_1m
    )


def suggested_price(
    max_sites: int | None, monthly_ai_check_limit: int | None, inputs: PricingInputs
) -> Decimal:
    """Suggested monthly price for a tier with these caps, rounded to two places.
    ``None`` caps (unlimited) are priced against the configured notional caps."""
    sites = inputs.unlimited_sites if max_sites is None else max_sites
    checks = inputs.unlimited_checks if monthly_ai_check_limit is None else monthly_ai_check_limit
    price = (
        inputs.base_fee
        + Decimal(sites) * inputs.per_site_fee
        + Decimal(checks) * inputs.cost_per_check * inputs.margin
    )
    return min(price, _MAX_PRICE).quantize(_CENT, rounding=ROUND_HALF_UP)


def suggested_price_cents(
    max_sites: int | None, monthly_ai_check_limit: int | None, inputs: PricingInputs
) -> int:
    amount = suggested_price(max_sites, monthly_ai_check_limit, inputs)
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _decimal(raw: str | None, fallback: Decimal) -> Decimal:
    if not raw:
        return fallback
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return fallback
    # Reject NaN/Infinity (and negatives): a non-finite knob would otherwise blow
    # up the quantize/round downstream. The is_finite() check must come first so
    # the `>= 0` comparison never runs on a NaN (which would itself raise).
    return value if (value.is_finite() and value >= 0) else fallback


def _int(raw: str | None, fallback: int, *, minimum: int = 0) -> int:
    if raw is None or not raw.strip().isdigit():
        return fallback
    value = int(raw)
    return value if value >= minimum else fallback


async def _avg_tokens(session: AsyncSession) -> tuple[int, int]:
    """Average prompt/completion tokens across recorded AI calls, or the defaults
    when there is no history to learn from yet."""
    row = (
        await session.execute(
            select(func.avg(AIUsage.prompt_tokens), func.avg(AIUsage.completion_tokens))
        )
    ).one()
    prompt = int(row[0]) if row[0] is not None else DEFAULT_AVG_PROMPT_TOKENS
    completion = int(row[1]) if row[1] is not None else DEFAULT_AVG_COMPLETION_TOKENS
    return prompt, completion


async def _token_prices(store: SettingsStore) -> tuple[Decimal, Decimal, str]:
    """Effective (input, output) USD price per 1M tokens and the model name: the
    settings override if set, otherwise the configured model's listed price."""
    model = await store.get("openai_model") or "gpt-4o-mini"
    prices = configured_prices(
        model,
        await store.get("openai_price_input_per_1m"),
        await store.get("openai_price_output_per_1m"),
    )
    if prices is None:
        raise InvalidRequest("AI pricing is unknown; configure valid input and output token prices")
    return Decimal(str(prices[0])), Decimal(str(prices[1])), model


async def build_pricing_inputs(session: AsyncSession, store: SettingsStore) -> PricingInputs:
    """Gather everything the algorithm needs from settings and real usage."""
    input_price, output_price, model = await _token_prices(store)
    avg_prompt, avg_completion = await _avg_tokens(session)
    cost = ai_cost_per_check(
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
        avg_prompt_tokens=avg_prompt,
        avg_completion_tokens=avg_completion,
    )
    return PricingInputs(
        base_fee=_decimal(await store.get("pricing_base_fee"), DEFAULT_BASE_FEE),
        per_site_fee=_decimal(await store.get("pricing_per_site_fee"), DEFAULT_PER_SITE_FEE),
        cost_per_check=cost,
        margin=_decimal(await store.get("pricing_ai_margin"), DEFAULT_AI_MARGIN),
        unlimited_sites=_int(
            await store.get("pricing_unlimited_sites"), DEFAULT_UNLIMITED_SITES, minimum=1
        ),
        unlimited_checks=_int(
            await store.get("pricing_unlimited_checks"), DEFAULT_UNLIMITED_CHECKS, minimum=1
        ),
        currency=normalize_pricing_currency(await store.get("pricing_currency")),
        avg_prompt_tokens=avg_prompt,
        avg_completion_tokens=avg_completion,
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
        model=model,
    )


def normalize_pricing_currency(raw: str | None) -> str:
    currency = (raw or DEFAULT_CURRENCY).strip().upper()
    return currency if currency in SUPPORTED_PRICING_CURRENCIES else DEFAULT_CURRENCY
