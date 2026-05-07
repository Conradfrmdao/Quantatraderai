"""G22: Adaptive risk multiplier — auto-scales position size by rolling Sharpe.

When the agent's 30-day Sharpe is strong (>1.0), it earns the right to size up.
When Sharpe is weak (<0.5), it sizes down to protect capital.

Usage (called inside _tick after account data is available):
    from src.risk.adaptive import get_adaptive_position_pct
    pct = await get_adaptive_position_pct(user_id, default_pct=3.0)
    risk_mgr.config["max_position_pct"] = pct
"""
from __future__ import annotations

import logging
import os
import math

logger = logging.getLogger("quantatraderai.adaptive_risk")

_cache: dict[str, tuple[float, float]] = {}  # user_id → (pct, timestamp)
_CACHE_TTL = 300  # seconds


async def get_adaptive_position_pct(
    user_id: str | None,
    default_pct: float = 3.0,
    min_pct: float     = 0.5,
    max_pct: float     = 8.0,
    min_trades: int    = 20,
) -> float:
    """Compute an adaptive max_position_pct based on rolling Sharpe ratio.

    - Sharpe > 1.5  → scale up to max_pct (8%)
    - Sharpe 0.5–1.5 → linear scale between default and max
    - Sharpe < 0.5  → scale down to min_pct (0.5%)
    - < min_trades   → stay at default (not enough data)
    """
    import time
    if not user_id:
        return default_pct

    now = time.monotonic()
    if user_id in _cache:
        pct, ts = _cache[user_id]
        if now - ts < _CACHE_TTL:
            return pct

    try:
        import asyncpg
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            return default_pct

        conn = await asyncpg.connect(db_url, timeout=5)
        try:
            rows = await conn.fetch(
                """
                SELECT pnl FROM "TradeLog"
                WHERE "userId" = $1
                  AND "createdAt" > NOW() - INTERVAL '30 days'
                  AND action != 'close'
                ORDER BY "createdAt" DESC
                LIMIT 500
                """,
                user_id,
            )
        finally:
            await conn.close()

        pnl_list = [float(r["pnl"]) for r in rows if r["pnl"] != 0]
        if len(pnl_list) < min_trades:
            return default_pct

        # Compute Sharpe from trade PnL (simplified: no risk-free rate)
        n     = len(pnl_list)
        mean  = sum(pnl_list) / n
        var   = sum((x - mean) ** 2 for x in pnl_list) / n
        std   = math.sqrt(var) if var > 0 else 1.0
        sharpe = mean / std * math.sqrt(252) if std else 0.0  # annualised

        if sharpe >= 1.5:
            pct = max_pct
        elif sharpe >= 0.5:
            # Linear interpolation from default to max
            t   = (sharpe - 0.5) / 1.0
            pct = default_pct + t * (max_pct - default_pct)
        else:
            # Scale down proportionally
            t   = max(0.0, sharpe / 0.5)
            pct = min_pct + t * (default_pct - min_pct)

        pct = round(max(min_pct, min(max_pct, pct)), 2)
        _cache[user_id] = (pct, now)

        logger.info(
            "Adaptive risk | user=%s trades=%d sharpe=%.2f → max_position_pct=%.1f%%",
            user_id, n, sharpe, pct,
        )
        return pct

    except Exception as e:
        logger.warning("Adaptive risk calc failed: %s", e)
        return default_pct
