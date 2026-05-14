"""Prompt and payload redaction helpers for AI governance."""

from __future__ import annotations

import json
import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{3,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{3,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{3,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b(?:x-internal-token|authorization|api[_-]?key|api[_-]?secret|private[_-]?key)\b\s*[:=]\s*['\"]?[^,'\"}\s]{6,}", re.IGNORECASE),
    re.compile(r"\b0x[a-fA-F0-9]{32,}\b"),
    re.compile(r"\b[a-fA-F0-9]{48,}\b"),
)

_SECRET_KEYS = {
    "apiKey",
    "apiSecret",
    "apiPassphrase",
    "metaApiToken",
    "privateKey",
    "secret",
    "token",
    "authorization",
    "x-internal-token",
}


def redact_text(text: str | None) -> str:
    value = str(text or "")
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def _redact_obj(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in _SECRET_KEYS:
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact_obj(item)
        return out
    if isinstance(value, list):
        return [_redact_obj(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_payload(value: Any) -> Any:
    return _redact_obj(value)


def redact_json(value: Any) -> str:
    try:
        return json.dumps(redact_payload(value), default=str)
    except Exception:
        return redact_text(str(value))
