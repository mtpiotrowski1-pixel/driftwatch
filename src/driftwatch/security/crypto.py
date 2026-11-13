"""Symmetric encryption for secret settings (OpenAI key, SMTP password).

Secrets are encrypted before they touch the database. New ciphertext carries a
non-secret key id; a bounded fallback ring decrypts older values, which callers
opportunistically rewrite with the primary key during a controlled rotation.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    """Encrypt with one primary key and decrypt with a bounded rotation ring."""

    _PREFIX = "dw2"
    # A dw1 key id was the first eight bytes of the Fernet signing key. Those
    # ciphertexts stay readable and are rewritten as dw2 on rotation.
    _LEGACY_PREFIX = "dw1"

    def __init__(self, primary_key: str, *fallback_keys: str) -> None:
        keys = [key for key in (primary_key, *fallback_keys) if key]
        self._primary_id = _key_id(primary_key)
        self._fernets = {
            _key_id(key): Fernet(base64.urlsafe_b64encode(_digest(key))) for key in keys
        }
        self._legacy_ids = {_legacy_key_id(key): _key_id(key) for key in keys}
        if self._primary_id not in self._fernets:
            raise ValueError("A primary encryption key is required")

    def encrypt(self, plaintext: str) -> str:
        token = self._fernets[self._primary_id].encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{self._PREFIX}:{self._primary_id}:{token}"

    def decrypt(self, ciphertext: str) -> str | None:
        """Return the plaintext, or ``None`` if the ciphertext is unreadable."""
        result = self._decrypt(ciphertext)
        return result[0] if result is not None else None

    def rotate(self, ciphertext: str) -> str | None:
        """Return ciphertext under the primary key, or ``None`` if unreadable."""
        result = self._decrypt(ciphertext)
        if result is None:
            return None
        plaintext, key_id, versioned = result
        if versioned and key_id == self._primary_id:
            return ciphertext
        return self.encrypt(plaintext)

    def _decrypt(self, ciphertext: str) -> tuple[str, str, bool] | None:
        parts = ciphertext.split(":", 2)
        if len(parts) == 3 and parts[0] in (self._PREFIX, self._LEGACY_PREFIX):
            prefix, key_id, token = parts
            if prefix == self._LEGACY_PREFIX:
                key_id = self._legacy_ids.get(key_id, "")
            fernet = self._fernets.get(key_id)
            if fernet is None:
                return None
            plaintext = _decrypt_token(fernet, token)
            current = prefix == self._PREFIX
            return (plaintext, key_id, current) if plaintext is not None else None

        # Pre-versioning ciphertexts have no key id. Try the configured ring and
        # let callers persist ``rotate``'s result opportunistically.
        for key_id, fernet in self._fernets.items():
            plaintext = _decrypt_token(fernet, ciphertext)
            if plaintext is not None:
                return plaintext, key_id, False
        return None


def _digest(secret_key: str) -> bytes:
    return hashlib.sha256(secret_key.encode("utf-8")).digest()


def _key_id(secret_key: str) -> str:
    # Hashed with a label, so the id shares no bytes with the derived key.
    labelled = b"driftwatch secret box key id:" + secret_key.encode("utf-8")
    return hashlib.sha256(labelled).hexdigest()[:16]


def _legacy_key_id(secret_key: str) -> str:
    return _digest(secret_key).hex()[:16]


def _decrypt_token(fernet: Fernet, token: str) -> str | None:
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return None
