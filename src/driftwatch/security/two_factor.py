"""Time-based one-time passwords (RFC 6238) and recovery codes.

TOTP is implemented directly on the standard library rather than pulled from a
dependency: the algorithm is small, and owning it keeps verification explicitly
constant-time and the clock injectable for tests. Secrets are base32 strings as
authenticator apps expect; the caller stores them encrypted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_DIGITS = 6
_PERIOD_SECONDS = 30
# Unambiguous alphabet for recovery codes — no 0/O/1/l/i to avoid copy errors.
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_RECOVERY_COUNT = 10
_RECOVERY_GROUP = 5


def generate_secret(num_bytes: int = 20) -> str:
    """Return a fresh base32 TOTP secret (160 bits by default), unpadded."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def generate_code(secret: str, *, at: float | None = None) -> str:
    """Return the current 6-digit code for a secret (``at`` overrides the clock)."""
    counter = int((time.time() if at is None else at) // _PERIOD_SECONDS)
    return _hotp(secret, counter)


def verify(secret: str, code: str, *, at: float | None = None, window: int = 1) -> bool:
    """Check a 6-digit code against the secret, tolerating +/- ``window`` steps
    of clock drift. ``at`` overrides the current time for deterministic tests."""
    return matching_counter(secret, code, at=at, window=window) is not None


def matching_counter(
    secret: str, code: str, *, at: float | None = None, window: int = 1
) -> int | None:
    """Return the matched step so a caller can atomically prevent login replay."""
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != _DIGITS:
        return None
    counter = int((time.time() if at is None else at) // _PERIOD_SECONDS)
    for drift in (0, *range(-window, 0), *range(1, window + 1)):
        candidate = int(counter + drift)
        if candidate >= 0 and hmac.compare_digest(_hotp(secret, candidate), cleaned):
            return candidate
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    """Build the ``otpauth://`` URI an authenticator app scans or imports."""
    label = quote(f"{issuer}:{account}")
    query = (
        f"secret={secret}"
        f"&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={_DIGITS}&period={_PERIOD_SECONDS}"
    )
    return f"otpauth://totp/{label}?{query}"


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(_pad(secret.upper()))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**_DIGITS)).zfill(_DIGITS)


def _pad(secret: str) -> str:
    return secret + "=" * (-len(secret) % 8)


def generate_recovery_codes() -> list[str]:
    """Return single-use recovery codes in ``xxxxx-xxxxx`` form (shown once)."""
    return [f"{_group()}-{_group()}" for _ in range(_RECOVERY_COUNT)]


def hash_recovery_code(code: str) -> str:
    """Hash a recovery code for storage. Recovery codes are high-entropy, so a
    fast digest is sufficient (and keeps login cheap) — unlike user passwords."""
    return hashlib.sha256(_normalize_recovery_code(code).encode("utf-8")).hexdigest()


def _normalize_recovery_code(code: str) -> str:
    return code.strip().lower().replace(" ", "").replace("-", "")


def _group() -> str:
    return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_GROUP))
