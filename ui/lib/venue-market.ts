export type VenueMarket = "spot" | "futures" | "forex" | "stocks" | "prediction";

type MarketOption = { value: VenueMarket; label: string };

const MARKET_OPTIONS: Record<string, MarketOption[]> = {
  HYPERLIQUID: [{ value: "futures", label: "Futures" }],
  BINANCE: [
    { value: "spot", label: "Spot" },
    { value: "futures", label: "Futures" },
  ],
  BYBIT: [
    { value: "futures", label: "Futures" },
    { value: "spot", label: "Spot" },
  ],
  OKX: [
    { value: "spot", label: "Spot" },
    { value: "futures", label: "Futures" },
  ],
  KRAKEN: [{ value: "spot", label: "Spot" }],
  COINBASE: [{ value: "spot", label: "Spot" }],
  CCXT: [
    { value: "spot", label: "Spot" },
    { value: "futures", label: "Futures" },
  ],
  OANDA: [{ value: "forex", label: "Forex" }],
  METATRADER: [{ value: "forex", label: "Forex" }],
  ALPACA: [{ value: "stocks", label: "Stocks" }],
  IBKR: [{ value: "stocks", label: "Stocks" }],
  POLYMARKET: [{ value: "prediction", label: "Prediction" }],
};

export function marketOptionsForVenueType(type: string | null | undefined): MarketOption[] {
  return MARKET_OPTIONS[type ?? ""] ?? [{ value: "spot", label: "Spot" }];
}

export function defaultMarketForVenueType(type: string | null | undefined): VenueMarket {
  return marketOptionsForVenueType(type)[0]?.value ?? "spot";
}

export function normalizeVenueMarket(type: string | null | undefined, market: string | null | undefined): VenueMarket {
  const requested = (market ?? "").toLowerCase();
  const allowed = marketOptionsForVenueType(type).map(option => option.value);
  return allowed.includes(requested as VenueMarket)
    ? (requested as VenueMarket)
    : defaultMarketForVenueType(type);
}

export function venueSupportsEditableMarket(type: string | null | undefined): boolean {
  return marketOptionsForVenueType(type).length > 1;
}
