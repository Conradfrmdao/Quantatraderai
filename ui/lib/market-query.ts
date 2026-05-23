export interface MarketQueryParams {
  symbol: string;
  timeframe: string;
  venue: string;
  market?: string;
  limit?: number;
}

export function buildMarketCandlesUrl({ symbol, timeframe, venue, market = "spot", limit = 500 }: MarketQueryParams): string {
  const params = new URLSearchParams({
    symbol,
    timeframe,
    venue: venue.toLowerCase(),
    market,
    limit: String(limit),
  });
  return `/api/market/candles?${params.toString()}`;
}

export function buildMarketContextUrl({ symbol, timeframe, venue, market = "spot" }: Omit<MarketQueryParams, "limit">): string {
  const params = new URLSearchParams({
    symbol,
    timeframe,
    venue: venue.toLowerCase(),
    market,
  });
  return `/api/market/context?${params.toString()}`;
}
