/**
 * Server-side proxy for Yahoo Finance chart data.
 * Needed because Yahoo Finance blocks direct browser fetch (CORS).
 * Called by TradingChart for all non-crypto symbols:
 *   forex (EURUSD=X), stocks (AAPL), indices (^DJI), commodities (GC=F)
 *
 * GET /api/chart?symbol=EURUSD&interval=60m&range=30d
 */

export const runtime = "nodejs"; // use Node.js runtime (not edge) for full fetch support

// Yahoo Finance timeframe param → interval + range
const DEFAULT_PARAMS: Record<string, { interval: string; range: string }> = {
  "1m":  { interval: "1m",  range: "1d"  },
  "5m":  { interval: "5m",  range: "5d"  },
  "15m": { interval: "15m", range: "5d"  },
  "30m": { interval: "30m", range: "30d" },
  "1h":  { interval: "60m", range: "30d" },
  "4h":  { interval: "1d",  range: "60d" }, // Yahoo has no 4h; use 1d data
  "1d":  { interval: "1d",  range: "1y"  },
};

// Map our generic symbols → Yahoo Finance ticker symbols
const SYMBOL_MAP: Record<string, string> = {
  // Metals
  XAUUSD: "GC=F", GOLD: "GC=F",
  XAGUSD: "SI=F", SILVER: "SI=F",
  // Oil
  USOIL: "CL=F", WTI: "CL=F", OIL: "CL=F",
  // Indices
  US30: "^DJI",   DJI: "^DJI",   DOW: "^DJI",
  NAS100: "^NDX",  NDX: "^NDX",   NASDAQ: "^NDX",
  SPX500: "^GSPC", SP500: "^GSPC", GSPC: "^GSPC",
  DE40: "^GDAXI",
  UK100: "^FTSE",
  JP225: "^N225",
  // Forex 6-char → add =X suffix
};

function toYahooTicker(symbol: string): string {
  const upper = symbol.toUpperCase().replace(/[/_\s\-]/g, "");
  if (SYMBOL_MAP[upper]) return SYMBOL_MAP[upper];
  // 6-char forex pair (EURUSD, GBPJPY etc.) — NOT ending in USDT/BTC
  if (/^[A-Z]{6}$/.test(upper) && !upper.endsWith("USDT") && !upper.endsWith("BTC") && !upper.endsWith("ETH")) {
    return `${upper}=X`;
  }
  return upper; // stocks, ETFs, etc.
}

interface Bar { time: number; open: number; high: number; low: number; close: number }

export async function GET(req: Request) {
  const url      = new URL(req.url);
  const symbol   = url.searchParams.get("symbol") ?? "";
  const tf       = url.searchParams.get("interval") ?? "1h";
  const range    = url.searchParams.get("range");

  if (!symbol) {
    return Response.json({ error: "symbol required" }, { status: 400 });
  }

  const params   = DEFAULT_PARAMS[tf] ?? DEFAULT_PARAMS["1h"];
  const interval = params.interval;
  const useRange = range ?? params.range;
  const ticker   = toYahooTicker(symbol);

  const yahooUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=${interval}&range=${useRange}&includePrePost=false`;

  // H10: Retry with exponential backoff on 429 / transient errors
  async function fetchWithRetry(url: string, maxAttempts = 3): Promise<Response> {
    let delay = 1000;
    for (let i = 0; i < maxAttempts; i++) {
      const controller = new AbortController();
      const timeout    = setTimeout(() => controller.abort(), 8000);
      try {
        const r = await fetch(url, {
          signal: controller.signal,
          headers: {
            "User-Agent":      "Mozilla/5.0 (compatible; QuantatraderAI/1.0)",
            "Accept":          "application/json",
            "Accept-Language": "en-US,en;q=0.9",
          },
          next: { revalidate: 60 },
        });
        clearTimeout(timeout);
        if (r.status === 429 && i < maxAttempts - 1) {
          await new Promise(res => setTimeout(res, delay));
          delay *= 2;
          continue;
        }
        return r;
      } catch (e) {
        clearTimeout(timeout);
        if (i === maxAttempts - 1) throw e;
        await new Promise(res => setTimeout(res, delay));
        delay *= 2;
      }
    }
    throw new Error("fetchWithRetry: exhausted");
  }

  try {
    const res = await fetchWithRetry(yahooUrl);

    if (!res.ok) {
      return Response.json({ error: `Yahoo Finance returned ${res.status} for ${ticker}` }, { status: 502 });
    }

    const json = await res.json() as {
      chart?: {
        result?: Array<{
          timestamp?: number[];
          indicators?: {
            quote?: Array<{
              open?: (number | null)[];
              high?: (number | null)[];
              low?:  (number | null)[];
              close?: (number | null)[];
            }>;
          };
        }>;
        error?: { code: string; description: string };
      };
    };

    if (json.chart?.error) {
      return Response.json({ error: `${json.chart.error.description} (${ticker})` }, { status: 404 });
    }

    const result = json.chart?.result?.[0];
    if (!result || !result.timestamp?.length) {
      return Response.json({ error: `No data found for symbol "${symbol}" (${ticker})` }, { status: 404 });
    }

    const timestamps = result.timestamp;
    const quote      = result.indicators?.quote?.[0];
    if (!quote) return Response.json({ bars: [] });

    const bars: Bar[] = [];
    for (let i = 0; i < timestamps.length; i++) {
      const o = quote.open?.[i], h = quote.high?.[i], l = quote.low?.[i], c = quote.close?.[i];
      if (o == null || h == null || l == null || c == null) continue;
      bars.push({ time: timestamps[i], open: o, high: h, low: l, close: c });
    }

    return Response.json({ bars, ticker, symbol });
  } catch (e) {
    console.error("[chart]", e);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 502 });
  }
}
