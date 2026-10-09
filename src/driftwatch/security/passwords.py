"""Password hashing with Argon2id.

Argon2id is intentionally CPU- and memory-hard (tens of milliseconds per call),
so it must never run on the asyncio event loop — one hash would stall every other
in-flight request and the scheduler. Request handlers use the async wrappers,
which offload to a worker thread; the sync forms are for scripts and tests.
"""

from __future__ import annotations

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when a stored hash uses outdated parameters and should be upgraded."""
    return _hasher.check_needs_rehash(hashed)


async def ahash_password(plain: str) -> str:
    """Hash off the event loop."""
    return await asyncio.to_thread(hash_password, plain)


async def averify_password(plain: str, hashed: str) -> bool:
    """Verify off the event loop."""
    return await asyncio.to_thread(verify_password, plain, hashed)
