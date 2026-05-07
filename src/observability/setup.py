"""Observability bootstrap — call once at server startup.

Wires:
  1. Sentry (error tracking + performance) — requires SENTRY_DSN env var
  2. structlog (structured JSON logging) — always enabled
  3. Prometheus metrics — exposed at GET /metrics
     - tick_duration_seconds (histogram)
     - llm_response_seconds (histogram, label: provider)
     - order_fill_seconds (histogram, label: venue)
     - websocket_clients (gauge)
     - agent_running (gauge)

Set env vars:
    SENTRY_DSN      — from sentry.io project settings
    SENTRY_ENV      — "production" | "staging" | "development"
    PROMETHEUS_PORT — port to expose /metrics (default: 9090, set 0 to disable)
"""

from __future__ import annotations

import logging
import os
import time


# ── Sentry ────────────────────────────────────────────────────────────────────

def init_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENV", "production"),
            integrations=[FastApiIntegration(), AsyncioIntegration()],
            traces_sample_rate=0.1,   # 10% of transactions
            profiles_sample_rate=0.05,
            send_default_pii=False,
        )
        logging.info("Sentry initialised (env=%s)", os.getenv("SENTRY_ENV", "production"))
    except Exception as e:
        logging.warning("Sentry init failed: %s", e)


# ── structlog ─────────────────────────────────────────────────────────────────

def init_structlog():
    try:
        import structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        logging.info("structlog JSON logging initialised")
    except Exception as e:
        logging.warning("structlog init failed: %s", e)


# ── Prometheus metrics ────────────────────────────────────────────────────────

_metrics_initialised = False

def get_metrics():
    """Return metric objects, initialising them on first call."""
    global _metrics_initialised
    try:
        from prometheus_client import Histogram, Gauge, Counter
        tick_duration = Histogram(
            "quantatrader_tick_duration_seconds",
            "Time to complete one trading tick",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )
        llm_duration = Histogram(
            "quantatrader_llm_response_seconds",
            "LLM response time",
            ["provider"],
            buckets=[0.1, 0.5, 1, 2, 5, 15, 30],
        )
        order_duration = Histogram(
            "quantatrader_order_fill_seconds",
            "Order placement latency",
            ["venue"],
            buckets=[0.05, 0.1, 0.5, 1, 5],
        )
        ws_clients = Gauge("quantatrader_websocket_clients", "Connected WebSocket clients")
        agent_running = Gauge("quantatrader_agent_running", "1 if agent is running")
        _metrics_initialised = True
        return {
            "tick_duration":  tick_duration,
            "llm_duration":   llm_duration,
            "order_duration": order_duration,
            "ws_clients":     ws_clients,
            "agent_running":  agent_running,
        }
    except Exception as e:
        logging.warning("Prometheus metrics init failed: %s", e)
        return {}


def setup_all():
    """Call once at application startup."""
    init_sentry()
    init_structlog()
    metrics = get_metrics()

    # Start Prometheus HTTP server on a separate port
    port_str = os.getenv("PROMETHEUS_PORT", "9090")
    try:
        port = int(port_str)
        if port > 0:
            from prometheus_client import start_http_server
            start_http_server(port)
            logging.info("Prometheus metrics at http://0.0.0.0:%d/metrics", port)
    except Exception as e:
        logging.warning("Prometheus HTTP server failed: %s", e)

    return metrics
