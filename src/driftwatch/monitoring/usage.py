"""Estimate the cost of an OpenAI call from its token usage.

This is a local operational counter, not a billing source of truth. Prices are
per million tokens (USD) and can be overridden per model through settings when
they change.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

# Standard uncached text prices, USD/1M tokens; checked against each official
# model page on 2026-10-08. This estimate excludes cache discounts and provider
# retries. Unknown model names deliberately have no price.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
}


def listed_price(model: str) -> tuple[float, float] | None:
    """Known (input, output) USD/1M tokens, or an explicitly unknown price."""
    return _PRICING.get(model)


def configured_prices(
    model: str, input_raw: str | None, output_raw: str | None
) -> tuple[float, float] | None:
    """Resolve operator overrides, retaining known catalog sides if omitted.

    An unknown model needs both prices. Invalid or nonfinite settings do not
    silently create a zero-cost estimate.
    """
    listed = listed_price(model)
    values: list[float] = []
    for index, raw in enumerate((input_raw, output_raw)):
        if raw is None or not raw.strip():
            if listed is None:
                return None
            value = listed[index]
        else:
            try:
                value = float(raw)
            except ValueError:
                return None
            if not isfinite(value) or value < 0:
                return None
        values.append(value)
    return values[0], values[1]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reported: bool = True

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class CostEstimate:
    model: str
    usage: TokenUsage
    cost_usd: float | None
    pricing_source: str = "catalog"


def estimate_cost(
    model: str,
    usage: TokenUsage,
    *,
    price_override: tuple[float, float] | None = None,
) -> CostEstimate:
    if not usage.reported:
        return CostEstimate(model, usage, None, "missing_usage")
    prices = price_override if price_override is not None else listed_price(model)
    if prices is None:
        return CostEstimate(model=model, usage=usage, cost_usd=None, pricing_source="unknown")
    if any(not isfinite(value) or value < 0 for value in prices):
        raise ValueError("Token prices must be finite and nonnegative")
    input_per_1m, output_per_1m = prices
    cost = (
        usage.prompt_tokens * input_per_1m + usage.completion_tokens * output_per_1m
    ) / 1_000_000
    return CostEstimate(
        model=model,
        usage=usage,
        cost_usd=round(cost, 6),
        pricing_source="override" if price_override is not None else "catalog",
    )
