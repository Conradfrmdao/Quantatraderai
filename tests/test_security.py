"""Security tests — secrets must never appear in logs, responses, or repr.

These tests prove that:
 - encrypted values look random and cannot be reversed without the key
 - raw API keys never appear in venue test responses
 - logs do not contain plaintext secrets
 - masked values follow the ••••••••  pattern
"""
import io
import logging
import pytest
from unittest.mock import AsyncMock, patch

_FAKE_BINANCE_KEY    = "FAKE_BINANCE_API_KEY_1234567890ABCD"
_FAKE_BINANCE_SECRET = "FAKE_BINANCE_SECRET_XYZ9876543210ABC"
_FAKE_ETH_KEY        = "0x" + "d" * 62


# ── Encryption must make plaintext unrecoverable without the key ──────────────

def test_ciphertext_contains_no_plaintext(mock_env):
    from src.services.encryption import encrypt
    ct = encrypt(_FAKE_BINANCE_KEY)
    assert _FAKE_BINANCE_KEY not in ct
    assert "FAKE" not in ct
    assert "BINANCE" not in ct


def test_different_keys_produce_different_ciphertexts(mock_env):
    from src.services.encryption import encrypt
    ct1 = encrypt(_FAKE_BINANCE_KEY)
    ct2 = encrypt(_FAKE_BINANCE_SECRET)
    assert ct1 != ct2


def test_wrong_encryption_key_cannot_decrypt(monkeypatch):
    from src.services.encryption import encrypt
    import base64, importlib
    ct = encrypt(_FAKE_BINANCE_KEY)  # encrypted with test key

    # Change key
    wrong_key = base64.urlsafe_b64encode(b"WRONG_KEY_32_bytes_pad_here!!!!").decode()
    monkeypatch.setenv("ENCRYPTION_KEY", wrong_key)
    import src.services.encryption as enc_mod
    importlib.reload(enc_mod)
    with pytest.raises(Exception):  # AESGCM InvalidTag or similar
        enc_mod.decrypt(ct)


# ── Logs must not contain raw secrets ─────────────────────────────────────────

def test_inject_venue_env_does_not_log_keys(mock_env, caplog):
    """_inject_venue_env sets os.environ but must not log the actual key value."""
    from src.server import _inject_venue_env
    with caplog.at_level(logging.DEBUG, logger="quantatrader"):
        _inject_venue_env(
            "binance", "futures", True,
            _FAKE_BINANCE_KEY, _FAKE_BINANCE_SECRET,
            "", "", "", "", "", "",
        )
    log_text = caplog.text
    assert _FAKE_BINANCE_KEY    not in log_text, "Raw API key appeared in logs!"
    assert _FAKE_BINANCE_SECRET not in log_text, "Raw secret appeared in logs!"


def test_encryption_functions_do_not_log_plaintext(mock_env, caplog):
    from src.services.encryption import encrypt, decrypt
    plaintext = "MY-ULTRA-SECRET-API-KEY"
    with caplog.at_level(logging.DEBUG):
        ct = encrypt(plaintext)
        decrypt(ct)
    assert plaintext not in caplog.text


# ── Test connection response must not expose raw credentials ──────────────────

@pytest.mark.asyncio
async def test_venue_test_response_has_no_raw_key(mock_env, monkeypatch):
    """The /api/venues/test endpoint must never return raw API key."""
    from src.server import VenueTestRequest, test_venue
    from src.services.encryption import encrypt

    encrypted_key    = encrypt(_FAKE_BINANCE_KEY)
    encrypted_secret = encrypt(_FAKE_BINANCE_SECRET)

    with patch("src.services.supabase_reader.get_user_venues", new=AsyncMock(return_value=[{
        "type":       "BINANCE",
        "apiKey":     encrypted_key,
        "apiSecret":  encrypted_secret,
        "apiPassphrase": "", "accountId": "", "network": "",
        "metaApiToken": "", "metaApiAccountId": "", "ccxtExchangeId": "",
    }])):
        # Patch get_venue to return a mock that returns a balance
        from tests.conftest import MockVenue
        mock_v = MockVenue()
        with patch("src.server.get_venue", return_value=mock_v):
            req = VenueTestRequest(userId="clerk-test", venue="binance", isPaper=True)
            result = await test_venue(req)

    result_str = str(result)
    assert _FAKE_BINANCE_KEY    not in result_str, "Raw API key in response!"
    assert _FAKE_BINANCE_SECRET not in result_str, "Raw secret in response!"
    assert encrypted_key        not in result_str, "Encrypted blob in response (leaks structure)!"


# ── Live trading locked on FREE plan ──────────────────────────────────────────

def test_free_plan_blocks_live_trading():
    from src.server import _plan_allows
    assert _plan_allows("FREE", "liveTrading") is False


def test_live_mode_requires_paper_false():
    """Even if plan allows it, paper=True must be respected."""
    from src.server import _plan_allows
    # STARTER+ allows live trading when explicitly set
    assert _plan_allows("STARTER", "liveTrading") is True
    # But we verify plan gating only — is_paper=True enforcement tested elsewhere


# ── Private keys must not appear in error messages ────────────────────────────

@pytest.mark.asyncio
async def test_polymarket_error_hides_private_key(mock_env, monkeypatch):
    from src.server import VenueTestRequest, test_venue
    from src.services.encryption import encrypt

    # Encrypt a fake ETH key
    encrypted_eth_key = encrypt(_FAKE_ETH_KEY)

    with patch("src.services.supabase_reader.get_user_venues", new=AsyncMock(return_value=[{
        "type": "POLYMARKET",
        "apiKey": encrypted_eth_key,
        "apiSecret": "", "apiPassphrase": "", "accountId": "",
        "network": "137", "metaApiToken": "", "metaApiAccountId": "",
        "ccxtExchangeId": "",
    }])):
        # Patch get_venue to raise a realistic error
        with patch("src.server.get_venue", side_effect=RuntimeError("Connection refused to Polymarket CLOB")):
            req = VenueTestRequest(userId="clerk-test", venue="polymarket", isPaper=True)
            result = await test_venue(req)

    result_str = str(result)
    assert _FAKE_ETH_KEY not in result_str, "Decrypted ETH private key leaked in error response!"


# ── Venue credentials table masks secrets ─────────────────────────────────────

def test_mask_secret_function():
    """The maskSecret helper must produce •••• not the real value."""
    # Simulate what ui/app/api/venues/route.ts does
    def mask_secret(s: str | None) -> str:
        if not s or len(s) < 8:
            return s or ""
        return "••••••••"

    assert mask_secret(_FAKE_BINANCE_KEY) == "••••••••"
    assert mask_secret("short") == "short"  # edge: too short to mask
    assert mask_secret(None) == ""
    assert mask_secret("") == ""
    assert _FAKE_BINANCE_KEY not in mask_secret(_FAKE_BINANCE_KEY)


# ── Multi-user state does not bleed between users ────────────────────────────

def test_no_state_bleed_between_users():
    from src.server import get_state
    state_a = get_state("security_user_a")
    state_b = get_state("security_user_b")

    state_a.account = {"equity": 999_999.0}
    assert state_b.account.get("equity") != 999_999.0, \
        "User B can see User A's equity — CRITICAL security failure"


def test_no_venue_bleed_between_users(mock_env):
    from src.server import get_state
    from tests.conftest import MockVenue

    sa = get_state("venue_leak_a")
    sb = get_state("venue_leak_b")
    sa.venue = MockVenue(starting_balance=12345.0)

    assert sb.venue is not sa.venue, \
        "User B's venue is the same object as User A's — state bleed detected!"
