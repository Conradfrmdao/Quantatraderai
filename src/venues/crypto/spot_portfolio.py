"""Helpers for modeling spot-crypto holdings as position-like rows."""

from __future__ import annotations

from src.venues.models import Balance

PREFERRED_SPOT_QUOTES: tuple[str, ...] = (
    "USDT", "USDC", "USD", "BUSD", "FDUSD", "USDP", "TUSD", "DAI",
)
PREFERRED_BRIDGE_QUOTES: tuple[str, ...] = (
    "BTC", "ETH", "BNB", "SOL", "EUR", "GBP", "JPY",
)

CASH_EQUIVALENT_QUOTES = frozenset(PREFERRED_SPOT_QUOTES)
SPOT_BALANCE_CACHE_TTL_S = 2.0


def is_cash_equivalent(currency: str | None) -> bool:
    return str(currency or "").upper() in CASH_EQUIVALENT_QUOTES


def build_balances_from_ccxt_payload(balance_payload: dict) -> list[Balance]:
    out: list[Balance] = []
    totals = balance_payload.get("total") or {}
    free_map = balance_payload.get("free") or {}

    for currency, total in totals.items():
        amount = float(total or 0)
        if amount == 0:
            continue
        available = float(free_map.get(currency) or 0)
        out.append(Balance(currency=str(currency), total=amount, available=available))

    return out


def base_currency_from_symbol(symbol: str | None) -> str:
    raw = str(symbol or "").upper().split(":")[0]
    if "/" in raw:
        return raw.split("/", 1)[0]

    for quote in PREFERRED_SPOT_QUOTES:
        if raw.endswith(quote):
            return raw[: -len(quote)]

    return raw


def pick_best_spot_symbol(markets: dict, base_currency: str) -> str | None:
    base = str(base_currency or "").upper()
    if not base:
        return None

    best_symbol: str | None = None
    best_rank = len(PREFERRED_SPOT_QUOTES) + 1

    for market in (markets or {}).values():
        if not market or market.get("spot") is False:
            continue
        if market.get("active") is False:
            continue
        if str(market.get("base") or "").upper() != base:
            continue

        quote = str(market.get("quote") or "").upper()
        if quote not in CASH_EQUIVALENT_QUOTES:
            continue

        try:
            rank = PREFERRED_SPOT_QUOTES.index(quote)
        except ValueError:
            continue

        if rank < best_rank:
            best_rank = rank
            best_symbol = str(market.get("symbol") or "")

    return best_symbol


def spot_market_priority(quote_currency: str | None) -> int:
    quote = str(quote_currency or "").upper()
    if quote in CASH_EQUIVALENT_QUOTES:
        return PREFERRED_SPOT_QUOTES.index(quote)
    if quote in PREFERRED_BRIDGE_QUOTES:
        return len(PREFERRED_SPOT_QUOTES) + PREFERRED_BRIDGE_QUOTES.index(quote)
    return len(PREFERRED_SPOT_QUOTES) + len(PREFERRED_BRIDGE_QUOTES) + 100


def iter_spot_markets_for_base(markets: dict, base_currency: str) -> list[dict]:
    base = str(base_currency or "").upper()
    candidates = [
        market for market in (markets or {}).values()
        if market
        and market.get("spot") is not False
        and market.get("active") is not False
        and str(market.get("base") or "").upper() == base
    ]
    return sorted(
        candidates,
        key=lambda market: (spot_market_priority(market.get("quote")), str(market.get("symbol") or "")),
    )


def iter_spot_markets_for_quote(markets: dict, quote_currency: str) -> list[dict]:
    quote = str(quote_currency or "").upper()
    candidates = [
        market for market in (markets or {}).values()
        if market
        and market.get("spot") is not False
        and market.get("active") is not False
        and str(market.get("quote") or "").upper() == quote
    ]
    return sorted(
        candidates,
        key=lambda market: (spot_market_priority(market.get("base")), str(market.get("symbol") or "")),
    )
