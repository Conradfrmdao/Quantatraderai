"use client";
import { useEffect, useRef, useState } from "react";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
type TF = (typeof TIMEFRAMES)[number];

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  symbol?:    string;
  venueType?: string;
  livePrice?: number | null; // Real-time price from WebSocket — updates last bar instantly
}

// Crypto venues where Binance public data is a valid fallback
const CRYPTO_VENUES = new Set(["BINANCE", "BYBIT", "OKX", "KRAKEN", "COINBASE", "HYPERLIQUID", "CCXT"]);
const FOREX_VENUES  = new Set(["OANDA", "METATRADER"]);
const STOCK_VENUES  = new Set(["ALPACA", "IBKR"]);

/**
 * Convert venue symbol → Yahoo Finance ticker symbol for public data.
 * Works without any API key — same data source as TradingView free tier.
 */
function toYahooSymbol(sym: string, venueType: string): string {
  const upper = sym.toUpperCase().replace(/[/_\s-]/g, "");
  if (FOREX_VENUES.has(venueType)) {
    // EURUSD → EURUSD=X, XAUUSD → GC=F (Gold), XAGUSD → SI=F (Silver)
    const metalMap: Record<string, string> = {
      XAUUSD: "GC=F", XAUEUR: "GC=F", GOLD: "GC=F",
      XAGUSD: "SI=F", SILVER: "SI=F",
      US30: "^DJI", DJI: "^DJI", DOW: "^DJI",
      NAS100: "^NDX", NASDAQ: "^NDX", NDX: "^NDX",
      SPX500: "^GSPC", SP500: "^GSPC", GSPC: "^GSPC",
      DE40: "^GDAXI", UK100: "^FTSE", JP225: "^N225",
      OIL: "CL=F", USOIL: "CL=F", WTI: "CL=F",
    };
    if (metalMap[upper]) return metalMap[upper];
    // Forex pair: EURUSD → EURUSD=X
    if (upper.length === 6 && !upper.includes("=")) return `${upper}=X`;
    return upper;
  }
  if (STOCK_VENUES.has(venueType)) return upper; // AAPL, TSLA etc.
  return upper;
}

/** Yahoo Finance timeframe → interval+range query params */
function yahooParams(tf: string): { interval: string; range: string } {
  const map: Record<string, { interval: string; range: string }> = {
    "1m": { interval: "1m",  range: "1d"  },
    "5m": { interval: "5m",  range: "5d"  },
    "15m":{ interval: "15m", range: "5d"  },
    "30m":{ interval: "30m", range: "30d" },
    "1h": { interval: "60m", range: "30d" },
    "4h": { interval: "1d",  range: "60d" }, // Yahoo has no 4h; use 1d and show as close
    "1d": { interval: "1d",  range: "1y"  },
  };
  return map[tf] ?? { interval: "60m", range: "30d" };
}

function normaliseBinanceSymbol(sym: string): string {
  return sym.replace(/[/_\-]/g, "").toUpperCase();
}

function formatPrice(price: number, venueType: string): string {
  if (FOREX_VENUES.has(venueType)) {
    // Forex: no currency prefix, 4 decimal places
    return price.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 5 });
  }
  if (STOCK_VENUES.has(venueType)) {
    return `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  // Crypto: 2 decimals for high-value, 6 for small
  return `$${price.toLocaleString("en-US", { maximumFractionDigits: price > 10 ? 2 : 6 })}`;
}

type Bar = { time: number; open: number; high: number; low: number; close: number };

export function TradingChart({ symbol = "BTC/USDT", venueType = "BINANCE", livePrice }: Props) {
  const containerRef   = useRef<HTMLDivElement>(null);
  const chartRef       = useRef<any>(null);
  const seriesRef      = useRef<any>(null);
  const wsRef          = useRef<WebSocket | null>(null);
  const pollRef        = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastBarTimeRef = useRef<number>(0);

  const [ready,       setReady]       = useState(false);
  const [tf,          setTf]          = useState<TF>("1h");
  const [price,       setPrice]       = useState<number | null>(null);
  const [change,      setChange]      = useState<number | null>(null);
  const [live,        setLive]        = useState(false);
  const [loading,     setLoading]     = useState(true);
  const [noData,      setNoData]      = useState(false);   // agent not running yet
  const [dataSource,  setDataSource]  = useState("");      // "live" | "cached" | "public"

  const isCrypto = CRYPTO_VENUES.has(venueType);
  const isForex  = FOREX_VENUES.has(venueType);

  // ── 0. Push WebSocket live price to last bar instantly ──────────
  // When the parent passes livePrice (from the WS price_update event),
  // update the chart's last candle without waiting for the next poll.
  useEffect(() => {
    if (livePrice == null || !seriesRef.current || !lastBarTimeRef.current) return;
    setPrice(livePrice);
    try {
      seriesRef.current.update({
        time:  lastBarTimeRef.current,
        close: livePrice,
      } as any);
    } catch {}
  }, [livePrice]);

  // ── 1. Create chart instance once ──────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    let gone = false;
    import("lightweight-charts").then(({ createChart, CrosshairMode, CandlestickSeries }) => {
      if (gone || !containerRef.current) return;
      const chart = createChart(containerRef.current, {
        width:  containerRef.current.clientWidth,
        height: 340,
        layout: {
          background: { color: "transparent" },
          textColor:  "rgba(255,255,255,0.45)",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.03)" },
          horzLines: { color: "rgba(255,255,255,0.03)" },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: "rgba(255,255,255,0.05)" },
        timeScale:       { borderColor: "rgba(255,255,255,0.05)", timeVisible: true },
      });
      const series = chart.addSeries(CandlestickSeries, {
        upColor:       "#4ade80",
        downColor:     "#f87171",
        wickUpColor:   "#4ade80",
        wickDownColor: "#f87171",
        borderVisible: false,
      });
      chartRef.current  = chart;
      seriesRef.current = series;
      setReady(true);

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current)
          chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      });
      ro.observe(containerRef.current);
      return () => ro.disconnect();
    });
    return () => {
      gone = true;
      chartRef.current?.remove();
      chartRef.current  = null;
      seriesRef.current = null;
    };
  }, []);

  // ── 2. Load / reload on symbol · timeframe · venue change ──────
  useEffect(() => {
    if (!ready) return;

    wsRef.current?.close();
    if (pollRef.current) clearInterval(pollRef.current);
    setLive(false);
    setLoading(true);
    setNoData(false);
    setDataSource("");
    lastBarTimeRef.current = 0;

    let cancelled = false;

    const applyBars = (bars: Bar[]) => {
      seriesRef.current?.setData(bars as any[]);
      chartRef.current?.timeScale().fitContent();
      if (bars.length) {
        lastBarTimeRef.current = bars[bars.length - 1].time;
        setPrice(bars[bars.length - 1].close);
      }
      if (bars.length >= 2) {
        const first = bars[0].close;
        const last  = bars[bars.length - 1].close;
        setChange(((last - first) / first) * 100);
      }
      setLoading(false);
    };

    // ── A. Always try the backend first (has candle cache when agent runs) ──
    const loadFromBackend = async (): Promise<Bar[]> => {
      const url = `${API}/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}&limit=500&venue=${venueType.toLowerCase()}`;
      const res = await fetch(url);
      if (!res.ok) return [];
      const data = await res.json() as { candles?: Bar[] };
      return data.candles ?? [];
    };

    // ── B. Yahoo Finance via server-side proxy (avoids CORS) ──
    // Handles: forex (EURUSD), stocks (AAPL), indices (US30/^DJI), metals (XAUUSD/GC=F)
    const loadFromYahoo = async (): Promise<Bar[]> => {
      try {
        const res  = await fetch(`/api/chart?symbol=${encodeURIComponent(symbol)}&interval=${tf}`);
        if (!res.ok) return [];
        const data = await res.json() as { bars?: Bar[]; error?: string };
        if (data.error || !data.bars?.length) return [];
        return data.bars;
      } catch { return []; }
    };

    // ── C. Binance public fallback for crypto symbols ──
    const loadFromBinance = async (): Promise<Bar[]> => {
      const sym  = normaliseBinanceSymbol(symbol);
      const url  = `https://api.binance.com/api/v3/klines?symbol=${sym}&interval=${tf}&limit=500`;
      const res  = await fetch(url);
      const data = await res.json();
      if (!Array.isArray(data)) return [];
      return data.map((row: any[]) => ({
        time:  Math.floor(row[0] / 1000),
        open:  parseFloat(row[1]),
        high:  parseFloat(row[2]),
        low:   parseFloat(row[3]),
        close: parseFloat(row[4]),
      }));
    };

    const startBinanceLiveWS = () => {
      const sym = normaliseBinanceSymbol(symbol).toLowerCase();
      const ws  = new WebSocket(`wss://stream.binance.com:9443/ws/${sym}@kline_${tf}`);
      wsRef.current = ws;
      ws.onopen    = () => { if (!cancelled) { setLive(true); setDataSource("live"); } };
      ws.onclose   = () => { if (!cancelled) setLive(false); };
      ws.onmessage = (e: MessageEvent) => {
        if (!seriesRef.current || cancelled) return;
        const { k } = JSON.parse(e.data as string) as { k: any };
        const t = Math.floor(k.t / 1000);
        if (t < lastBarTimeRef.current) return;
        lastBarTimeRef.current = t;
        seriesRef.current.update({
          time: t, open: parseFloat(k.o), high: parseFloat(k.h),
          low: parseFloat(k.l), close: parseFloat(k.c),
        } as any);
        setPrice(parseFloat(k.c));
      };
    };

    const startPoll = (interval = 30_000) => {
      pollRef.current = setInterval(async () => {
        if (cancelled) return;
        const bars = await loadFromBackend().catch(() => []);
        if (bars.length) {
          seriesRef.current?.setData(bars as any[]);
          setPrice(bars[bars.length - 1].close);
          setLive(true);
          setDataSource("live");
        }
      }, interval);
    };

    const load = async () => {
      try {
        // Step 1: try backend cache first (fastest, most accurate when agent is live)
        let bars = await loadFromBackend();
        if (bars.length) {
          applyBars(bars);
          setDataSource("live");
          if (isCrypto) startBinanceLiveWS();
          else startPoll(10_000); // poll backend every 10s when agent is running
          return;
        }

        // Step 2: crypto — Binance public API (no account needed)
        if (isCrypto) {
          bars = await loadFromBinance();
          if (bars.length) {
            applyBars(bars);
            setDataSource("public");
            startBinanceLiveWS();
            return;
          }
        }

        // Step 3: forex/stocks/indices/metals — Yahoo Finance free public API
        // Works for EURUSD, GBP/USD, AAPL, TSLA, US30, NAS100, XAU/USD etc.
        if (!isCrypto) {
          bars = await loadFromYahoo();
          if (bars.length) {
            applyBars(bars);
            setDataSource("public");
            setLive(true);

            // ── Fast price tick: poll /api/price every 5s ──────────────
            // This updates the price header in real-time (like a WebSocket would)
            // without re-fetching the full bar history.
            const pricePollRef = { id: null as any };
            const fastPricePoll = async () => {
              if (cancelled) return;
              try {
                const r = await fetch(`/api/price?symbol=${encodeURIComponent(symbol)}`);
                if (!r.ok) return;
                const d = await r.json() as {
                  price?: number; changePct?: number; high?: number; low?: number; error?: string
                };
                if (d.price && !d.error) {
                  setPrice(d.price);
                  if (d.changePct !== undefined) setChange(d.changePct);
                  // Update the last bar on the chart with the current price
                  if (seriesRef.current && lastBarTimeRef.current) {
                    const nowTs = Math.floor(Date.now() / 1000);
                    seriesRef.current.update({
                      time:  lastBarTimeRef.current,
                      open:  bars[bars.length - 1]?.open ?? d.price,
                      high:  d.high  ?? Math.max(bars[bars.length - 1]?.high ?? d.price, d.price),
                      low:   d.low   ?? Math.min(bars[bars.length - 1]?.low  ?? d.price, d.price),
                      close: d.price,
                    } as any);
                  }
                }
              } catch {}
            };

            fastPricePoll(); // immediate first call
            pricePollRef.id = setInterval(fastPricePoll, 3_000) as any;

            // ── Slow bar history refresh every 60s ─────────────────────
            pollRef.current = setInterval(async () => {
              if (cancelled) { clearInterval(pricePollRef.id); return; }
              // Try live backend first (if agent started since last poll)
              const backendBars = await loadFromBackend().catch(() => []);
              if (backendBars.length) {
                seriesRef.current?.setData(backendBars as any[]);
                setDataSource("live");
                clearInterval(pricePollRef.id); // backend is live, no need for Yahoo polling
                startPoll(10_000);
                return;
              }
              // Refresh full Yahoo history
              const freshBars = await loadFromYahoo().catch(() => []);
              if (freshBars.length) {
                seriesRef.current?.setData(freshBars as any[]);
                bars.splice(0, bars.length, ...freshBars);
              }
            }, 20_000);

            return () => clearInterval(pricePollRef.id);
          }
        }

        // Step 4: nothing worked — show helpful placeholder
        if (!cancelled) { setLoading(false); setNoData(true); }
      } catch {
        if (!cancelled) { setLoading(false); setNoData(true); }
      }
    };

    load();

    return () => {
      cancelled = true;
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [ready, symbol, tf, venueType, isCrypto]);

  // ── Friendly venue label ────────────────────────────────────────
  const venueLabel: Record<string, string> = {
    OANDA: "OANDA", METATRADER: "MetaTrader", ALPACA: "Alpaca", IBKR: "Interactive Brokers",
    HYPERLIQUID: "Hyperliquid", BINANCE: "Binance", BYBIT: "Bybit", OKX: "OKX",
    KRAKEN: "Kraken", COINBASE: "Coinbase",
  };

  return (
    <div>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 20, fontWeight: 600, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
            {price !== null ? formatPrice(price, venueType) : "—"}
          </span>
          {change !== null && (
            <span style={{ fontSize: 13, fontWeight: 500, color: change >= 0 ? "#4ade80" : "#f87171" }}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </span>
          )}
          {!loading && (
            <span style={{ fontSize: 10, color: live ? "#4ade80" : "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: "0.08em", marginLeft: 6 }}>
              {live ? "● live" : dataSource === "cached" ? "cached" : dataSource === "public" ? "public" : ""}
            </span>
          )}
        </div>

        {/* Timeframe picker */}
        <div style={{ display: "flex", gap: 2 }}>
          {TIMEFRAMES.map(t => (
            <button key={t} onClick={() => setTf(t)} style={{
              padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500, cursor: "pointer",
              background: tf === t ? "rgba(255,255,255,0.1)" : "transparent",
              border: tf === t ? "1px solid rgba(255,255,255,0.15)" : "1px solid transparent",
              color: tf === t ? "#fff" : "var(--muted)",
            }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Chart canvas */}
      <div ref={containerRef} style={{ width: "100%", height: 340, position: "relative" }}>
        {/* Loading state */}
        {loading && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <div style={{ width: 24, height: 24, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.1)", borderTopColor: "rgba(255,255,255,0.5)", animation: "spin 0.8s linear infinite" }} />
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>Loading {symbol}…</span>
          </div>
        )}

        {/* No-data state — agent not running for this venue */}
        {!loading && noData && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 32, textAlign: "center" }}>
            <div style={{ fontSize: 32, lineHeight: 1 }}>
              {isForex ? "💱" : STOCK_VENUES.has(venueType) ? "📈" : "📊"}
            </div>
            <p style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
              {venueLabel[venueType] ?? venueType} — {symbol}
            </p>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", lineHeight: 1.6, maxWidth: 280 }}>
              Could not load chart data for <strong style={{ color: "rgba(255,255,255,0.6)" }}>{symbol}</strong>.
              Check the symbol is correct for {venueLabel[venueType] ?? venueType}.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
