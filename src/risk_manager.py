"""Centralized risk management for QuantatraderAI.

All safety guards are enforced here, independent of LLM decisions.
Limits are loaded from risk.yaml with per-(venue, asset_class) overrides;
env vars in .env are the outermost fallback.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import CONFIG
from src.venues.crypto.spot_portfolio import base_currency_from_symbol


class _ConfigProxy:
    """Dict-like proxy that maps server.py's risk_mgr.config['x'] pattern
    directly to RiskManager instance attributes so they stay in sync."""

    _KEYS = {
        "max_position_pct", "max_loss_per_position_pct", "max_leverage",
        "max_total_exposure_pct", "daily_loss_circuit_breaker_pct",
        "mandatory_sl_pct", "max_concurrent_positions", "min_balance_reserve_pct",
    }

    def __init__(self, rm: "RiskManager"):
        object.__setattr__(self, "_rm", rm)

    def get(self, key: str, default=None):
        return getattr(self._rm, key, default)

    def __getitem__(self, key: str):
        if key not in self._KEYS:
            raise KeyError(key)
        return getattr(self._rm, key)

    def __setitem__(self, key: str, value):
        if key in self._KEYS:
            existing = getattr(self._rm, key, value)
            setattr(self._rm, key, type(existing)(value))

    def update(self, d: dict):
        for k, v in d.items():
            self[k] = v

    def __contains__(self, key: str) -> bool:
        return key in self._KEYS

    def __bool__(self) -> bool:
        return True


def _load_yaml_config(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        import yaml
    except ImportError:
        logging.warning("pyyaml not installed; skipping risk.yaml at %s", path)
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        logging.warning("risk.yaml at %s is not a mapping; ignoring", path)
        return {}
    return data


def _resolve_limits(yaml_cfg: dict, venue: str | None, asset_class: str | None) -> dict:
    """Merge yaml default + matching override for (venue, asset_class).

    Matching order:
      1. Exact venue match  (e.g. override venue="binance" matches "binance")
      2. Prefix match        (e.g. override venue="binance" matches "binance:futures")
    First match wins.
    """
    merged = dict(yaml_cfg.get("default") or {})
    venue_norm = (venue or "").lower().split(":")[0]  # strip sub-type for matching
    for override in yaml_cfg.get("overrides") or []:
        if not isinstance(override, dict):
            continue
        ov = (override.get("venue") or "").lower()
        ac = override.get("asset_class")
        if ov == venue_norm and ac == asset_class:
            merged.update({k: v for k, v in override.items() if k not in {"venue", "asset_class"}})
            break
    return merged


class RiskManager:
    """Enforces risk limits on every trade before execution.

    venue/asset_class pick the override block in risk.yaml. Env vars in
    CONFIG are the fallback when neither risk.yaml nor an override provides
    a value.
    """

    def __init__(self, venue: str | None = None, asset_class: str | None = None):
        self.venue = venue or CONFIG.get("venue")
        self.asset_class = asset_class

        yaml_cfg = _load_yaml_config(CONFIG.get("risk_config_path") or "risk.yaml")
        yaml_limits = _resolve_limits(yaml_cfg, self.venue, self.asset_class)

        def _pick(key: str, env_key: str, cast, default):
            if key in yaml_limits:
                return cast(yaml_limits[key])
            env_val = CONFIG.get(env_key)
            if env_val is not None:
                return cast(env_val)
            return cast(default)

        self.max_position_pct = _pick("max_position_pct", "max_position_pct", float, 3)
        self.max_loss_per_position_pct = _pick(
            "max_loss_per_position_pct", "max_loss_per_position_pct", float, 8
        )
        self.max_leverage = _pick("max_leverage", "max_leverage", float, 2)
        self.max_total_exposure_pct = _pick(
            "max_total_exposure_pct", "max_total_exposure_pct", float, 20
        )
        self.daily_loss_circuit_breaker_pct = _pick(
            "daily_loss_circuit_breaker_pct", "daily_loss_circuit_breaker_pct", float, 4
        )
        self.mandatory_sl_pct = _pick("mandatory_sl_pct", "mandatory_sl_pct", float, 2.5)
        self.max_concurrent_positions = _pick(
            "max_concurrent_positions", "max_concurrent_positions", int, 5
        )
        self.min_balance_reserve_pct = _pick(
            "min_balance_reserve_pct", "min_balance_reserve_pct", float, 30
        )

        # Daily tracking
        self.daily_high_value = None
        self.daily_high_date = None
        self.circuit_breaker_active = False
        self.circuit_breaker_date = None

        self.config = _ConfigProxy(self)

        logging.info(
            "RISK: venue=%s asset_class=%s limits=pos<=%.1f%% lev<=%.1fx SL=%.2f%% DD=%.1f%%",
            self.venue, self.asset_class, self.max_position_pct,
            self.max_leverage, self.mandatory_sl_pct, self.daily_loss_circuit_breaker_pct,
        )

    def _reset_daily_if_needed(self, account_value: float):
        today = datetime.now(timezone.utc).date()
        if self.daily_high_date != today:
            self.daily_high_value = account_value
            self.daily_high_date = today
            self.circuit_breaker_active = False
            self.circuit_breaker_date = None
        elif account_value > self.daily_high_value:
            self.daily_high_value = account_value

    # ------------------------------------------------------------------
    # Individual checks — each returns (allowed: bool, reason: str)
    # ------------------------------------------------------------------

    def check_position_size(self, alloc_usd: float, account_value: float) -> tuple[bool, str]:
        if account_value <= 0:
            return False, "Account value is zero or negative"
        max_alloc = account_value * (self.max_position_pct / 100.0)
        if alloc_usd > max_alloc:
            return False, (
                f"Allocation ${alloc_usd:.2f} exceeds {self.max_position_pct}% "
                f"of account (${max_alloc:.2f})"
            )
        return True, ""

    def check_total_exposure(self, positions: list[dict], new_alloc: float,
                              account_value: float) -> tuple[bool, str]:
        current_exposure = 0.0
        for pos in positions:
            qty = abs(float(pos.get("quantity") or pos.get("szi") or 0))
            entry = float(pos.get("entry_price") or pos.get("entryPx") or 0)
            current_exposure += qty * entry
        total = current_exposure + new_alloc
        max_exposure = account_value * (self.max_total_exposure_pct / 100.0)
        if total > max_exposure:
            return False, (
                f"Total exposure ${total:.2f} would exceed {self.max_total_exposure_pct}% "
                f"of account (${max_exposure:.2f})"
            )
        return True, ""

    def check_leverage(self, alloc_usd: float, balance: float) -> tuple[bool, str]:
        if balance <= 0:
            return False, "Balance is zero or negative"
        effective_lev = alloc_usd / balance
        if effective_lev > self.max_leverage:
            return False, (
                f"Effective leverage {effective_lev:.1f}x exceeds max {self.max_leverage}x"
            )
        return True, ""

    def check_portfolio_leverage(
        self, positions: list[dict], new_alloc_usd: float, balance: float
    ) -> tuple[bool, str]:
        """Portfolio-level leverage: (total open notional + new alloc) / balance.

        Catches aggregate over-leverage that individual per-trade checks miss when
        many small trades pile up across positions.
        """
        if balance <= 0:
            return False, "Balance is zero or negative"
        existing_notional = 0.0
        for p in positions:
            qty   = abs(float(p.get("quantity") or p.get("szi") or 0))
            entry = float(p.get("entry_price") or p.get("entryPx") or 0)
            existing_notional += qty * entry
        total_notional = existing_notional + new_alloc_usd
        portfolio_lev  = total_notional / balance if balance > 0 else 0.0
        if portfolio_lev > self.max_leverage:
            return False, (
                f"Portfolio leverage {portfolio_lev:.1f}x "
                f"(existing ${existing_notional:.0f} + new ${new_alloc_usd:.0f} "
                f"on ${balance:.0f} balance) exceeds max {self.max_leverage}x"
            )
        return True, ""

    def check_daily_drawdown(self, account_value: float) -> tuple[bool, str]:
        self._reset_daily_if_needed(account_value)
        if self.circuit_breaker_active:
            return False, "Daily loss circuit breaker is active — no new trades until tomorrow (UTC)"
        if self.daily_high_value and self.daily_high_value > 0:
            drawdown_pct = ((self.daily_high_value - account_value) / self.daily_high_value) * 100
            if drawdown_pct >= self.daily_loss_circuit_breaker_pct:
                self.circuit_breaker_active = True
                self.circuit_breaker_date = datetime.now(timezone.utc).date()
                return False, (
                    f"Daily drawdown {drawdown_pct:.2f}% exceeds circuit breaker "
                    f"threshold of {self.daily_loss_circuit_breaker_pct}%"
                )
        return True, ""

    def check_concurrent_positions(self, current_count: int) -> tuple[bool, str]:
        if current_count >= self.max_concurrent_positions:
            return False, (
                f"Already at max concurrent positions ({self.max_concurrent_positions})"
            )
        return True, ""

    def check_balance_reserve(self, balance: float, initial_balance: float) -> tuple[bool, str]:
        if initial_balance <= 0:
            return True, ""
        min_balance = initial_balance * (self.min_balance_reserve_pct / 100.0)
        if balance < min_balance:
            return False, (
                f"Balance ${balance:.2f} below minimum reserve "
                f"${min_balance:.2f} ({self.min_balance_reserve_pct}% of initial)"
            )
        return True, ""

    # ------------------------------------------------------------------
    # Stop-loss enforcement
    # ------------------------------------------------------------------

    def enforce_stop_loss(self, sl_price: float | None, entry_price: float,
                           is_buy: bool) -> float:
        if sl_price is not None:
            return sl_price
        sl_distance = entry_price * (self.mandatory_sl_pct / 100.0)
        # Use 5 decimal places to preserve pip-level precision for FOREX
        # (safe for crypto too — no rounding artefacts at this precision)
        if is_buy:
            return round(entry_price - sl_distance, 5)
        else:
            return round(entry_price + sl_distance, 5)

    # ------------------------------------------------------------------
    # Force-close losing positions
    # ------------------------------------------------------------------

    def check_losing_positions(self, positions: list[dict]) -> list[dict]:
        to_close = []
        for pos in positions:
            coin = pos.get("coin") or pos.get("symbol")
            entry_px = float(pos.get("entryPx") or pos.get("entry_price") or 0)
            size = float(pos.get("szi") or pos.get("quantity") or 0)
            pnl = float(pos.get("pnl") or pos.get("unrealized_pnl") or 0)

            if entry_px == 0 or size == 0:
                continue

            notional = abs(size) * entry_px
            if notional == 0:
                continue

            loss_pct = abs(pnl / notional) * 100 if pnl < 0 else 0

            if loss_pct >= self.max_loss_per_position_pct:
                logging.warning(
                    "RISK: Force-closing %s — loss %.2f%% exceeds max %.2f%%",
                    coin, loss_pct, self.max_loss_per_position_pct
                )
                to_close.append({
                    "coin": coin,
                    "size": abs(size),
                    "is_long": size > 0,
                    "loss_pct": round(loss_pct, 2),
                    "pnl": round(pnl, 2),
                })
        return to_close

    def _spot_holding_value(self, positions: list[dict], symbol: str, fallback_price: float) -> float:
        target_base = base_currency_from_symbol(symbol)
        holding_value = 0.0
        for pos in positions:
            pos_symbol = str(pos.get("symbol") or pos.get("coin") or "")
            if base_currency_from_symbol(pos_symbol) != target_base:
                continue
            qty = abs(float(pos.get("quantity") or pos.get("szi") or 0))
            px = float(
                pos.get("current_price")
                or pos.get("mark_price")
                or fallback_price
                or pos.get("entry_price")
                or pos.get("entryPx")
                or 0
            )
            holding_value += qty * px
        return holding_value

    # ------------------------------------------------------------------
    # Composite validation — run all checks before a trade
    # ------------------------------------------------------------------

    def validate_trade(self, trade: dict, account_state: dict,
                        initial_balance: float) -> tuple[bool, str, dict]:
        action = trade.get("action", "hold")
        if action == "hold":
            return True, "", trade

        alloc_usd = float(trade.get("allocation_usd", 0))
        if alloc_usd <= 0:
            return False, "Zero or negative allocation", trade

        # Venue minimum order size (Hyperliquid is $10). Bump if below.
        min_order_usd = float(account_state.get("min_order_usd", 11.0))
        if alloc_usd < min_order_usd:
            alloc_usd = min_order_usd
            trade = {**trade, "allocation_usd": alloc_usd}
            logging.info("RISK: Bumped allocation to $%.2f (venue minimum)", min_order_usd)

        account_value = float(account_state.get("total_value", 0))
        balance = float(account_state.get("balance", 0))
        positions = account_state.get("positions", [])
        is_buy = action == "buy"
        is_spot_sell = self.asset_class == "crypto_spot" and action == "sell"

        if is_spot_sell:
            current_price = float(trade.get("current_price", 0))
            holding_value = self._spot_holding_value(
                positions,
                str(trade.get("asset") or trade.get("symbol") or ""),
                current_price,
            )
            if holding_value <= 0:
                return False, "No spot holding available to sell", trade
            if alloc_usd > holding_value:
                alloc_usd = holding_value
                trade = {**trade, "allocation_usd": alloc_usd}
            return True, "", trade

        ok, reason = self.check_daily_drawdown(account_value)
        if not ok:
            return False, reason, trade

        ok, reason = self.check_balance_reserve(balance, initial_balance)
        if not ok:
            return False, reason, trade

        ok, reason = self.check_position_size(alloc_usd, account_value)
        if not ok:
            max_alloc = account_value * (self.max_position_pct / 100.0)
            if max_alloc < min_order_usd:
                max_alloc = min_order_usd
            logging.warning("RISK: Capping allocation from $%.2f to $%.2f", alloc_usd, max_alloc)
            alloc_usd = max_alloc
            trade = {**trade, "allocation_usd": alloc_usd}

        ok, reason = self.check_total_exposure(positions, alloc_usd, account_value)
        if not ok:
            return False, reason, trade

        ok, reason = self.check_leverage(alloc_usd, balance)
        if not ok:
            return False, reason, trade

        ok, reason = self.check_portfolio_leverage(positions, alloc_usd, balance)
        if not ok:
            return False, reason, trade

        active_count = sum(
            1 for p in positions
            if abs(float(p.get("szi") or p.get("quantity") or 0)) > 0
        )
        ok, reason = self.check_concurrent_positions(active_count)
        if not ok:
            return False, reason, trade

        current_price = float(trade.get("current_price", 0))
        entry_price = current_price if current_price > 0 else 1.0
        sl_price = trade.get("sl_price")
        enforced_sl = self.enforce_stop_loss(sl_price, entry_price, is_buy)
        if sl_price is None:
            logging.info("RISK: Auto-setting SL at %.2f (%.1f%% from entry)",
                        enforced_sl, self.mandatory_sl_pct)
        trade = {**trade, "sl_price": enforced_sl}

        return True, "", trade

    def get_risk_summary(self) -> dict:
        return {
            "venue": self.venue,
            "asset_class": self.asset_class,
            "max_position_pct": self.max_position_pct,
            "max_loss_per_position_pct": self.max_loss_per_position_pct,
            "max_leverage": self.max_leverage,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "daily_loss_circuit_breaker_pct": self.daily_loss_circuit_breaker_pct,
            "mandatory_sl_pct": self.mandatory_sl_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "min_balance_reserve_pct": self.min_balance_reserve_pct,
            "circuit_breaker_active": self.circuit_breaker_active,
            "portfolio_leverage_check": True,
        }
