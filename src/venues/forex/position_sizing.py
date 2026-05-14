"""Forex sizing helpers.

The core platform still passes allocation as notional USD/account currency.
These helpers make the conversion explicit and testable for OANDA units and
MetaTrader lots.
"""

from __future__ import annotations


STANDARD_LOT_UNITS = 100_000.0


def notional_to_units(notional: float, price: float) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    return max(0.0, float(notional) / float(price))


def units_to_lots(units: float, lot_size: float = STANDARD_LOT_UNITS, min_lot: float = 0.01, step: float = 0.01) -> float:
    if lot_size <= 0 or step <= 0:
        raise ValueError("lot_size and step must be positive")
    lots = max(float(units) / float(lot_size), float(min_lot))
    return round(round(lots / step) * step, 2)


def notional_to_lots(notional: float, price: float, lot_size: float = STANDARD_LOT_UNITS) -> float:
    return units_to_lots(notional_to_units(notional, price), lot_size=lot_size)
