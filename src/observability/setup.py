"""Observability bootstrap — call once at server startup via setup_all()."""

from __future__ import annotations

import logging
import os


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logging.warning("SENTRY_DSN not set — error tracking disabled")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi   import FastApiIntegration
        from sentry_sdk.integrations.asyncio   import AsyncioIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging   import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            release=os.getenv("GIT_SHA", "unknown"),
            traces_sample_rate=0.1,
            profiles_sample_rate=0.05,
            send_default_pii=False,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                AsyncioIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,      # breadcrumb on WARNING
                    event_level=logging.ERROR,  # send event on ERROR
                ),
            ],
            before_send=_scrub_secrets,
        )
        logging.info("Sentry initialised (env=%s)", os.getenv("SENTRY_ENV", "production"))
    except Exception as e:
        logging.warning("Sentry init failed: %s", e)


def _scrub_secrets(event: dict, hint: object) -> dict | None:
    """Drop any event that accidentally contains credentials."""
    import json
    try:
        raw = json.dumps(event)
        if any(pat in raw for pat in ("sk-", "pk_live", "whsec_", "sk_live", "gsk_", "private_key")):
            return None
    except Exception:
        pass
    return event


def init_structlog() -> None:
    try:
        import structlog

        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]

        structlog.configure(
            processors=shared_processors + [structlog.processors.JSONRenderer()],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Route stdlib logging through structlog so everything is JSON
        logging.basicConfig(
            format="%(message)s",
            level=logging.INFO,
            handlers=[logging.StreamHandler()],
        )
        logging.info("structlog JSON logging initialised")
    except Exception as e:
        logging.warning("structlog init failed: %s", e)


def init_prometheus() -> dict:
    port_str = os.getenv("PROMETHEUS_PORT", "9090")
    try:
        from prometheus_client import Histogram, Gauge, start_http_server

        metrics = {
            "tick_duration": Histogram(
                "quantatrader_tick_duration_seconds",
                "Time to complete one trading tick",
                buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
            ),
            "llm_duration": Histogram(
                "quantatrader_llm_response_seconds",
                "LLM response time",
                ["provider"],
                buckets=[0.1, 0.5, 1, 2, 5, 15, 30],
            ),
            "order_duration": Histogram(
                "quantatrader_order_fill_seconds",
                "Order placement latency",
                ["venue"],
                buckets=[0.05, 0.1, 0.5, 1, 5],
            ),
            "ws_clients":    Gauge("quantatrader_websocket_clients", "Connected WebSocket clients"),
            "agent_running": Gauge("quantatrader_agent_running",     "1 if agent is running"),
            "errors_total":  Gauge("quantatrader_errors_total",      "Cumulative error count"),
        }

        port = int(port_str)
        if port > 0:
            start_http_server(port)
            logging.info("Prometheus metrics at http://0.0.0.0:%d/metrics", port)

        return metrics
    except Exception as e:
        logging.warning("Prometheus init failed: %s", e)
        return {}


def setup_all() -> dict:
    """Call once at application startup. Returns Prometheus metrics dict."""
    init_sentry()
    init_structlog()
    return init_prometheus()
