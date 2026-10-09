"""Classify a content diff as significant or not, with a short summary.

The pipeline depends on the :class:`ChangeAnalyzer` protocol, not on OpenAI, so
analysis can be faked in tests and the package imports without an API key. A
failed analysis raises :class:`AnalysisError`; callers treat that as a
retryable condition and must not send a notification on an uncertain verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from driftwatch.monitoring.analysis_input import prepare_input, user_message
from driftwatch.monitoring.usage import CostEstimate, TokenUsage, estimate_cost

_DEFAULT_TIMEOUT = 30.0


class AnalysisError(Exception):
    """The analyzer could not produce a verdict (no key, network, or parse)."""


@dataclass(frozen=True, slots=True)
class Analysis:
    significant: bool
    headline: str
    summary: str
    cost: CostEstimate


class ChangeAnalyzer(Protocol):
    async def analyze(
        self, *, diff_text: str, url: str, system_prompt: str, model: str
    ) -> Analysis: ...


class _Verdict(BaseModel):
    significant: bool = Field(description="True when the change matters to followers.")
    headline: str = Field(description="One-sentence headline, at most 100 characters.")
    summary: str = Field(description="Two or three sentences describing the change.")


def response_schema() -> dict[str, str]:
    """The fixed fields the model must return, name -> description. Exposed so the
    settings UI can show the structured contract that wraps user-written rules."""
    return {name: field.description or "" for name, field in _Verdict.model_fields.items()}


class OpenAIChangeAnalyzer:
    """Production analyzer backed by OpenAI structured outputs."""

    def __init__(
        self,
        api_key: str,
        *,
        max_diff_chars: int = 16_000,
        timeout: float = _DEFAULT_TIMEOUT,
        price_override: tuple[float, float] | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_diff_chars = max_diff_chars
        self._timeout = timeout
        self._price_override = price_override

    async def analyze(
        self, *, diff_text: str, url: str, system_prompt: str, model: str
    ) -> Analysis:
        if not self._api_key:
            raise AnalysisError("OpenAI API key is not configured")

        from openai import AsyncOpenAI, OpenAIError

        prepared = prepare_input(
            diff_text=diff_text,
            url=url,
            system_prompt=system_prompt,
            model=model,
            max_chars=self._max_diff_chars,
        )
        # ``async with`` closes the httpx connection pool deterministically rather
        # than leaving it to GC finalizers on a long-lived event loop.
        try:
            async with AsyncOpenAI(api_key=self._api_key, timeout=self._timeout) as client:
                completion = await client.chat.completions.parse(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message(url, prepared.diff_text)},
                    ],
                    response_format=_Verdict,
                )
        except OpenAIError as exc:
            # Provider bodies may repeat credentials or captured page text.
            # Persist a useful exception category without copying that body.
            raise AnalysisError(f"OpenAI request failed ({type(exc).__name__})") from exc

        verdict = completion.choices[0].message.parsed
        if verdict is None:
            raise AnalysisError("model returned no structured verdict")

        return Analysis(
            significant=verdict.significant,
            # Page-derived text: strip control chars so it can't carry CR/LF into
            # the email subject/headers or the rendered bodies.
            headline=_clean_line(verdict.headline)[:200],
            summary=verdict.summary,
            cost=estimate_cost(model, _usage_of(completion), price_override=self._price_override),
        )


def _clean_line(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ").strip()


def _usage_of(completion: object) -> TokenUsage:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return TokenUsage(reported=False)
    return TokenUsage(
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )
