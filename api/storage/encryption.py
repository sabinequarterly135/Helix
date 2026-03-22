"""Fernet symmetric encryption for API key storage.

Uses HELIX_SECRET_KEY env var as the encryption key. If not set,
auto-generates a key and appends it to .env on first use.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class KeyEncryptor:
    """Encrypt and decrypt API keys using Fernet symmetric encryption.

    Derives a valid 32-byte Fernet key from an arbitrary-length secret
    via SHA-256 hashing, so user-provided secrets of any length work.
    """

    def __init__(self, secret_key: str | None = None):
        """Initialize with explicit key or from HELIX_SECRET_KEY env var.

        If neither is available, auto-generates a key and saves to .env.
        """
        secret = secret_key or os.environ.get("HELIX_SECRET_KEY")

        if not secret:
            secret = self._generate_and_save_key()

        # Derive a valid 32-byte Fernet key from the secret via SHA-256
        derived = hashlib.sha256(secret.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(derived)
        self._fernet = Fernet(fernet_key)

    @staticmethod
    def _generate_and_save_key() -> str:
        """Generate a new Fernet key and persist it to .env."""
        raw_key = Fernet.generate_key().decode()
        logger.info("Auto-generating HELIX_SECRET_KEY and saving to .env")

        env_path = Path(".env")
        # Append to existing .env or create a new one
        with env_path.open("a", encoding="utf-8") as f:
            f.write(f"\nHELIX_SECRET_KEY={raw_key}\n")

        os.environ["HELIX_SECRET_KEY"] = raw_key
        return raw_key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string, returning a base64-encoded ciphertext.

        Returns empty string for empty/None input.
        """
        if not plaintext:
            return ""
        token = self._fernet.encrypt(plaintext.encode())
        return token.decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet ciphertext, returning the original plaintext.

        Returns empty string for empty/None input. Gracefully degrades
        (returns empty string with a warning) if the key has changed.
        """
        if not ciphertext:
            return ""
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode())
            return plaintext.decode()
        except InvalidToken:
            logger.warning("Failed to decrypt value (key may have changed), returning empty string")
            return ""

    def is_encrypted(self, value: str) -> bool:
        """Check if a value looks like a Fernet token.

        Fernet tokens always start with 'gAAAAA' (base64 encoding of version byte + timestamp).
        """
        if not value:
            return False
        return value.startswith("gAAAAA")


# Module-level singleton for convenience
_encryptor: KeyEncryptor | None = None


def get_encryptor() -> KeyEncryptor:
    """Return a module-level KeyEncryptor singleton."""
    global _encryptor
    if _encryptor is None:
        _encryptor = KeyEncryptor()
    return _encryptor
