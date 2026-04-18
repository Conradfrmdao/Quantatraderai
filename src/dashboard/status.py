"""CLI: print current balances, positions, and active risk config.

Usage:
    poetry run python -m src.dashboard.status --venue hyperliquid
"""

from __future__ import annotations

import argparse
import asyncio
import json

from src.config_loader import CONFIG
from src.risk_manager import RiskManager
from src.venues.registry import get_venue


async def _show(venue_name: str) -> None:
    venue = get_venue(venue_name)
    balances = await venue.get_balances()
    positions = await venue.get_positions()
    risk = RiskManager(venue=venue_name.split(":")[0], asset_class=getattr(venue, "asset_class", None))

    print(f"=== QuntaTradeAI status — venue={venue_name} ===")
    print("\nBalances:")
    for b in balances:
        print(f"  {b.currency}: total={b.total:.4f} available={b.available:.4f}")

    print("\nPositions:")
    if not positions:
        print("  (none)")
    for p in positions:
        direction = "LONG" if p.quantity > 0 else "SHORT"
        print(
            f"  {p.symbol} {direction} qty={abs(p.quantity):.6f} "
            f"entry={p.entry_price:.4f} upnl={p.unrealized_pnl:+.2f}"
        )

    print("\nRisk config:")
    print(json.dumps(risk.get_risk_summary(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="QuntaTradeAI status CLI")
    parser.add_argument("--venue", default=CONFIG.get("venue") or "hyperliquid")
    args = parser.parse_args()
    asyncio.run(_show(args.venue))


if __name__ == "__main__":
    main()
