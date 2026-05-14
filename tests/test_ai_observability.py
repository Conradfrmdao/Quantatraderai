from __future__ import annotations

import pytest


def test_safe_error_payload_contains_trace_id_and_hides_internal_details():
    from src.ai.errors import AIError, AIErrorCode, safe_error_payload

    payload = safe_error_payload(
        AIError(
            AIErrorCode.AI_PROVIDER_FAILED,
            trace_id="trace-safe-1",
            metadata={"raw": "sk-secret-value"},
        )
    )

    assert payload["error"]["code"] == "AI_PROVIDER_FAILED"
    assert payload["error"]["trace_id"] == "trace-safe-1"
    assert "sk-secret-value" not in str(payload)
    assert "No trade was executed" in payload["error"]["message"]


def test_redaction_scrubs_secrets_from_text_and_payload():
    from src.ai.redaction import redact_payload, redact_text

    text = "Authorization: Bearer abc.def.ghi sk-secret gsk_hello AIzaExample 0x1234567890abcdef1234567890abcdef12345678"
    redacted = redact_text(text)
    assert "Bearer" not in redacted
    assert "sk-secret" not in redacted
    assert "gsk_" not in redacted
    assert "AIza" not in redacted

    payload = redact_payload({"apiKey": "sk-test", "nested": {"authorization": "Bearer token", "safe": "ok"}})
    assert payload["apiKey"] == "[REDACTED]"
    assert payload["nested"]["authorization"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "ok"


@pytest.mark.asyncio
async def test_capture_sentry_exception_attaches_safe_metadata(monkeypatch):
    captured: list[dict] = []

    class DummyScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def set_tag(self, key, value):
            captured.append({"tag": key, "value": value})

        def set_context(self, key, value):
            captured.append({"context": key, "value": value})

    class DummySentry:
        @staticmethod
        def push_scope():
            return DummyScope()

        @staticmethod
        def capture_exception(exc):
            captured.append({"exception": str(exc)})

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", DummySentry)

    from src.ai.telemetry import capture_sentry_exception

    capture_sentry_exception(RuntimeError("boom"), context={
        "user_id": "user-1",
        "trace_id": "trace-2",
        "provider": "groq",
        "secret": "sk-leak",
    })

    assert any(item.get("tag") == "user_id" for item in captured)
    assert any(item.get("tag") == "trace_id" for item in captured)
    assert "sk-leak" not in str(captured)
