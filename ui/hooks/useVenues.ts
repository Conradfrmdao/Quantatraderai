"use client";
import { useState, useEffect, useCallback } from "react";

export interface UserVenue {
  id:          string;
  displayName: string;
  type:        string;  // HYPERLIQUID | BINANCE | OANDA | METATRADER | ALPACA | IBKR | BYBIT | OKX | KRAKEN | COINBASE | CCXT | POLYMARKET
  market:      string;
  paperCapital: number;
  isPaper:     boolean;
  isActive:    boolean;
  network:     string | null;
  ccxtExchangeId: string | null;
}

/** Fetches all venues the current user has configured (from /api/venues). */
export function useVenues() {
  const [venues, setVenues]   = useState<UserVenue[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    fetch("/api/venues")
      .then(r => r.json())
      .then((d: { venues: UserVenue[] } | UserVenue[]) => {
        const list = Array.isArray(d) ? d : d.venues ?? [];
        setVenues(list);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { venues, loading, reload };
}

/** VenueType → backend registry name used by /api/agent/start */
export const VENUE_REGISTRY_NAME: Record<string, string> = {
  HYPERLIQUID: "hyperliquid",
  BINANCE:     "binance",
  BYBIT:       "bybit",
  OKX:         "okx",
  KRAKEN:      "kraken",
  COINBASE:    "coinbase",
  OANDA:       "oanda",
  METATRADER:  "metatrader",
  ALPACA:      "alpaca",
  IBKR:        "ibkr",
  CCXT:        "ccxt",
  POLYMARKET:  "polymarket",
};

/** Default symbol universe per venue type — what to populate the symbol picker with. */
export const VENUE_SYMBOLS: Record<string, string[]> = {
  HYPERLIQUID: ["BTC", "ETH", "SOL", "ARB", "AVAX", "DOGE", "LINK", "SUI"],
  BINANCE:     ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT", "LINK/USDT"],
  BYBIT:       ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT"],
  OKX:         ["BTC-USDT", "ETH-USDT", "SOL-USDT"],
  KRAKEN:      ["BTC/USD", "ETH/USD", "SOL/USD"],
  COINBASE:    ["BTC-USD", "ETH-USD", "SOL-USD"],
  OANDA:       ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "XAU_USD"],
  METATRADER:  ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "US30", "NAS100", "SPX500"],
  ALPACA:      ["AAPL", "TSLA", "NVDA", "MSFT", "SPY", "QQQ"],
  IBKR:        ["AAPL", "TSLA", "NVDA", "MSFT", "SPY", "QQQ"],
  CCXT:        ["BTC/USDT", "ETH/USDT"],
  POLYMARKET:  [],
};

/** Human-readable label for asset class */
export const VENUE_LABEL: Record<string, string> = {
  HYPERLIQUID: "Hyperliquid · Crypto Perps",
  BINANCE:     "Binance · Crypto",
  BYBIT:       "Bybit · Crypto Perps",
  OKX:         "OKX · Crypto",
  KRAKEN:      "Kraken · Crypto",
  COINBASE:    "Coinbase · Crypto",
  OANDA:       "OANDA · Forex / CFDs",
  METATRADER:  "MetaTrader · Forex / Metals / Indices",
  ALPACA:      "Alpaca · US Stocks",
  IBKR:        "Interactive Brokers · Stocks / Options / Futures",
  CCXT:        "CCXT · Generic Exchange",
  POLYMARKET:  "Polymarket · Prediction Markets",
};
