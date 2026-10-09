"""Tests for interaction-step parsing and capture retry behaviour."""

from __future__ import annotations

import asyncio

import pytest

from driftwatch.monitoring.capture import (
    CaptureBlocked,
    CaptureContentTooLarge,
    CaptureError,
    InteractionStep,
    PageCapturer,
    PlaywrightCapturer,
    _cap,
    capture_with_retry,
)


class FlakyCapturer:
    def __init__(self, *, failures_before_success: int, html: str = "<p>ok</p>") -> None:
        self._remaining_failures = failures_before_success
        self._html = html
        self.attempts = 0

    async def capture(self, *, url: str, css_selector: str | None = None, **_: object) -> str:
        self.attempts += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise CaptureError("transient")
        return self._html


def test_interaction_step_parsing_applies_defaults() -> None:
    step = InteractionStep.from_dict({"action": "click", "selector": "#more"})
    assert step.action == "click"
    assert step.selector == "#more"
    assert step.timeout_ms == 10_000


async def test_capture_with_retry_recovers_from_transient_failure() -> None:
    capturer: PageCapturer = FlakyCapturer(failures_before_success=1)
    html = await capture_with_retry(
        capturer, url="https://example.test", attempts=2, backoff_seconds=0
    )
    assert html == "<p>ok</p>"


async def test_capture_with_retry_gives_up_after_attempts() -> None:
    capturer = FlakyCapturer(failures_before_success=5)
    with pytest.raises(CaptureError):
        await capture_with_retry(
            capturer, url="https://example.test", attempts=2, backoff_seconds=0
        )
    assert capturer.attempts == 2


class _ConcurrencyProbe(PlaywrightCapturer):
    """Replaces the real browser run with a recorded sleep so the launch gate's
    effect on concurrency can be observed without launching Chromium."""

    def __init__(self, *, max_concurrent: int) -> None:
        super().__init__(pin_dns=False, max_concurrent=max_concurrent)
        self.active = 0
        self.peak = 0

    async def _run_capture(self, *_: object, **__: object) -> str:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.02)
            return "<p>ok</p>"
        finally:
            self.active -= 1


async def test_capture_caps_concurrent_browser_launches() -> None:
    probe = _ConcurrencyProbe(max_concurrent=3)
    await asyncio.gather(*(probe.capture(url="https://example.test") for _ in range(12)))
    assert probe.peak == 3


def test_capture_rejects_oversized_content_instead_of_silently_truncating() -> None:
    with pytest.raises(CaptureContentTooLarge) as failure:
        _cap("x" * 4_000_001)
    assert failure.value.transient is False


async def test_fill_origin_guard_checks_the_elements_owning_frame() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    handle = SimpleNamespace(
        owner_frame=AsyncMock(return_value=SimpleNamespace(url="https://other.example.test")),
        fill=AsyncMock(),
        dispose=AsyncMock(),
    )
    locator = SimpleNamespace(first=SimpleNamespace(element_handle=AsyncMock(return_value=handle)))
    page = SimpleNamespace(url="https://approved.example.test", locator=lambda _: locator)
    step = InteractionStep(
        action="fill", selector="#password", value="synthetic", allowed_origin=page.url
    )
    with pytest.raises(CaptureBlocked, match="unapproved origin"):
        await PlaywrightCapturer._replay(page, step)
    handle.fill.assert_not_awaited()
    handle.dispose.assert_awaited_once()
