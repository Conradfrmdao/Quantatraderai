"""Copy trading — mirror leader trades to follower accounts.

When a leader agent executes a trade, all registered followers automatically
place a proportionally scaled order on their own venue.

DB schema:
    CopyRelationship: leaderId (User), followerId (User), maxAllocPct, isActive

The mirror() function is called from server.py after every successful
leader order placement.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("quantatraderai.copy_trading")


async def get_followers(leader_user_id: str) -> list[dict[str, Any]]:
    """Return active follower records for a leader."""
    import os, asyncpg
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return []
    try:
        conn = await asyncpg.connect(db_url, timeout=5, statement_cache_size=0)
        try:
            rows = await conn.fetch(
                """
                SELECT cr.*, u."clerkId" AS follower_clerk_id
                FROM "CopyRelationship" cr
                JOIN "User" u ON u.id = cr."followerId"
                WHERE cr."leaderId"=$1 AND cr."isActive"=true
                """,
                leader_user_id,
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    except Exception as e:
        logger.warning("get_followers failed: %s", e)
        return []


async def mirror_trade(
    leader_user_id: str,
    symbol: str,
    action: str,
    leader_alloc_usd: float,
    leader_equity: float,
    sl_price: float | None = None,
    tp_price: float | None = None,
) -> list[dict[str, Any]]:
    """Mirror a leader trade to all active followers.

    Scales allocation as: follower_alloc = follower_equity * (leader_alloc_pct)
    capped at follower's maxAllocPct.

    Returns list of mirror results per follower.
    """
    if leader_equity <= 0:
        return []

    leader_alloc_pct = leader_alloc_usd / leader_equity
    followers = await get_followers(leader_user_id)
    results = []

    for f in followers:
        try:
            from src.services.supabase_reader import get_user_venues
            from src.venues.registry import get_venue

            follower_clerk_id = f.get("follower_clerk_id")
            max_alloc_pct     = float(f.get("maxAllocPct", 3.0)) / 100

            venues = await get_user_venues(follower_clerk_id)
            venue_row = venues[0] if venues else None
            if not venue_row:
                results.append({"follower": follower_clerk_id, "ok": False, "reason": "No venue configured"})
                continue

            follower_venue_name = venue_row.get("type", "binance").lower()
            venue = get_venue(follower_venue_name)
            balances = await venue.get_balances()
            balance  = next((b.available for b in balances if b.currency in ("USDT","USD","BUSD")), 0.0)

            alloc_pct = min(leader_alloc_pct, max_alloc_pct)
            alloc_usd = balance * alloc_pct

            if alloc_usd < 10:
                results.append({"follower": follower_clerk_id, "ok": False, "reason": "Alloc too small"})
                continue

            # B7: Map leader's symbol to follower's venue symbol (cross-asset support)
            from src.copy_trading.symbol_map import map_symbol, detect_asset_family
            mapped_symbol = map_symbol(symbol, follower_venue_name) or symbol
            family = detect_asset_family(symbol)

            try:
                ticker = await venue.get_ticker(mapped_symbol)
                price  = ticker.last or 0
            except Exception as ticker_err:
                results.append({
                    "follower": follower_clerk_id, "ok": False,
                    "reason": f"Symbol {mapped_symbol} not available on {follower_venue_name}: {ticker_err}",
                    "leader_symbol": symbol, "mapped_symbol": mapped_symbol,
                })
                continue

            if price <= 0:
                results.append({
                    "follower": follower_clerk_id, "ok": False,
                    "reason": f"No price for {mapped_symbol} on {follower_venue_name}",
                })
                continue

            # Run the follower's own RiskManager before placing — the follower's
            # account may already be over-exposed regardless of the leader's action.
            from src.risk_manager import RiskManager as _RM
            _follower_risk = _RM(venue=follower_venue_name)
            _follower_positions = await venue.get_positions()
            _follower_account_state = {
                "total_value": balance,
                "balance": balance,
                "positions": [p.__dict__ for p in _follower_positions],
                "min_order_usd": 10.0,
            }
            _trade_proposal = {
                "action": action,
                "allocation_usd": alloc_usd,
                "current_price": price,
                "sl_price": sl_price,
                "tp_price": tp_price,
            }
            _risk_ok, _risk_reason, _trade_proposal = _follower_risk.validate_trade(
                _trade_proposal, _follower_account_state, balance
            )
            if not _risk_ok:
                results.append({
                    "follower": follower_clerk_id, "ok": False,
                    "reason": f"Risk manager blocked copy trade: {_risk_reason}",
                })
                continue
            alloc_usd = float(_trade_proposal.get("allocation_usd", alloc_usd))

            qty = alloc_usd / price
            await venue.place_order(
                symbol=mapped_symbol, side=action, quantity=qty,
                order_type="market", stop_loss=sl_price, take_profit=tp_price,
            )
            logger.info(
                "COPY: leader=%s sym=%s → follower=%s venue=%s sym=%s qty=%s @ $%s family=%s",
                leader_user_id, symbol, follower_clerk_id, follower_venue_name, mapped_symbol, qty, price, family,
            )
            results.append({
                "follower": follower_clerk_id, "ok": True,
                "qty": qty, "price": price,
                "leader_symbol": symbol, "mapped_symbol": mapped_symbol,
                "venue": follower_venue_name,
            })

        except Exception as e:
            logger.warning("Mirror failed for follower %s: %s", f.get("follower_clerk_id"), e)
            results.append({"follower": f.get("follower_clerk_id"), "ok": False, "reason": str(e)})

    return results
