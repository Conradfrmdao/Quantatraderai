"""Entry-point script that wires together the trading agent, data feeds, and API."""

import sys
import argparse
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))
from src.agent.decision_maker import TradingAgent
from src.indicators.local_indicators import compute_all, last_n, latest
from src.risk_manager import RiskManager
from src.venues.registry import get_venue
from src.venues.crypto.hyperliquid import HyperliquidVenue as _HLVenue
import asyncio
import logging
from collections import deque, OrderedDict
from datetime import datetime, timezone
import math  # For Sharpe
from dotenv import load_dotenv
import os
import json
from aiohttp import web
from src.utils.formatting import format_number as fmt, format_size as fmt_sz
from src.utils.prompt_utils import json_default, round_or_none, round_series

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Resolve the project root regardless of working directory so log files always
# land in the same place whether launched via CLI, Docker, or IDE.
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_LOG_DIR = pathlib.Path(os.environ.get("LOG_DIR", str(_PROJECT_ROOT / "logs")))
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def clear_terminal():
    """Clear the terminal screen on Windows or POSIX systems."""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_interval_seconds(interval_str):
    """Convert interval strings like '5m' or '1h' to seconds."""
    if interval_str.endswith('m'):
        return int(interval_str[:-1]) * 60
    elif interval_str.endswith('h'):
        return int(interval_str[:-1]) * 3600
    elif interval_str.endswith('d'):
        return int(interval_str[:-1]) * 86400
    else:
        raise ValueError(f"Unsupported interval: {interval_str}")

def main():
    """Parse CLI args, bootstrap dependencies, and launch the trading loop."""
    clear_terminal()
    parser = argparse.ArgumentParser(
        prog="quantatrader",
        description="QuantatraderAI — Claude-powered multi-venue AI trading agent.",
    )
    parser.add_argument("--venue", type=str, default=None,
                        help="hyperliquid (default) | ccxt[:<exchange>] | oanda. "
                             "Currently this main loop uses the Hyperliquid path; other venues "
                             "are exercised via src/backtesting/engine.py and src/dashboard/status.py.")
    parser.add_argument("--assets", type=str, nargs="+", required=False, help="Assets to trade, e.g., BTC ETH")
    parser.add_argument("--interval", type=str, required=False, help="Interval period, e.g., 1h")
    args = parser.parse_args()

    # Allow assets/interval via .env (CONFIG) if CLI not provided
    from src.config_loader import CONFIG
    assets_env = CONFIG.get("assets")
    interval_env = CONFIG.get("interval")
    if (not args.assets or len(args.assets) == 0) and assets_env:
        # Support space or comma separated
        if "," in assets_env:
            args.assets = [a.strip() for a in assets_env.split(",") if a.strip()]
        else:
            args.assets = [a.strip() for a in assets_env.split(" ") if a.strip()]
    if not args.interval and interval_env:
        args.interval = interval_env

    if not args.assets or not args.interval:
        parser.error("Please provide --assets and --interval, or set ASSETS and INTERVAL in .env")

    venue_name = (args.venue or CONFIG.get("venue") or "hyperliquid").lower()
    venue = get_venue(venue_name)
    # _hl_api: HyperliquidAPI handle for HL-specific features (OI, funding, fills,
    # TP/SL trigger orders, open orders).  None for non-Hyperliquid venues.
    _hl_api = venue.api if isinstance(venue, _HLVenue) else None
    # Legacy alias so HL-specific code blocks below stay readable
    hyperliquid = _hl_api

    agent   = TradingAgent(hyperliquid=_hl_api)
    risk_mgr = RiskManager(
        venue=venue_name.split(":")[0],
        asset_class=venue.asset_class,
    )
    print(f"Venue: {venue.name}  asset_class: {venue.asset_class}")


    start_time = datetime.now(timezone.utc)
    invocation_count = 0
    trade_log = []  # For Sharpe: list of returns
    active_trades = []  # {'asset','is_long','amount','entry_price','tp_oid','sl_oid','exit_plan'}
    recent_events = deque(maxlen=200)
    diary_path      = str(_LOG_DIR / "diary.jsonl")
    decisions_path  = str(_LOG_DIR / "decisions.jsonl")
    prompts_path    = str(_LOG_DIR / "prompts.log")
    initial_account_value = None
    # Perp mid-price history sampled each loop (authoritative, avoids spot/perp basis mismatch)
    price_history = {}

    print(f"Starting trading agent for assets: {args.assets} at interval: {args.interval}")

    def add_event(msg: str):
        """Log an informational event and push it into the recent events deque."""
        logging.info(msg)

    async def run_loop():
        """Main trading loop that gathers data, calls the agent, and executes trades."""
        nonlocal invocation_count, initial_account_value

        # Pre-load Hyperliquid meta cache for correct order sizing (HL-only)
        if _hl_api:
            await _hl_api.get_meta_and_ctxs()
            hip3_dexes = {a.split(":")[0] for a in args.assets if ":" in a}
            for dex in hip3_dexes:
                await _hl_api.get_meta_and_ctxs(dex=dex)
                add_event(f"Loaded HIP-3 meta for dex: {dex}")

        while True:
            invocation_count += 1
            minutes_since_start = (datetime.now(timezone.utc) - start_time).total_seconds() / 60

            # Global account state — use Venue abstraction (works for all venues)
            _balances  = await venue.get_balances()
            _positions = await venue.get_positions()
            balance = next(
                (b.available for b in _balances if b.currency in ("USDC","USDT","USD","BUSD")),
                sum(b.total for b in _balances) if _balances else 0.0,
            )
            pnl_total  = sum(p.unrealized_pnl for p in _positions)
            total_value = balance + pnl_total

            # Build a normalized state dict that RiskManager.validate_trade expects
            state = {
                "total_value": total_value,
                "balance": balance,
                "positions": [
                    {
                        "symbol":        p.symbol,
                        "quantity":      p.quantity,
                        "entry_price":   p.entry_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "leverage":      p.leverage,
                    }
                    for p in _positions
                ],
                "min_order_usd": 11.0,
            }

            sharpe = calculate_sharpe(trade_log)
            account_value = total_value
            if initial_account_value is None:
                initial_account_value = account_value
            total_return_pct = ((account_value - initial_account_value) / initial_account_value * 100.0) if initial_account_value else 0.0

            positions = []
            for p in _positions:
                try:
                    ticker   = await venue.get_ticker(p.symbol)
                    current_px = ticker.last
                except Exception:
                    current_px = p.entry_price
                positions.append({
                    "symbol":            p.symbol,
                    "quantity":          round_or_none(p.quantity, 6),
                    "entry_price":       round_or_none(p.entry_price, 2),
                    "current_price":     round_or_none(current_px, 2),
                    "liquidation_price": round_or_none(p.liquidation_price, 2),
                    "unrealized_pnl":    round_or_none(p.unrealized_pnl, 4),
                    "leverage":          p.leverage,
                })

            # --- RISK: Force-close positions that exceed max loss ---
            try:
                positions_to_close = risk_mgr.check_losing_positions(state["positions"])
                for ptc in positions_to_close:
                    coin = ptc["coin"]
                    size = ptc["size"]
                    add_event(f"RISK FORCE-CLOSE: {coin} at {ptc['loss_pct']}% loss (PnL: ${ptc['pnl']})")
                    try:
                        await venue.close_position(coin, size)
                        for tr in active_trades[:]:
                            if tr.get("asset") == coin:
                                active_trades.remove(tr)
                        with open(diary_path, "a") as f:
                            f.write(json.dumps({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "asset": coin,
                                "action": "risk_force_close",
                                "loss_pct": ptc["loss_pct"],
                                "pnl": ptc["pnl"],
                            }) + "\n")
                    except Exception as fc_err:
                        add_event(f"Force-close error for {coin}: {fc_err}")
            except Exception as risk_err:
                add_event(f"Risk check error: {risk_err}")

            recent_diary = []
            try:
                with open(diary_path, "r") as f:
                    lines = f.readlines()
                    for line in lines[-10:]:
                        entry = json.loads(line)
                        recent_diary.append(entry)
            except Exception:
                pass

            # Open orders — Hyperliquid only (other venues expose this differently)
            open_orders_struct = []
            open_orders: list = []
            if _hl_api:
                try:
                    open_orders = await _hl_api.get_open_orders()
                    for o in open_orders[:50]:
                        open_orders_struct.append({
                            "coin": o.get("coin"),
                            "oid": o.get("oid"),
                            "is_buy": o.get("isBuy"),
                            "size": round_or_none(o.get("sz"), 6),
                            "price": round_or_none(o.get("px"), 2),
                            "trigger_price": round_or_none(o.get("triggerPx"), 2),
                            "order_type": o.get("orderType"),
                        })
                except Exception:
                    open_orders = []

            # Reconcile active trades against live positions
            try:
                assets_with_positions = {
                    p["symbol"] for p in state["positions"]
                    if abs(float(p.get("quantity") or 0)) > 0
                }
                assets_with_orders = {o.get("coin") for o in open_orders if o.get("coin")}
                for tr in active_trades[:]:
                    asset = tr.get("asset")
                    if asset not in assets_with_positions and asset not in assets_with_orders:
                        add_event(f"Reconciling stale active trade for {asset} (no position, no orders)")
                        active_trades.remove(tr)
                        with open(diary_path, "a") as f:
                            f.write(json.dumps({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "asset": asset,
                                "action": "reconcile_close",
                                "reason": "no_position_no_orders",
                                "opened_at": tr.get("opened_at"),
                            }) + "\n")
            except Exception:
                pass

            # Recent fills — Hyperliquid only
            recent_fills_struct = []
            if _hl_api:
                try:
                    fills = await _hl_api.get_recent_fills(limit=50)
                    for f_entry in fills[-20:]:
                        try:
                            t_raw = f_entry.get("time") or f_entry.get("timestamp")
                            timestamp = None
                            if t_raw is not None:
                                try:
                                    t_int = int(t_raw)
                                    timestamp = datetime.fromtimestamp(
                                        t_int / 1000 if t_int > 1e12 else t_int,
                                        tz=timezone.utc,
                                    ).isoformat()
                                except Exception:
                                    timestamp = str(t_raw)
                            recent_fills_struct.append({
                                "timestamp": timestamp,
                                "coin": f_entry.get("coin") or f_entry.get("asset"),
                                "is_buy": f_entry.get("isBuy"),
                                "size": round_or_none(f_entry.get("sz") or f_entry.get("size"), 6),
                                "price": round_or_none(f_entry.get("px") or f_entry.get("price"), 2),
                            })
                        except Exception:
                            continue
                except Exception:
                    pass

            dashboard = {
                "total_return_pct": round(total_return_pct, 2),
                "balance": round_or_none(state['balance'], 2),
                "account_value": round_or_none(account_value, 2),
                "sharpe_ratio": round_or_none(sharpe, 3),
                "positions": positions,
                "active_trades": [
                    {
                        "asset": tr.get('asset'),
                        "is_long": tr.get('is_long'),
                        "amount": round_or_none(tr.get('amount'), 6),
                        "entry_price": round_or_none(tr.get('entry_price'), 2),
                        "tp_oid": tr.get('tp_oid'),
                        "sl_oid": tr.get('sl_oid'),
                        "exit_plan": tr.get('exit_plan'),
                        "opened_at": tr.get('opened_at')
                    }
                    for tr in active_trades
                ],
                "open_orders": open_orders_struct,
                "recent_diary": recent_diary,
                "recent_fills": recent_fills_struct,
            }

            def _candles_to_dicts(candles) -> list[dict]:
                """Convert Venue Candle objects OR raw HL dicts to compute_all format."""
                result = []
                for c in (candles or []):
                    if hasattr(c, "close"):
                        result.append({"open": c.open, "high": c.high, "low": c.low,
                                       "close": c.close, "volume": c.volume})
                    elif isinstance(c, dict):
                        # Raw HL dicts use single-letter keys (o/h/l/c/v)
                        result.append({
                            "open":   float(c.get("open") or c.get("o") or 0),
                            "high":   float(c.get("high") or c.get("h") or 0),
                            "low":    float(c.get("low")  or c.get("l") or 0),
                            "close":  float(c.get("close") or c.get("c") or 0),
                            "volume": float(c.get("volume") or c.get("v") or 0),
                        })
                return result

            # Gather data for ALL assets using Venue abstraction
            market_sections = []
            asset_prices = {}
            for asset in args.assets:
                try:
                    ticker = await venue.get_ticker(asset)
                    current_price = ticker.last or 0.0
                    asset_prices[asset] = current_price
                    if asset not in price_history:
                        price_history[asset] = deque(maxlen=60)
                    price_history[asset].append({"t": datetime.now(timezone.utc).isoformat(), "mid": round_or_none(current_price, 2)})

                    # OI + funding: Hyperliquid only
                    oi = funding = None
                    if _hl_api:
                        try:
                            oi      = await _hl_api.get_open_interest(asset)
                            funding = await _hl_api.get_funding_rate(asset)
                        except Exception:
                            pass

                    # Candles via Venue interface (works for all venues)
                    candles_5m = _candles_to_dicts(await venue.get_candles(asset, "5m", 100))
                    candles_4h = _candles_to_dicts(await venue.get_candles(asset, "4h", 100))

                    intra = compute_all(candles_5m)
                    lt    = compute_all(candles_4h)

                    recent_mids = [entry["mid"] for entry in list(price_history.get(asset, []))[-10:]]
                    funding_annualized = round(funding * 24 * 365 * 100, 2) if funding else None

                    market_sections.append({
                        "asset": asset,
                        "current_price": round_or_none(current_price, 2),
                        "intraday": {
                            "ema20": round_or_none(latest(intra.get("ema20", [])), 2),
                            "macd": round_or_none(latest(intra.get("macd", [])), 2),
                            "rsi7": round_or_none(latest(intra.get("rsi7", [])), 2),
                            "rsi14": round_or_none(latest(intra.get("rsi14", [])), 2),
                            "series": {
                                "ema20": round_series(last_n(intra.get("ema20", []), 10), 2),
                                "macd": round_series(last_n(intra.get("macd", []), 10), 2),
                                "rsi7": round_series(last_n(intra.get("rsi7", []), 10), 2),
                                "rsi14": round_series(last_n(intra.get("rsi14", []), 10), 2),
                            }
                        },
                        "long_term": {
                            "ema20": round_or_none(latest(lt.get("ema20", [])), 2),
                            "ema50": round_or_none(latest(lt.get("ema50", [])), 2),
                            "atr3": round_or_none(latest(lt.get("atr3", [])), 2),
                            "atr14": round_or_none(latest(lt.get("atr14", [])), 2),
                            "macd_series": round_series(last_n(lt.get("macd", []), 10), 2),
                            "rsi_series": round_series(last_n(lt.get("rsi14", []), 10), 2),
                        },
                        "open_interest": round_or_none(oi, 2),
                        "funding_rate": round_or_none(funding, 8),
                        "funding_annualized_pct": funding_annualized,
                        "recent_mid_prices": recent_mids,
                    })
                except Exception as e:
                    add_event(f"Data gather error {asset}: {e}")
                    continue

            # Fetch macro sentiment (Fear & Greed + news) — enriches NEWS_REACTOR persona
            # and gives all strategies a macro bias signal.  Failures are non-fatal.
            macro_sentiment: dict = {}
            try:
                from src.intel.sentiment import get_fear_greed
                fng = await get_fear_greed()
                macro_sentiment["crypto_fear_greed"] = fng
            except Exception as _sent_err:
                add_event(f"Sentiment fetch error: {_sent_err}")

            try:
                from src.intel.news import get_news_sentiment
                # Aggregate news for the first asset as a general market signal
                _primary_asset = args.assets[0] if args.assets else "BTC"
                news_data = await get_news_sentiment(_primary_asset, limit=5)
                macro_sentiment["news_sentiment"] = news_data
            except Exception as _news_err:
                pass  # news is optional; don't log every failed call

            # Single LLM call with all assets
            context_payload = OrderedDict([
                ("invocation", {
                    "minutes_since_start": round(minutes_since_start, 2),
                    "current_time": datetime.now(timezone.utc).isoformat(),
                    "invocation_count": invocation_count
                }),
                ("account", dashboard),
                ("risk_limits", risk_mgr.get_risk_summary()),
                ("macro_sentiment", macro_sentiment),
                ("market_data", market_sections),
                ("instructions", {
                    "assets": args.assets,
                    "requirement": "Decide actions for all assets and return a strict JSON object matching the schema."
                })
            ])
            context = json.dumps(context_payload, default=json_default)
            add_event(f"Combined prompt length: {len(context)} chars for {len(args.assets)} assets")
            with open(prompts_path, "a") as f:
                f.write(f"\n\n--- {datetime.now()} - ALL ASSETS ---\n{json.dumps(context_payload, indent=2, default=json_default)}\n")

            def _is_failed_outputs(outs):
                """Return True when outputs are missing or clearly invalid."""
                if not isinstance(outs, dict):
                    return True
                decisions = outs.get("trade_decisions")
                if not isinstance(decisions, list) or not decisions:
                    return True
                try:
                    return all(
                        isinstance(o, dict)
                        and (o.get('action') == 'hold')
                        and ('parse error' in (o.get('rationale', '').lower()))
                        for o in decisions
                    )
                except Exception:
                    return True

            try:
                outputs = agent.decide_trade(args.assets, context)
                if not isinstance(outputs, dict):
                    add_event(f"Invalid output format (expected dict): {outputs}")
                    outputs = {}
            except Exception as e:
                import traceback
                add_event(f"Agent error: {e}")
                add_event(f"Traceback: {traceback.format_exc()}")
                outputs = {}

            # Retry once on failure/parse error with a stricter instruction prefix
            if _is_failed_outputs(outputs):
                add_event("Retrying LLM once due to invalid/parse-error output")
                context_retry_payload = OrderedDict([
                    ("retry_instruction", "Return ONLY the JSON array per schema with no prose."),
                    ("original_context", context_payload)
                ])
                context_retry = json.dumps(context_retry_payload, default=json_default)
                try:
                    outputs = agent.decide_trade(args.assets, context_retry)
                    if not isinstance(outputs, dict):
                        add_event(f"Retry invalid format: {outputs}")
                        outputs = {}
                except Exception as e:
                    import traceback
                    add_event(f"Retry agent error: {e}")
                    add_event(f"Retry traceback: {traceback.format_exc()}")
                    outputs = {}

            reasoning_text = outputs.get("reasoning", "") if isinstance(outputs, dict) else ""
            if reasoning_text:
                add_event(f"LLM reasoning summary: {reasoning_text}")

            # Log full cycle decisions for the dashboard
            cycle_decisions = []
            for d in outputs.get("trade_decisions", []) if isinstance(outputs, dict) else []:
                cycle_decisions.append({
                    "asset": d.get("asset"),
                    "action": d.get("action", "hold"),
                    "allocation_usd": d.get("allocation_usd", 0),
                    "rationale": d.get("rationale", ""),
                })
            cycle_log = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cycle": invocation_count,
                "reasoning": reasoning_text[:2000] if reasoning_text else "",
                "decisions": cycle_decisions,
                "account_value": round_or_none(account_value, 2),
                "balance": round_or_none(state['balance'], 2),
                "positions_count": len([p for p in state['positions'] if abs(float(p.get('szi') or 0)) > 0]),
            }
            try:
                with open(decisions_path, "a") as f:
                    f.write(json.dumps(cycle_log) + "\n")
            except Exception:
                pass

            # Execute trades for each asset
            for output in outputs.get("trade_decisions", []) if isinstance(outputs, dict) else []:
                try:
                    asset = output.get("asset")
                    if not asset or asset not in args.assets:
                        continue
                    action = output.get("action")
                    current_price = asset_prices.get(asset, 0)
                    action = output["action"]
                    rationale = output.get("rationale", "")
                    if rationale:
                        add_event(f"Decision rationale for {asset}: {rationale}")
                    if action in ("buy", "sell"):
                        is_buy = action == "buy"
                        alloc_usd = float(output.get("allocation_usd", 0.0))
                        if alloc_usd <= 0:
                            add_event(f"Holding {asset}: zero/negative allocation")
                            continue

                        # --- RISK: Validate trade before execution ---
                        output["current_price"] = current_price
                        allowed, reason, output = risk_mgr.validate_trade(
                            output, state, initial_account_value or 0
                        )
                        if not allowed:
                            add_event(f"RISK BLOCKED {asset}: {reason}")
                            with open(diary_path, "a") as f:
                                f.write(json.dumps({
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "asset": asset,
                                    "action": "risk_blocked",
                                    "reason": reason,
                                    "original_alloc_usd": alloc_usd,
                                }) + "\n")
                            continue
                        # Use potentially adjusted values from risk manager
                        alloc_usd = float(output.get("allocation_usd", alloc_usd))
                        amount = alloc_usd / current_price

                        # Place market or limit order via Venue abstraction
                        order_type  = output.get("order_type", "market")
                        limit_price = float(output["limit_price"]) if output.get("limit_price") else None

                        order = await venue.place_order(
                            symbol=asset,
                            side="buy" if is_buy else "sell",
                            quantity=amount,
                            order_type=order_type,
                            price=limit_price,
                            stop_loss=output.get("sl_price"),   # atomic SL where venue supports it
                            take_profit=output.get("tp_price"),  # atomic TP where venue supports it
                        )
                        if limit_price:
                            add_event(f"LIMIT {action.upper()} {asset} qty={amount:.4f} @ ${limit_price}")

                        # HL-specific TP/SL trigger orders (placed BEFORE fill-check sleep
                        # to eliminate the race window where the position has no protection).
                        tp_oid = sl_oid = None
                        if _hl_api:
                            if output.get("tp_price"):
                                try:
                                    tp_order = await _hl_api.place_take_profit(asset, is_buy, amount, output["tp_price"])
                                    _tp_oids = _hl_api.extract_oids(tp_order)
                                    tp_oid = _tp_oids[0] if _tp_oids else None
                                    add_event(f"TP placed {asset} at {output['tp_price']}")
                                except Exception as _tp_err:
                                    add_event(f"TP placement error {asset}: {_tp_err}")
                            if output.get("sl_price"):
                                try:
                                    sl_order = await _hl_api.place_stop_loss(asset, is_buy, amount, output["sl_price"])
                                    _sl_oids = _hl_api.extract_oids(sl_order)
                                    sl_oid = _sl_oids[0] if _sl_oids else None
                                    add_event(f"SL placed {asset} at {output['sl_price']}")
                                except Exception as _sl_err:
                                    add_event(f"SL placement error {asset}: {_sl_err}")

                        # Confirm fill via recent fills (HL only; other venues use order.status)
                        filled = getattr(order, "status", "") == "filled"
                        if _hl_api and not filled:
                            await asyncio.sleep(1)
                            try:
                                fills_check = await _hl_api.get_recent_fills(limit=10)
                                for fc in reversed(fills_check):
                                    if fc.get("coin") == asset or fc.get("asset") == asset:
                                        filled = True
                                        break
                            except Exception:
                                pass

                        # Realized PnL for Sharpe tracking
                        _realized_pnl = None
                        for _prior in active_trades:
                            if _prior.get("asset") == asset and _prior.get("entry_price"):
                                _pe = float(_prior["entry_price"])
                                _pq = float(_prior.get("amount", 0))
                                if _pq > 0 and _pe > 0:
                                    _dir = 1 if _prior.get("is_long") else -1
                                    _realized_pnl = round(_dir * _pq * (current_price - _pe), 4)
                                break
                        trade_log.append({
                            "type": action, "price": current_price, "amount": amount,
                            "exit_plan": output.get("exit_plan", ""), "filled": filled,
                            "pnl": _realized_pnl,
                        })
                        # Reconcile: if opposite-side position exists or TP/SL just filled, clear stale active_trades for this asset
                        for existing in active_trades[:]:
                            if existing.get('asset') == asset:
                                try:
                                    active_trades.remove(existing)
                                except ValueError:
                                    pass
                        active_trades.append({
                            "asset": asset,
                            "is_long": is_buy,
                            "amount": amount,
                            "entry_price": current_price,
                            "tp_oid": tp_oid,
                            "sl_oid": sl_oid,
                            "exit_plan": output["exit_plan"],
                            "opened_at": datetime.now().isoformat()
                        })
                        add_event(f"{action.upper()} {asset} amount {amount:.4f} at ~{current_price}")
                        if rationale:
                            add_event(f"Post-trade rationale for {asset}: {rationale}")
                        # Write to diary after confirming fills status
                        with open(diary_path, "a") as f:
                            diary_entry = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "asset": asset,
                                "action": action,
                                "order_type": order_type,
                                "limit_price": limit_price,
                                "allocation_usd": alloc_usd,
                                "amount": amount,
                                "entry_price": current_price,
                                "tp_price": output.get("tp_price"),
                                "tp_oid": tp_oid,
                                "sl_price": output.get("sl_price"),
                                "sl_oid": sl_oid,
                                "exit_plan": output.get("exit_plan", ""),
                                "rationale": output.get("rationale", ""),
                                "order_result": str(order),
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "filled": filled
                            }
                            f.write(json.dumps(diary_entry) + "\n")
                    else:
                        add_event(f"Hold {asset}: {output.get('rationale', '')}")
                        # Write hold to diary
                        with open(diary_path, "a") as f:
                            diary_entry = {
                                "timestamp": datetime.now().isoformat(),
                                "asset": asset,
                                "action": "hold",
                                "rationale": output.get("rationale", "")
                            }
                            f.write(json.dumps(diary_entry) + "\n")
                except Exception as e:
                    import traceback
                    add_event(f"Execution error {asset}: {e}")
                    add_event(f"Traceback: {traceback.format_exc()}")

            await asyncio.sleep(get_interval_seconds(args.interval))

    async def handle_diary(request):
        """Return diary entries as JSON or newline-delimited text."""
        try:
            raw = request.query.get('raw')
            download = request.query.get('download')
            if raw or download:
                if not os.path.exists(diary_path):
                    return web.Response(text="", content_type="text/plain")
                with open(diary_path, "r") as f:
                    data = f.read()
                headers = {}
                if download:
                    headers["Content-Disposition"] = f"attachment; filename=diary.jsonl"
                return web.Response(text=data, content_type="text/plain", headers=headers)
            limit = int(request.query.get('limit', '200'))
            with open(diary_path, "r") as f:
                lines = f.readlines()
            start = max(0, len(lines) - limit)
            entries = [json.loads(l) for l in lines[start:]]
            return web.json_response({"entries": entries})
        except FileNotFoundError:
            return web.json_response({"entries": []})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_logs(request):
        """Stream log files with optional download or tailing behaviour."""
        try:
            path = request.query.get('path', str(_LOG_DIR / 'llm_requests.log'))
            download = request.query.get('download')
            limit_param = request.query.get('limit')
            if not os.path.exists(path):
                return web.Response(text="", content_type="text/plain")
            with open(path, "r") as f:
                data = f.read()
            if download or (limit_param and (limit_param.lower() == 'all' or limit_param == '-1')):
                headers = {}
                if download:
                    headers["Content-Disposition"] = f"attachment; filename={os.path.basename(path)}"
                return web.Response(text=data, content_type="text/plain", headers=headers)
            limit = int(limit_param) if limit_param else 2000
            return web.Response(text=data[-limit:], content_type="text/plain")
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    _allowed_origin = os.environ.get("ALLOWED_ORIGINS", "").split(",")[0].strip() or "*"

    def _cors(response):
        """Add CORS headers so the Next.js UI can call the API."""
        response.headers["Access-Control-Allow-Origin"] = _allowed_origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    async def handle_status(request):
        """Agent health — provider, model, venue, uptime, tick count."""
        uptime_s = (datetime.now(timezone.utc) - start_time).total_seconds()
        return _cors(web.json_response({
            "status": "running",
            "provider": agent.provider.name,
            "model": agent.model,
            "venue": args.venue or "hyperliquid",
            "assets": args.assets,
            "interval": args.interval,
            "uptime_seconds": int(uptime_s),
            "tick_count": invocation_count,
        }))

    async def handle_account(request):
        """Current account snapshot — balance, equity, PnL, return."""
        try:
            state = await hyperliquid.get_user_state()
            total_value = state.get("total_value") or (
                state["balance"] + sum(p.get("pnl", 0) for p in state["positions"])
            )
            init = initial_account_value or total_value
            return _cors(web.json_response({
                "balance": round(state["balance"], 4),
                "equity": round(total_value, 4),
                "initial_equity": round(init, 4),
                "total_return_pct": round((total_value - init) / init * 100, 4) if init else 0,
                "open_positions": len(state["positions"]),
                "sharpe": round(calculate_sharpe(trade_log), 4),
            }))
        except Exception as e:
            return _cors(web.json_response({"error": str(e)}, status=500))

    async def handle_positions(request):
        """Live open positions."""
        try:
            state = await hyperliquid.get_user_state()
            rows = []
            for pos in state["positions"]:
                coin = pos.get("coin")
                px = await hyperliquid.get_current_price(coin) if coin else None
                rows.append({
                    "symbol": coin,
                    "quantity": round_or_none(pos.get("szi"), 6),
                    "entry_price": round_or_none(pos.get("entryPx"), 2),
                    "current_price": round_or_none(px, 2),
                    "liquidation_price": round_or_none(pos.get("liquidationPx") or pos.get("liqPx"), 2),
                    "unrealized_pnl": round_or_none(pos.get("pnl"), 4),
                    "leverage": pos.get("leverage"),
                })
            return _cors(web.json_response({"positions": rows}))
        except Exception as e:
            return _cors(web.json_response({"error": str(e)}, status=500))

    async def handle_risk(request):
        """Active risk configuration."""
        from src.config_loader import CONFIG as CFG
        return _cors(web.json_response({
            "max_position_pct": CFG.get("max_position_pct"),
            "max_leverage": CFG.get("max_leverage"),
            "mandatory_sl_pct": CFG.get("mandatory_sl_pct"),
            "max_loss_per_position_pct": CFG.get("max_loss_per_position_pct"),
            "daily_loss_circuit_breaker_pct": CFG.get("daily_loss_circuit_breaker_pct"),
            "max_total_exposure_pct": CFG.get("max_total_exposure_pct"),
            "max_concurrent_positions": CFG.get("max_concurrent_positions"),
            "min_balance_reserve_pct": CFG.get("min_balance_reserve_pct"),
        }))

    async def handle_decisions(request):
        """Last N AI trade decisions from the diary."""
        try:
            limit = int(request.query.get("limit", "20"))
            if not os.path.exists(diary_path):
                return _cors(web.json_response({"decisions": []}))
            with open(diary_path) as f:
                lines = f.readlines()
            start = max(0, len(lines) - limit)
            entries = [json.loads(l) for l in lines[start:]]
            return _cors(web.json_response({"decisions": entries}))
        except Exception as e:
            return _cors(web.json_response({"error": str(e)}, status=500))

    async def start_api(app):
        """Register HTTP endpoints."""
        app.router.add_get("/diary", handle_diary)
        app.router.add_get("/logs", handle_logs)
        app.router.add_get("/api/status", handle_status)
        app.router.add_get("/api/account", handle_account)
        app.router.add_get("/api/positions", handle_positions)
        app.router.add_get("/api/risk", handle_risk)
        app.router.add_get("/api/decisions", handle_decisions)

    async def main_async():
        """Start the aiohttp server and kick off the trading loop."""
        app = web.Application()
        await start_api(app)
        from src.config_loader import CONFIG as CFG
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, CFG.get("api_host"), int(CFG.get("api_port")))
        await site.start()
        await run_loop()

    def calculate_total_return(state, trade_log):
        """Compute percent return relative to an assumed initial balance."""
        initial = 10000
        current = state['balance'] + sum(p.get('pnl', 0) for p in state.get('positions', []))
        return ((current - initial) / initial) * 100 if initial else 0

    def calculate_sharpe(returns):
        """Compute a naive Sharpe-like ratio from the trade log.

        Each entry in `returns` may carry a `pnl` key (set when a position closes)
        or a `return_pct` key.  Entries without either are ignored so that open
        trades don't dilute the ratio with zeros.
        """
        if not returns:
            return 0
        vals = [
            r["pnl"] for r in returns
            if "pnl" in r and r["pnl"] is not None
        ]
        if len(vals) < 2:
            return 0
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = math.sqrt(var) if var > 0 else 0
        return mean / std if std > 0 else 0

    async def check_exit_condition(trade, hyperliquid_api):
        """Evaluate whether a given trade's exit plan triggers a close."""
        plan = (trade.get("exit_plan") or "").lower()
        if not plan:
            return False
        try:
            candles_4h = await hyperliquid_api.get_candles(trade["asset"], "4h", 60)
            indicators = compute_all(candles_4h)
            if "macd" in plan and "below" in plan:
                macd_val = latest(indicators.get("macd", []))
                threshold = float(plan.split("below")[-1].strip())
                return macd_val is not None and macd_val < threshold
            if "close above ema50" in plan:
                ema50_val = latest(indicators.get("ema50", []))
                current = await hyperliquid_api.get_current_price(trade["asset"])
                return ema50_val is not None and current > ema50_val
        except Exception:
            return False
        return False

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
