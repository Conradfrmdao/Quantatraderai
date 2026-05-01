"""AES-256-GCM symmetric encryption for API keys stored in Supabase.

Generate a key once and set it in both .env (Python) and .env.local (Next.js):
    python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

Stored format: base64url(nonce[12] + ciphertext + tag[16])
The Node.js counterpart in ui/lib/encryption.ts uses the identical scheme so
keys encrypted by Next.js can be decrypted here and vice versa.
"""
from __future__ import annotations

import base64
import os
import secrets as _secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes:
    raw = os.getenv("ENCRYPTION_KEY", "")
    if not raw:
        raise RuntimeError(
            "ENCRYPTION_KEY env var is not set. "
            "Generate one with: python -c \"import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
        )
    padded = raw + "==" * (4 - len(raw) % 4 if len(raw) % 4 else 0)
    try:
        key = base64.urlsafe_b64decode(padded)
    except Exception as e:
        raise RuntimeError(f"ENCRYPTION_KEY is not valid base64url: {e}") from e
    if len(key) not in (16, 24, 32):
        raise RuntimeError(f"ENCRYPTION_KEY must decode to 16/24/32 bytes, got {len(key)}")
    return key


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext string → base64url-encoded ciphertext."""
    aesgcm = AESGCM(_key())
    nonce  = _secrets.token_bytes(12)
    ct     = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt base64url-encoded ciphertext → plaintext string."""
    aesgcm = AESGCM(_key())
    raw    = base64.urlsafe_b64decode(ciphertext + "==" * (4 - len(ciphertext) % 4 if len(ciphertext) % 4 else 0))
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
