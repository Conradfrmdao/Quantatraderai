"""Shared structured logger — import this everywhere instead of `logging`."""

from __future__ import annotations
import logging
import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def capture(exc: Exception, **ctx: object) -> None:
    """Report an exception to Sentry with extra context, non-blocking."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in ctx.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass
    log.error("exception", exc_info=exc, **ctx)


def set_sentry_user(user_id: str, email: str | None = None) -> None:
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": user_id, "email": email})
    except Exception:
        pass


def add_breadcrumb(message: str, category: str = "app", **data: object) -> None:
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(message=message, category=category, data=data)
    except Exception:
        pass
