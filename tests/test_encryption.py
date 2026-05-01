"""Unit tests — AES-256-GCM encryption service.

Covers: round-trip, tamper detection, empty-key error, key-length variants.
"""
import os
import base64
import pytest


def test_encrypt_decrypt_roundtrip(mock_env):
    from src.services.encryption import encrypt, decrypt
    plaintext = "super-secret-binance-api-key-abc123"
    ct = encrypt(plaintext)
    assert ct != plaintext
    assert decrypt(ct) == plaintext


def test_ciphertext_is_different_each_call(mock_env):
    from src.services.encryption import encrypt
    ct1 = encrypt("same-value")
    ct2 = encrypt("same-value")
    # Nonce is random so every call produces different ciphertext
    assert ct1 != ct2


def test_ciphertext_tamper_detected(mock_env):
    from src.services.encryption import encrypt, decrypt
    from cryptography.exceptions import InvalidTag
    ct = encrypt("my-api-key")
    # Corrupt one byte in the ciphertext section
    raw = base64.urlsafe_b64decode(ct + "==")
    bad = bytearray(raw)
    bad[15] ^= 0xFF
    bad_ct = base64.urlsafe_b64encode(bytes(bad)).decode().rstrip("=")
    with pytest.raises((InvalidTag, Exception)):
        decrypt(bad_ct)


def test_missing_encryption_key_raises(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    import importlib
    import src.services.encryption as enc_mod
    importlib.reload(enc_mod)          # reload to clear cached _key()
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        enc_mod.encrypt("x")
    # Restore: reloaded module will pick up env on next call; but next test uses mock_env


def test_32_byte_key_accepted(monkeypatch):
    key = base64.urlsafe_b64encode(b"a" * 32).decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    import importlib
    import src.services.encryption as enc_mod
    importlib.reload(enc_mod)
    ct = enc_mod.encrypt("hello")
    assert enc_mod.decrypt(ct) == "hello"


def test_long_plaintext(mock_env):
    from src.services.encryption import encrypt, decrypt
    plaintext = "x" * 4096
    assert decrypt(encrypt(plaintext)) == plaintext


def test_unicode_plaintext(mock_env):
    from src.services.encryption import encrypt, decrypt
    plaintext = "私のAPIキー🔑"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_empty_string_plaintext(mock_env):
    from src.services.encryption import encrypt, decrypt
    assert decrypt(encrypt("")) == ""


def test_secrets_never_appear_in_repr(mock_env):
    from src.services.encryption import encrypt
    secret = "ULTRA_SECRET_DO_NOT_LOG"
    ct = encrypt(secret)
    assert secret not in ct
    assert secret not in repr(ct)
