import { describe, expect, it } from "vitest";

import { buildMarketCandlesUrl, buildMarketContextUrl } from "@/lib/market-query";

describe("market-query", () => {
  it("builds candle URLs against the backend market API with the selected venue and symbol", () => {
    const url = buildMarketCandlesUrl({
      symbol: "ETH/USDT",
      timeframe: "5m",
      venue: "BINANCE",
      market: "futures",
      limit: 240,
    });

    expect(url.startsWith("/api/market/candles?")).toBe(true);
    expect(url).toContain("symbol=ETH%2FUSDT");
    expect(url).toContain("timeframe=5m");
    expect(url).toContain("venue=binance");
    expect(url).toContain("market=futures");
    expect(url).toContain("limit=240");
    expect(url.includes("api.binance.com")).toBe(false);
  });

  it("builds context URLs against the shared backend market API", () => {
    const url = buildMarketContextUrl({
      symbol: "AAPL",
      timeframe: "1h",
      venue: "ALPACA",
      market: "spot",
    });

    expect(url).toBe("/api/market/context?symbol=AAPL&timeframe=1h&venue=alpaca&market=spot");
  });
});
