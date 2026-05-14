"use client";
import { useEffect, useRef, useState } from "react";

import {
  alignToBucket,
  dedupeAndSortBars,
  describeFeedFreshness,
  formatTimestamp,
  getBrowserTimeZone,
  mergeRealtimeBar,
  secondsSince,
  timeframeSeconds,
  toUnixSeconds,
  validateCandleSequence,
  type Bar,
  type CandleValidation,
  type ChartTimezoneMode,
} from "@/lib/chart-sync";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
type TF = (typeof TIMEFRAMES)[number];

interface LiveChartEvent {
  symbol: string;
  price: number;
  ts?: number | null;
  exchangeTs?: number | null;
  receivedAt: number;
  candle?: Bar | null;
  timeframe?: string | null;
  transport?: string | null;
  source?: string | null;
}

interface Props {
  symbol?: string;
  venueType?: string;
  venueLabel?: string;
  assetClass?: string;
  liveEvent?: LiveChartEvent | null;
  appRealtimeConnected?: boolean;
}

interface HistoryResponse {
  bars: Bar[];
  source: string;
  timeBasis: string;
  exchangeTimezone: string;
  asOf: number | null;
}

interface PriceResponse {
  price?: number;
  changePct?: number | null;
  high?: number | null;
  low?: number | null;
  error?: string;
  source?: string;
  ts?: number | null;
  exchange_ts?: number | null;
  exchange_timezone?: string | null;
  transport?: string | null;
}

const EMPTY_VALIDATION: CandleValidation = {
  duplicates: 0,
  skippedIntervals: 0,
  misaligned: 0,
  futureBars: 0,
  latestBarAgeSec: null,
};

function inferAssetClassFromVenueType(venueType: string): "crypto" | "forex" | "stocks" | "prediction" {
  if (venueType === "OANDA" || venueType === "METATRADER") return "forex";
  if (venueType === "ALPACA" || venueType === "IBKR") return "stocks";
  if (venueType === "POLYMARKET") return "prediction";
  return "crypto";
}

function normaliseBinanceSymbol(sym: string): string {
  return sym.replace(/[/_\-]/g, "").toUpperCase();
}

function formatPrice(price: number, assetClass: string): string {
  if (assetClass === "forex") {
    return price.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 5 });
  }
  if (assetClass === "stocks") {
    return `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `$${price.toLocaleString("en-US", { maximumFractionDigits: price > 10 ? 2 : 6 })}`;
}

function transportLabel(transport: string, source: string): string {
  if (transport === "websocket") {
    if (source === "binance_ws") return "Binance websocket";
    return "Authenticated websocket";
  }
  if (transport === "polling") return "Venue polling";
  if (transport === "rest") return "REST snapshot";
  if (source === "cache" || source === "stale_cache") return "Cached snapshot";
  return "Idle";
}

function timezoneLabel(mode: ChartTimezoneMode, browserTimeZone: string, exchangeTimeZone: string): string {
  if (mode === "utc") return "UTC";
  if (mode === "exchange") return `Exchange (${exchangeTimeZone})`;
  return `Local (${browserTimeZone})`;
}

function browserOffsetLabel(): string {
  const offsetMinutes = -new Date().getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absMinutes = Math.abs(offsetMinutes);
  const hours = String(Math.floor(absMinutes / 60)).padStart(2, "0");
  const minutes = String(absMinutes % 60).padStart(2, "0");
  return `UTC${sign}${hours}:${minutes}`;
}

export function TradingChart({
  symbol = "BTC/USDT",
  venueType = "BINANCE",
  venueLabel,
  assetClass,
  liveEvent,
  appRealtimeConnected = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const historyPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const lastBarTimeRef = useRef<number>(0);
  const currentBarsRef = useRef<Bar[]>([]);

  const resolvedAssetClass = assetClass ?? inferAssetClassFromVenueType(venueType);
  const isCrypto = resolvedAssetClass === "crypto";
  const isBinanceVenue = venueType.toUpperCase() === "BINANCE";
  const continuousMarket = resolvedAssetClass === "crypto" || resolvedAssetClass === "prediction";

  const [ready, setReady] = useState(false);
  const [tf, setTf] = useState<TF>("1h");
  const [price, setPrice] = useState<number | null>(null);
  const [change, setChange] = useState<number | null>(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);
  const [dataSource, setDataSource] = useState("");
  const [feedSource, setFeedSource] = useState("");
  const [timeBasis, setTimeBasis] = useState("utc_epoch");
  const [exchangeTimeZone, setExchangeTimeZone] = useState("UTC");
  const [browserTimeZone, setBrowserTimeZone] = useState("UTC");
  const [timezoneMode, setTimezoneMode] = useState<ChartTimezoneMode>("local");
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [lastEventTs, setLastEventTs] = useState<number | null>(null);
  const [lastExchangeTs, setLastExchangeTs] = useState<number | null>(null);
  const [lastCandleTs, setLastCandleTs] = useState<number | null>(null);
  const [lastWsTickAt, setLastWsTickAt] = useState<number | null>(null);
  const [lastPollAt, setLastPollAt] = useState<number | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [feedTransport, setFeedTransport] = useState("rest");
  const [feedConnection, setFeedConnection] = useState("offline");
  const [debugOpen, setDebugOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [validation, setValidation] = useState<CandleValidation>(EMPTY_VALIDATION);

  const feedFreshness = describeFeedFreshness(lastUpdatedAt, nowMs);
  const updateAgeSec = secondsSince(lastUpdatedAt, nowMs);
  const expectsLiveFeed = live || dataSource === "live" || feedTransport === "websocket" || feedTransport === "polling";
  const freshnessLabel = expectsLiveFeed
    ? (feedFreshness === "stale" ? "LIVE DELAYED" : "LIVE")
    : dataSource === "cache" || dataSource === "stale_cache"
      ? "CACHED"
      : feedFreshness === "stale"
        ? "PUBLIC DELAYED"
        : "PUBLIC";
  const freshnessText = updateAgeSec == null
    ? "Awaiting updates"
    : feedFreshness === "stale"
      ? `Last update ${updateAgeSec}s ago`
      : `Updated ${updateAgeSec}s ago`;
  const feedColor = feedFreshness === "live" ? "#22c55e" : feedFreshness === "delayed" ? "#f59e0b" : "#ef4444";

  useEffect(() => {
    setBrowserTimeZone(getBrowserTimeZone());
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const syncValidation = (bars: Bar[]) => {
    setValidation(validateCandleSequence(bars, tf, Math.floor(Date.now() / 1000)));
  };

  const keepLatestVisible = () => {
    if (!chartRef.current) return;
    try {
      chartRef.current.timeScale().scrollToRealTime();
    } catch {}
  };

  const applyHistoryBars = (result: HistoryResponse, liveMode: boolean) => {
    const cleaned = dedupeAndSortBars(result.bars);
    currentBarsRef.current = cleaned;
    seriesRef.current?.setData(cleaned as any[]);
    chartRef.current?.timeScale().fitContent();
    keepLatestVisible();

    if (cleaned.length) {
      const first = cleaned[0].close;
      const last = cleaned[cleaned.length - 1].close;
      const lastTime = cleaned[cleaned.length - 1].time;
      lastBarTimeRef.current = lastTime;
      setPrice(last);
      setChange(first ? ((last - first) / first) * 100 : 0);
      setLastCandleTs(lastTime);
      setLastEventTs(result.asOf ?? lastTime);
      setLastExchangeTs(result.asOf ?? lastTime);
      setValidation(validateCandleSequence(cleaned, tf, Math.floor(Date.now() / 1000)));
    } else {
      lastBarTimeRef.current = 0;
      setLastCandleTs(null);
      setLastEventTs(null);
      setLastExchangeTs(null);
      setValidation(EMPTY_VALIDATION);
    }

    setFeedSource(result.source);
    setExchangeTimeZone(result.exchangeTimezone || "UTC");
    setTimeBasis(result.timeBasis || "utc_epoch");
    setLastUpdatedAt(Date.now());
    setLastPollAt(Date.now());
    setLive(liveMode);
    setLoading(false);
  };

  const applyRealtimeUpdate = (payload: {
    price: number;
    sourceTs?: number | null;
    exchangeTs?: number | null;
    candle?: Bar | null;
    transport: string;
    source: string;
    connection: string;
  }) => {
    if (!seriesRef.current || !lastBarTimeRef.current || !Number.isFinite(payload.price)) return;

    const merged = mergeRealtimeBar({
      bars: currentBarsRef.current,
      timeframe: tf,
      price: payload.price,
      sourceTs: payload.sourceTs,
      exchangeTs: payload.exchangeTs,
      candle: payload.candle,
    });

    if (!merged.updatedBar) return;

    currentBarsRef.current = merged.bars;
    lastBarTimeRef.current = merged.updatedBar.time;
    seriesRef.current.update(merged.updatedBar as any);
    keepLatestVisible();

    const eventTs = payload.sourceTs ?? null;
    const exchangeTs = payload.exchangeTs ?? null;
    const receivedAt = Date.now();
    setPrice(payload.price);
    setLastUpdatedAt(receivedAt);
    setLastCandleTs(merged.updatedBar.time);
    setLastEventTs(eventTs);
    setLastExchangeTs(exchangeTs);
    const latencySource = exchangeTs ?? eventTs;
    setLatencyMs(latencySource ? Math.max(0, receivedAt - latencySource * 1000) : null);
    setFeedTransport(payload.transport);
    setFeedConnection(payload.connection);
    setFeedSource(payload.source);
    setDataSource(
      payload.source === "agent" || payload.source === "venue"
        ? "live"
        : payload.source === "binance_ws"
          ? "public"
          : payload.source,
    );
    setLive(payload.source === "agent" || payload.source === "venue" || payload.source === "binance_ws");
    if (payload.transport === "websocket") {
      setLastWsTickAt(receivedAt);
    } else {
      setLastPollAt(receivedAt);
    }
    syncValidation(merged.bars);
  };

  useEffect(() => {
    if (!liveEvent) return;
    const liveSymbol = normaliseBinanceSymbol(liveEvent.symbol ?? "");
    const selectedSymbol = normaliseBinanceSymbol(symbol);
    if (!liveSymbol || liveSymbol !== selectedSymbol) return;
    if (typeof liveEvent.price !== "number" || !Number.isFinite(liveEvent.price)) return;

    const candle = liveEvent.timeframe === tf ? liveEvent.candle ?? null : null;
    applyRealtimeUpdate({
      price: liveEvent.price,
      sourceTs: liveEvent.ts ?? null,
      exchangeTs: liveEvent.exchangeTs ?? null,
      candle,
      transport: liveEvent.transport ?? "websocket",
      source: liveEvent.source ?? "agent",
      connection: appRealtimeConnected ? "connected" : "reconnecting",
    });
  }, [appRealtimeConnected, liveEvent, symbol, tf]);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let observer: ResizeObserver | null = null;
    let onOrient: (() => void) | null = null;

    import("lightweight-charts").then(({ createChart, CrosshairMode, CandlestickSeries }) => {
      if (disposed || !containerRef.current) return;
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 340,
        layout: {
          background: { color: "transparent" },
          textColor: "rgba(255,255,255,0.45)",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.03)" },
          horzLines: { color: "rgba(255,255,255,0.03)" },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: "rgba(255,255,255,0.05)" },
        timeScale: {
          borderColor: "rgba(255,255,255,0.05)",
          timeVisible: true,
          rightOffset: 6,
          shiftVisibleRangeOnNewBar: true,
          rightBarStaysOnScroll: true,
        },
      });
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#4ade80",
        downColor: "#f87171",
        wickUpColor: "#4ade80",
        wickDownColor: "#f87171",
        borderVisible: false,
      });

      chartRef.current = chart;
      seriesRef.current = series;
      setReady(true);

      const resizeChart = () => {
        if (!containerRef.current || !chartRef.current) return;
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
        keepLatestVisible();
      };

      observer = new ResizeObserver(resizeChart);
      observer.observe(containerRef.current);

      onOrient = () => {
        resizeChart();
        window.setTimeout(resizeChart, 320);
      };

      window.addEventListener("app:orientation-change", onOrient);
      window.addEventListener("orientationchange", onOrient);
      window.addEventListener("resize", onOrient);
    });

    return () => {
      disposed = true;
      observer?.disconnect();
      if (onOrient) {
        window.removeEventListener("app:orientation-change", onOrient);
        window.removeEventListener("orientationchange", onOrient);
        window.removeEventListener("resize", onOrient);
      }
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;

    const formatAxisTime = (time: unknown) => {
      const unixTs = toUnixSeconds(time);
      if (unixTs == null) return "";
      return formatTimestamp(unixTs, {
        mode: timezoneMode,
        browserTimeZone,
        exchangeTimeZone,
        includeDate: tf === "4h" || tf === "1d",
      });
    };

    const formatTooltipTime = (time: unknown) => {
      const unixTs = toUnixSeconds(time);
      if (unixTs == null) return "";
      return formatTimestamp(unixTs, {
        mode: timezoneMode,
        browserTimeZone,
        exchangeTimeZone,
        includeDate: true,
        withSeconds: true,
      });
    };

    chartRef.current.applyOptions({
      localization: {
        timeFormatter: formatTooltipTime,
      },
      timeScale: {
        tickMarkFormatter: formatAxisTime,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        shiftVisibleRangeOnNewBar: true,
        rightBarStaysOnScroll: true,
      },
    });
  }, [browserTimeZone, exchangeTimeZone, tf, timezoneMode]);

  useEffect(() => {
    if (!ready) return;

    wsRef.current?.close();
    if (historyPollRef.current) clearInterval(historyPollRef.current);
    if (reconnectTimerRef.current != null) window.clearTimeout(reconnectTimerRef.current);

    seriesRef.current?.setData([]);
    setLoading(true);
    setNoData(false);
    setLive(false);
    setPrice(null);
    setChange(null);
    setDataSource("");
    setFeedSource("");
    setTimeBasis("utc_epoch");
    setLastUpdatedAt(null);
    setLastEventTs(null);
    setLastExchangeTs(null);
    setLastCandleTs(null);
    setLastWsTickAt(null);
    setLastPollAt(null);
    setLatencyMs(null);
    setFeedTransport("rest");
    setFeedConnection("offline");
    setValidation(EMPTY_VALIDATION);
    lastBarTimeRef.current = 0;
    currentBarsRef.current = [];

    let cancelled = false;
    let pricePollId: ReturnType<typeof setInterval> | null = null;

    const loadFromBackend = async (): Promise<HistoryResponse> => {
      const url = `/api/agent/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}&limit=500&venue=${venueType.toLowerCase()}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return { bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null };
      const data = await res.json() as {
        candles?: Bar[];
        source?: string;
        time_basis?: string;
        exchange_timezone?: string;
        server_ts?: number;
      };
      return {
        bars: data.candles ?? [],
        source: data.source ?? "",
        timeBasis: data.time_basis ?? "utc_epoch",
        exchangeTimezone: data.exchange_timezone ?? "UTC",
        asOf: data.server_ts ?? null,
      };
    };

    const loadFromYahoo = async (): Promise<HistoryResponse> => {
      try {
        const res = await fetch(`/api/chart?symbol=${encodeURIComponent(symbol)}&interval=${tf}`, { cache: "no-store" });
        if (!res.ok) return { bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null };
        const data = await res.json() as {
          bars?: Bar[];
          source?: string;
          error?: string;
          time_basis?: string;
          exchange_timezone?: string;
          as_of?: number | null;
        };
        if (data.error || !data.bars?.length) {
          return { bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null };
        }
        return {
          bars: data.bars,
          source: data.source ?? "yahoo",
          timeBasis: data.time_basis ?? "utc_epoch",
          exchangeTimezone: data.exchange_timezone ?? "UTC",
          asOf: data.as_of ?? null,
        };
      } catch {
        return { bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null };
      }
    };

    const loadFromBinance = async (): Promise<HistoryResponse> => {
      const sym = normaliseBinanceSymbol(symbol);
      const url = `https://api.binance.com/api/v3/klines?symbol=${sym}&interval=${tf}&limit=500`;
      const res = await fetch(url, { cache: "no-store" });
      const data = await res.json();
      if (!Array.isArray(data)) {
        return { bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null };
      }
      const bars = data.map((row: any[]) => ({
        time: Math.floor(row[0] / 1000),
        open: parseFloat(row[1]),
        high: parseFloat(row[2]),
        low: parseFloat(row[3]),
        close: parseFloat(row[4]),
        volume: parseFloat(row[5]),
      }));
      return {
        bars,
        source: "binance_public",
        timeBasis: "utc_epoch",
        exchangeTimezone: "UTC",
        asOf: bars[bars.length - 1]?.time ?? null,
      };
    };

    const startBinanceLiveWS = (mode: "live" | "public" = "live", attempt = 0) => {
      if (cancelled) return;
      const sym = normaliseBinanceSymbol(symbol).toLowerCase();
      const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${sym}@kline_${tf}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setLive(true);
        setDataSource(mode);
        setFeedTransport("websocket");
        setFeedConnection("connected");
      };

      ws.onclose = () => {
        if (cancelled) return;
        setFeedConnection("reconnecting");
        setLive(false);
        const delay = Math.min(10_000, 1_000 * (attempt + 1));
        reconnectTimerRef.current = window.setTimeout(() => startBinanceLiveWS(mode, attempt + 1), delay);
      };

      ws.onmessage = (event: MessageEvent) => {
        if (cancelled || !seriesRef.current) return;
        const payload = JSON.parse(event.data as string) as { E?: number; k?: any };
        const kline = payload.k;
        if (!kline) return;
        applyRealtimeUpdate({
          price: parseFloat(kline.c),
          sourceTs: typeof payload.E === "number" ? Math.floor(payload.E / 1000) : Math.floor(Date.now() / 1000),
          exchangeTs: typeof payload.E === "number" ? Math.floor(payload.E / 1000) : null,
          candle: {
            time: Math.floor(kline.t / 1000),
            open: parseFloat(kline.o),
            high: parseFloat(kline.h),
            low: parseFloat(kline.l),
            close: parseFloat(kline.c),
            volume: parseFloat(kline.v),
          },
          transport: "websocket",
          source: "binance_ws",
          connection: "connected",
        });
      };
    };

    const startVenuePolling = (historyInterval = 20_000) => {
      const fastPricePoll = async () => {
        if (cancelled) return;
        try {
          let payload: PriceResponse | null = null;
          try {
            const liveRes = await fetch(
              `/api/price/live?symbol=${encodeURIComponent(symbol)}&venue=${venueType.toLowerCase()}`,
              { cache: "no-store" },
            );
            if (liveRes.ok) {
              const liveData = await liveRes.json() as PriceResponse;
              if (liveData.price && !liveData.error) payload = liveData;
            }
          } catch {}

          if (!payload) {
            const fallbackRes = await fetch(`/api/price?symbol=${encodeURIComponent(symbol)}`, { cache: "no-store" });
            if (!fallbackRes.ok) return;
            payload = await fallbackRes.json() as PriceResponse;
          }
          if (!payload || !payload.price || payload.error) return;

          setExchangeTimeZone(payload.exchange_timezone ?? exchangeTimeZone);
          setDataSource(payload.source === "agent" || payload.source === "venue" ? "live" : "public");
          setLive(payload.source === "agent" || payload.source === "venue");
          if (payload.changePct != null) setChange(payload.changePct);
          applyRealtimeUpdate({
            price: payload.price,
            sourceTs: typeof payload.ts === "number" ? payload.ts : Math.floor(Date.now() / 1000),
            exchangeTs: typeof payload.exchange_ts === "number" ? payload.exchange_ts : null,
            candle: lastBarTimeRef.current ? {
              time: alignToBucket(
                typeof payload.exchange_ts === "number"
                  ? payload.exchange_ts
                  : typeof payload.ts === "number"
                    ? payload.ts
                    : Math.floor(Date.now() / 1000),
                tf,
              ),
              open: currentBarsRef.current[currentBarsRef.current.length - 1]?.close ?? payload.price,
              high: Number(payload.high ?? payload.price),
              low: Number(payload.low ?? payload.price),
              close: payload.price,
            } : null,
            transport: payload.transport ?? "polling",
            source: payload.source ?? "venue",
            connection: "connected",
          });
        } catch {}
      };

      void fastPricePoll();
      pricePollId = setInterval(fastPricePoll, 3_000);

      historyPollRef.current = setInterval(async () => {
        if (cancelled) return;
        const backend = await loadFromBackend().catch(() => ({ bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null }));
        if (backend.bars.length) {
          applyHistoryBars(backend, backend.source === "agent" || backend.source === "venue");
          setDataSource(backend.source);
          return;
        }
        if (!isCrypto) {
          const freshBars = await loadFromYahoo().catch(() => ({ bars: [], source: "", timeBasis: "utc_epoch", exchangeTimezone: "UTC", asOf: null }));
          if (freshBars.bars.length) {
            applyHistoryBars(freshBars, false);
            setDataSource("public");
          }
        }
      }, historyInterval);
    };

    const load = async () => {
      try {
        const backend = await loadFromBackend();
        if (cancelled) return;
        if (backend.bars.length) {
          applyHistoryBars(backend, backend.source === "agent" || backend.source === "venue");
          setDataSource(backend.source);
          if (isCrypto && isBinanceVenue) startBinanceLiveWS(backend.source === "agent" || backend.source === "venue" ? "live" : "public");
          else startVenuePolling(10_000);
          return;
        }

        if (isCrypto) {
          const publicBars = await loadFromBinance();
          if (cancelled) return;
          if (publicBars.bars.length) {
            applyHistoryBars(publicBars, false);
            setDataSource("public");
            startBinanceLiveWS("public");
            return;
          }
        }

        const yahooBars = await loadFromYahoo();
        if (cancelled) return;
        if (yahooBars.bars.length) {
          applyHistoryBars(yahooBars, false);
          setDataSource("public");
          startVenuePolling(20_000);
          return;
        }

        setLoading(false);
        setNoData(true);
      } catch {
        if (!cancelled) {
          setLoading(false);
          setNoData(true);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      wsRef.current?.close();
      if (historyPollRef.current) clearInterval(historyPollRef.current);
      if (pricePollId) clearInterval(pricePollId);
      if (reconnectTimerRef.current != null) window.clearTimeout(reconnectTimerRef.current);
    };
  }, [ready, symbol, tf, venueType, isCrypto, isBinanceVenue]);

  const localNow = formatTimestamp(Math.floor(nowMs / 1000), {
    mode: "local",
    browserTimeZone,
    exchangeTimeZone,
    includeDate: true,
    withSeconds: true,
  });
  const lastCandleLabel = lastCandleTs
    ? formatTimestamp(lastCandleTs, {
        mode: timezoneMode,
        browserTimeZone,
        exchangeTimeZone,
        includeDate: true,
        withSeconds: true,
      })
    : "—";
  const lastEventLabel = lastEventTs
    ? formatTimestamp(lastEventTs, {
        mode: timezoneMode,
        browserTimeZone,
        exchangeTimeZone,
        includeDate: true,
        withSeconds: true,
      })
    : "—";
  const exchangeClockLabel = lastExchangeTs
    ? formatTimestamp(lastExchangeTs, {
        mode: "exchange",
        browserTimeZone,
        exchangeTimeZone,
        includeDate: true,
        withSeconds: true,
      })
    : "—";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 20, fontWeight: 600, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
              {price !== null ? formatPrice(price, resolvedAssetClass) : "—"}
            </span>
            {change !== null && (
              <span style={{ fontSize: 13, fontWeight: 500, color: change >= 0 ? "#4ade80" : "#f87171" }}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)}%
              </span>
            )}
          </div>

          {!loading && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, color: feedColor, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                <span style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: feedColor,
                  boxShadow: feedFreshness === "live" ? "0 0 0 0 rgba(34,197,94,0.6)" : undefined,
                  animation: feedFreshness === "live" ? "pulse-ring 1.4s ease-out infinite" : undefined,
                }} />
                {freshnessLabel}
              </span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>{freshnessText}</span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                {transportLabel(feedTransport, feedSource)} · {feedConnection}
              </span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                TZ: {timezoneLabel(timezoneMode, browserTimeZone, exchangeTimeZone)}
              </span>
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {TIMEFRAMES.map((value) => (
            <button
              key={value}
              onClick={() => setTf(value)}
              style={{
                padding: "4px 8px",
                borderRadius: 6,
                fontSize: 11,
                fontWeight: 500,
                cursor: "pointer",
                background: tf === value ? "rgba(255,255,255,0.1)" : "transparent",
                border: tf === value ? "1px solid rgba(255,255,255,0.15)" : "1px solid transparent",
                color: tf === value ? "#fff" : "var(--muted)",
              }}
            >
              {value}
            </button>
          ))}
          <select
            value={timezoneMode}
            onChange={(event) => setTimezoneMode(event.target.value as ChartTimezoneMode)}
            style={{
              padding: "4px 8px",
              borderRadius: 6,
              fontSize: 11,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.1)",
              color: "#fff",
            }}
          >
            <option value="local">Local</option>
            <option value="utc">UTC</option>
            <option value="exchange">Exchange</option>
          </select>
          <button
            onClick={() => setDebugOpen((open) => !open)}
            style={{
              padding: "4px 8px",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              background: debugOpen ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
              border: `1px solid ${debugOpen ? "rgba(74,222,128,0.25)" : "rgba(255,255,255,0.1)"}`,
              color: debugOpen ? "#4ade80" : "rgba(255,255,255,0.6)",
            }}
          >
            Debug
          </button>
        </div>
      </div>

      <div ref={containerRef} style={{ width: "100%", height: 340, position: "relative" }}>
        {debugOpen && (
          <div style={{
            position: "absolute",
            top: 10,
            right: 10,
            zIndex: 4,
            width: 280,
            maxWidth: "calc(100% - 20px)",
            padding: 12,
            borderRadius: 12,
            background: "rgba(10,15,24,0.88)",
            border: "1px solid rgba(255,255,255,0.08)",
            backdropFilter: "blur(12px)",
            display: "grid",
            gap: 6,
          }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#4ade80", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Chart Debug
            </div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.7)" }}>Local now: {localNow}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Browser TZ: {browserTimeZone} ({browserOffsetLabel()})</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Chart TZ: {timezoneLabel(timezoneMode, browserTimeZone, exchangeTimeZone)}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Timestamp basis: {timeBasis}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Latest candle: {lastCandleLabel}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Last tick event: {lastEventLabel}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Exchange clock: {exchangeClockLabel}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Transport: {transportLabel(feedTransport, feedSource)}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Connection: {feedConnection}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Updated: {freshnessText}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Latency: {latencyMs != null ? `${latencyMs} ms` : "n/a"}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Last WS tick: {lastWsTickAt ? `${secondsSince(lastWsTickAt, nowMs)}s ago` : "n/a"}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Last poll: {lastPollAt ? `${secondsSince(lastPollAt, nowMs)}s ago` : "n/a"}</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Interval: {tf} ({timeframeSeconds(tf)}s)</div>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>Validation: {validation.duplicates} dup · {validation.skippedIntervals} gap · {validation.misaligned} misaligned · {validation.futureBars} future</div>
            {!continuousMarket && validation.skippedIntervals > 0 && (
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.35)" }}>
                Session gaps can be normal on forex and stock markets outside trading hours.
              </div>
            )}
            {feedFreshness === "stale" && (
              <div style={{ fontSize: 10, color: "#fca5a5" }}>
                Delayed feed warning: no chart update has landed for more than 10 seconds.
              </div>
            )}
          </div>
        )}

        {loading && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <div style={{ width: 24, height: 24, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.1)", borderTopColor: "rgba(255,255,255,0.5)", animation: "spin 0.8s linear infinite" }} />
            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>Loading {symbol}…</span>
          </div>
        )}

        {!loading && noData && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 32, textAlign: "center" }}>
            <div style={{ fontSize: 32, lineHeight: 1 }}>
              {resolvedAssetClass === "forex" ? "💱" : resolvedAssetClass === "stocks" ? "📈" : "📊"}
            </div>
            <p style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
              {(venueLabel ?? venueType)} — {symbol}
            </p>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", lineHeight: 1.6, maxWidth: 280 }}>
              Could not load chart data for <strong style={{ color: "rgba(255,255,255,0.6)" }}>{symbol}</strong>.
              Check the symbol is correct for {venueLabel ?? venueType}.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
