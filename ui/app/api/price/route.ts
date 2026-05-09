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

// ── Stooq: free real-time forex quotes (no API key needed) ──────
// Maps Yahoo Finance =X symbols to Stooq lowercase symbols
const STOOQ_MAP: Record<string, string> = {
  "GC=F": "xauusd", "SI=F": "xagusd", "CL=F": "cl.f",
  "^DJI": "dji.us", "^GSPC": "spx.us", "^NDX": "ndq.us",
  "^GDAXI": "dax.de", "^FTSE": "ftse.uk", "^N225": "n225.jp",
};

function toStooqSymbol(yahooTicker: string): string | null {
  if (STOOQ_MAP[yahooTicker]) return STOOQ_MAP[yahooTicker];
  // Forex pairs like EURUSD=X → eurusd
  if (yahooTicker.endsWith("=X")) return yahooTicker.replace("=X", "").toLowerCase();
  return null;
}

async function fetchStooqPrice(yahooTicker: string): Promise<{ price: number; high: number; low: number } | null> {
  const sym = toStooqSymbol(yahooTicker);
  if (!sym) return null;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 5000);
    const res = await fetch(
      `https://stooq.com/q/l/?s=${encodeURIComponent(sym)}&f=sd2t2ohlcv&e=csv`,
      { signal: ctrl.signal, headers: { "User-Agent": "Mozilla/5.0" }, cache: "no-store" }
    );
    clearTimeout(t);
    if (!res.ok) return null;
    const text = await res.text();
    const lines = text.trim().split("\n");
    if (lines.length < 2) return null;
    const cols = lines[1].split(","); // Date,Time,Open,High,Low,Close,Volume
    const close = parseFloat(cols[5]);
    const high  = parseFloat(cols[3]);
    const low   = parseFloat(cols[4]);
    if (!isFinite(close) || close <= 0) return null;
    return { price: close, high, low };
  } catch { return null; }
}

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const symbol = url.searchParams.get("symbol") ?? "";
  if (!symbol) return Response.json({ error: "symbol required" }, { status: 400 });

  const ticker = toYahooTicker(symbol);

  // ── Try Stooq first for forex/commodity pairs (real-time, free) ──
  const isForexOrCommodity = ticker.endsWith("=X") || ticker.endsWith("=F") || ticker.startsWith("^");
  if (isForexOrCommodity) {
    const stooq = await fetchStooqPrice(ticker);
    if (stooq) {
      return Response.json({
        price: stooq.price, high: stooq.high, low: stooq.low,
        change: null, changePct: null, prevClose: null,
        ts: Math.floor(Date.now() / 1000),
        ticker, symbol, source: "stooq",
      }, {
        headers: { "Cache-Control": "public, s-maxage=3, stale-while-revalidate=5" },
      });
    }
  }

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
