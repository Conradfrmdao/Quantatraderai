/**
 * Fast live price endpoint — returns the latest price for any symbol.
 * Uses Yahoo Finance v8 chart with 1-minute interval, 1-day range
 * (same API as /api/chart — confirmed working).
 * No auth — public market data.
 *
 * GET /api/price?symbol=EURUSD
 */

export const runtime = "nodejs";

const SYMBOL_MAP: Record<string, string> = {
  XAUUSD: "GC=F", GOLD: "GC=F",
  XAGUSD: "SI=F", SILVER: "SI=F",
  USOIL: "CL=F", WTI: "CL=F", OIL: "CL=F",
  US30: "^DJI",   DJI: "^DJI",
  NAS100: "^NDX",  NDX: "^NDX",
  SPX500: "^GSPC", SP500: "^GSPC",
  DE40: "^GDAXI",
  UK100: "^FTSE",
  JP225: "^N225",
};

function toYahooTicker(symbol: string): string {
  const upper = symbol.toUpperCase().replace(/[/_\\s\\-]/g, "");
  if (SYMBOL_MAP[upper]) return SYMBOL_MAP[upper];
  if (/^[A-Z]{6}$/.test(upper) && !upper.endsWith("USDT") && !upper.endsWith("BTC")) {
    return `${upper}=X`;
  }
  return upper;
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = url.searchParams.get("symbol") ?? "";
  if (!symbol) return Response.json({ error: "symbol required" }, { status: 400 });

  const ticker = toYahooTicker(symbol);

  // Use v8 chart with 2m interval, 1d range — gets the latest bars including current price
  const chartUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?interval=2m&range=1d&includePrePost=false`;

  // H10: retry with backoff on 429
  async function fetchWithRetry(url: string, attempts = 3): Promise<Response> {
    let delay = 800;
    for (let i = 0; i < attempts; i++) {
      const ctrl = new AbortController();
      const t    = setTimeout(() => ctrl.abort(), 6000);
      try {
        const r = await fetch(url, {
          signal: ctrl.signal,
          headers: { "User-Agent": "Mozilla/5.0 (compatible; QuantatraderAI/1.0)", "Accept": "application/json" },
          cache: "no-store",
        });
        clearTimeout(t);
        if (r.status === 429 && i < attempts - 1) { await new Promise(res => setTimeout(res, delay)); delay *= 2; continue; }
        return r;
      } catch (e) { clearTimeout(t); if (i === attempts - 1) throw e; await new Promise(res => setTimeout(res, delay)); delay *= 2; }
    }
    throw new Error("exhausted");
  }

  try {
    const res = await fetchWithRetry(chartUrl);

    if (!res.ok) {
      return Response.json({ error: `Price fetch failed ${res.status} for ${ticker}` }, { status: 502 });
    }

    const json = await res.json() as {
      chart?: {
        result?: Array<{
          meta?: {
            regularMarketPrice?: number;
            previousClose?: number;
            regularMarketTime?: number;
            currency?: string;
            exchangeTimezoneName?: string;
          };
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
      return Response.json({ error: `${json.chart.error.description}` }, { status: 404 });
    }

    const result = json.chart?.result?.[0];
    if (!result) {
      return Response.json({ error: `No data for ${ticker}` }, { status: 404 });
    }

    // Get the latest close from the bar data (most accurate current price)
    const quotes = result.indicators?.quote?.[0];
    const closes = quotes?.close ?? [];
    const highs  = quotes?.high  ?? [];
    const lows   = quotes?.low   ?? [];

    // Find the last non-null close
    let latestClose = result.meta?.regularMarketPrice;
    let latestHigh  = latestClose;
    let latestLow   = latestClose;
    for (let i = closes.length - 1; i >= 0; i--) {
      if (closes[i] != null) {
        latestClose = closes[i]!;
        latestHigh  = highs[i]  ?? latestClose;
        latestLow   = lows[i]   ?? latestClose;
        break;
      }
    }

    const prevClose  = result.meta?.previousClose ?? latestClose ?? 0;
    const change     = latestClose != null ? latestClose - prevClose : 0;
    const changePct  = prevClose ? (change / prevClose) * 100 : 0;

    return Response.json({
      price:     latestClose,
      high:      latestHigh,
      low:       latestLow,
      change,
      changePct,
      prevClose,
      ts:        result.meta?.regularMarketTime,
      ticker,
      symbol,
      currency:  result.meta?.currency,
    }, {
      headers: { "Cache-Control": "public, s-maxage=3, stale-while-revalidate=5" },
    });
  } catch (e) {
    console.error("[price]", e);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 502 });
  }
}
