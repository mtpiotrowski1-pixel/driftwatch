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

    _PREFIX = "dw1"

    def __init__(self, primary_key: str, *fallback_keys: str) -> None:
        keys = (primary_key, *fallback_keys)
        self._primary_id = _key_id(primary_key)
        self._fernets = {
            _key_id(key): Fernet(base64.urlsafe_b64encode(_digest(key))) for key in keys if key
        }
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
        if len(parts) == 3 and parts[0] == self._PREFIX:
            key_id, token = parts[1], parts[2]
            fernet = self._fernets.get(key_id)
            if fernet is None:
                return None
            plaintext = _decrypt_token(fernet, token)
            return (plaintext, key_id, True) if plaintext is not None else None

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
    return hashlib.sha256(secret_key.encode("utf-8")).hexdigest()[:16]


def _decrypt_token(fernet: Fernet, token: str) -> str | None:
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return None
