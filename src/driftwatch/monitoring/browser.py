"""Pick a Chromium-family browser to drive, regardless of its version.

Playwright speaks the DevTools protocol straight to the browser process, so —
unlike Selenium with ``msedgedriver`` — there is no separately-versioned driver
to keep in sync. We can launch the operator's *installed* Edge or Chrome
(``channel="msedge"`` / ``"chrome"``) at whatever version it happens to be, and
fall back to Playwright's bundled Chromium when neither is present. Detection
probes by actually launching each candidate and keeping the first that works.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class BrowserChannel(StrEnum):
    AUTO = "auto"
    MSEDGE = "msedge"
    CHROME = "chrome"
    CHROMIUM = "chromium"  # Playwright's bundled build — no system browser needed


class BrowserUnavailable(RuntimeError):
    """No Edge, Chrome, or bundled Chromium could be launched."""


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    channel: BrowserChannel
    launch_kwargs: dict[str, Any] = field(default_factory=dict)


def parse_channel(value: str | None) -> BrowserChannel:
    try:
        return BrowserChannel(value) if value else BrowserChannel.AUTO
    except ValueError:
        return BrowserChannel.AUTO


def detection_order(forced: BrowserChannel) -> list[BrowserChannel]:
    if forced is not BrowserChannel.AUTO:
        return [forced]
    return [BrowserChannel.MSEDGE, BrowserChannel.CHROME, BrowserChannel.CHROMIUM]


def _launch_kwargs(channel: BrowserChannel) -> dict[str, Any]:
    return {} if channel is BrowserChannel.CHROMIUM else {"channel": channel.value}


async def resolve_launch_plan(
    playwright: Any, *, forced: BrowserChannel = BrowserChannel.AUTO, headless: bool
) -> LaunchPlan:
    """Return the first launchable browser, probing in detection order."""
    from playwright.async_api import Error as PlaywrightError

    last_error: Exception | None = None
    for channel in detection_order(forced):
        kwargs = _launch_kwargs(channel)
        try:
            browser = await playwright.chromium.launch(headless=headless, **kwargs)
        except PlaywrightError as exc:
            last_error = exc
            logger.debug("browser channel %s unavailable: %s", channel, exc)
            continue
        # Guard the probe close so a teardown error can't orphan the process.
        try:
            await browser.close()
        except PlaywrightError as exc:
            logger.debug("probe close for channel %s failed: %s", channel, exc)
        logger.info("using browser channel: %s", channel)
        return LaunchPlan(channel=channel, launch_kwargs=kwargs)

    raise BrowserUnavailable(
        "Could not launch Microsoft Edge, Google Chrome, or bundled Chromium. "
        "Install Edge or Chrome, or run `playwright install chromium`."
    ) from last_error
