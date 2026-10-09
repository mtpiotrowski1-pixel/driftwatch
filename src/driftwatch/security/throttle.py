"""In-memory failure throttle for the authentication endpoints.

Argon2 makes each password guess expensive but does not stop a determined
brute-force or password-spray. This caps repeated failures per client over a
sliding window. It is process-local and keyed per client address, so a single
source is slowed without letting an attacker lock another user's account; a
multi-instance deployment would back this with shared storage.

Memory is bounded: keys whose newest failure has aged out of the window can
never throttle again, so they are swept lazily, and a hard key cap evicts the
least-recently-active entries — otherwise a public instance hit by scanners
from many one-off IPs would leak one entry per IP forever.
"""

from __future__ import annotations

import asyncio
import time

# Sweep stale keys once the map grows past this; cheap amortized cleanup.
_SWEEP_THRESHOLD = 2_048
_MAX_KEYS = 100_000


class LoginThrottle:
    def __init__(self, *, max_failures: int = 10, window_seconds: float = 300.0) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def retry_after(self, key: str, *, max_failures: int | None = None) -> float | None:
        """Seconds the caller must wait if locked out, else ``None``. ``max_failures``
        overrides the default ceiling for this key (e.g. a softer per-account limit)."""
        limit = self._max if max_failures is None else max_failures
        async with self._lock:
            recent = self._prune(key)
            if len(recent) >= limit:
                return max(self._window - (time.monotonic() - recent[0]), 1.0)
            return None

    async def record_failure(self, key: str) -> None:
        async with self._lock:
            now = time.monotonic()
            self._failures.setdefault(key, []).append(now)
            if len(self._failures) > _SWEEP_THRESHOLD:
                self._sweep(now)

    async def consume(self, key: str, *, max_actions: int) -> float | None:
        """Atomically reserve one action in the sliding window.

        Authentication uses the explicit check/record/reset methods because only
        failures count. Administrative test actions count on every attempt, so
        they need a single locked operation that cannot be raced by concurrent
        requests. Returns a retry delay when the reservation is refused.
        """
        async with self._lock:
            recent = self._prune(key)
            if len(recent) >= max_actions:
                return max(self._window - (time.monotonic() - recent[0]), 1.0)
            now = time.monotonic()
            recent.append(now)
            self._failures[key] = recent
            if len(self._failures) > _SWEEP_THRESHOLD:
                self._sweep(now)
            return None

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._failures.pop(key, None)

    def _prune(self, key: str) -> list[float]:
        now = time.monotonic()
        recent = [stamp for stamp in self._failures.get(key, []) if now - stamp < self._window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def _sweep(self, now: float) -> None:
        # Drop keys whose most recent failure aged out of the window — they can
        # never reach the threshold again, so they are pure garbage.
        stale = [
            key
            for key, stamps in self._failures.items()
            if not stamps or now - stamps[-1] >= self._window
        ]
        for key in stale:
            del self._failures[key]
        # Belt-and-suspenders ceiling: if a burst of fresh keys still exceeds the
        # cap, evict the least-recently-active ones.
        overflow = len(self._failures) - _MAX_KEYS
        if overflow > 0:
            oldest = sorted(self._failures, key=lambda key: self._failures[key][-1])[:overflow]
            for key in oldest:
                del self._failures[key]
