"""Safe AI observability helpers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import aiohttp

from src.ai.redaction import redact_payload

logger = logging.getLogger("quantatraderai.ai.telemetry")


async def capture_posthog(event: str, properties: dict[str, Any]) -> None:
    token = os.getenv("NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN", "").strip()
    host = (os.getenv("NEXT_PUBLIC_POSTHOG_HOST") or "https://us.i.posthog.com").rstrip("/")
    if not token:
        return
    payload = {
        "api_key": token,
        "event": event,
        "properties": redact_payload(properties),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{host}/capture/",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=4),
            ) as resp:
                await resp.read()
                if resp.status >= 400:
                    logger.debug("posthog capture skipped status=%s", resp.status)
    except Exception as exc:
        logger.debug("posthog capture failed: %s", exc)


def capture_sentry_exception(exc: Exception, *, context: dict[str, Any] | None = None) -> None:
    try:
        import sentry_sdk

        safe_context = redact_payload(context or {})
        with sentry_sdk.push_scope() as scope:
            for key, value in safe_context.items():
                if value is None:
                    continue
                if key in {"user_id", "trace_id", "venue", "provider", "model", "action", "mode", "plan"}:
                    scope.set_tag(key, str(value))
                else:
                    scope.set_context("ai", safe_context)
            sentry_sdk.capture_exception(exc)
    except Exception as sentry_exc:
        logger.debug("sentry capture skipped: %s", sentry_exc)


def ai_structured_log(level: str, message: str, **fields: Any) -> None:
    payload = redact_payload(fields)
    payload["message"] = message
    getattr(logger, level, logger.info)(json.dumps(payload, default=str))
