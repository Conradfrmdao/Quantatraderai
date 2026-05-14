export type ChartTimezoneMode = "local" | "utc" | "exchange";
export type FeedFreshness = "live" | "delayed" | "stale";

export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface CandleValidation {
  duplicates: number;
  skippedIntervals: number;
  misaligned: number;
  futureBars: number;
  latestBarAgeSec: number | null;
}

export interface RealtimeBarMergeInput {
  bars: Bar[];
  timeframe: string;
  price: number;
  sourceTs?: number | null;
  exchangeTs?: number | null;
  candle?: Partial<Bar> | null;
}

export const TIMEFRAME_SECONDS: Record<string, number> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "30m": 1800,
  "1h": 3600,
  "4h": 14400,
  "1d": 86400,
};

export function timeframeSeconds(timeframe: string): number {
  return TIMEFRAME_SECONDS[String(timeframe || "1h").toLowerCase()] ?? 3600;
}

export function alignToBucket(unixTs: number, timeframe: string): number {
  const interval = timeframeSeconds(timeframe);
  return Math.floor(unixTs / interval) * interval;
}

export function toUnixSeconds(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (!value || typeof value !== "object") return null;
  const maybeBusinessDay = value as { year?: number; month?: number; day?: number };
  if (
    typeof maybeBusinessDay.year === "number" &&
    typeof maybeBusinessDay.month === "number" &&
    typeof maybeBusinessDay.day === "number"
  ) {
    return Math.floor(Date.UTC(maybeBusinessDay.year, maybeBusinessDay.month - 1, maybeBusinessDay.day) / 1000);
  }
  return null;
}

export function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function resolveDisplayTimezone(
  mode: ChartTimezoneMode,
  browserTimeZone: string,
  exchangeTimeZone?: string | null,
): string {
  if (mode === "utc") return "UTC";
  if (mode === "exchange") return exchangeTimeZone || "UTC";
  return browserTimeZone || "UTC";
}

function buildFormatter(timeZone: string, includeDate: boolean, withSeconds: boolean): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    month: includeDate ? "short" : undefined,
    day: includeDate ? "2-digit" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined,
    hour12: true,
  });
}

export function formatTimestamp(
  unixTs: number,
  options?: {
    mode?: ChartTimezoneMode;
    browserTimeZone?: string;
    exchangeTimeZone?: string | null;
    includeDate?: boolean;
    withSeconds?: boolean;
  },
): string {
  const mode = options?.mode ?? "local";
  const browserTimeZone = options?.browserTimeZone ?? "UTC";
  const exchangeTimeZone = options?.exchangeTimeZone ?? "UTC";
  const timeZone = resolveDisplayTimezone(mode, browserTimeZone, exchangeTimeZone);
  const includeDate = options?.includeDate ?? false;
  const withSeconds = options?.withSeconds ?? false;
  try {
    return buildFormatter(timeZone, includeDate, withSeconds).format(new Date(unixTs * 1000));
  } catch {
    return new Date(unixTs * 1000).toISOString();
  }
}

export function secondsSince(timestampMs: number | null, nowMs = Date.now()): number | null {
  if (!timestampMs || !Number.isFinite(timestampMs)) return null;
  return Math.max(0, Math.floor((nowMs - timestampMs) / 1000));
}

export function describeFeedFreshness(
  lastUpdateAt: number | null,
  nowMs = Date.now(),
  delayedAfterMs = 3_000,
  staleAfterMs = 10_000,
): FeedFreshness {
  if (!lastUpdateAt) return "stale";
  const ageMs = Math.max(0, nowMs - lastUpdateAt);
  if (ageMs > staleAfterMs) return "stale";
  if (ageMs > delayedAfterMs) return "delayed";
  return "live";
}

export function dedupeAndSortBars(bars: Bar[]): Bar[] {
  const byTime = new Map<number, Bar>();
  for (const bar of bars) {
    if (!bar || !Number.isFinite(bar.time)) continue;
    byTime.set(Number(bar.time), { ...bar, time: Number(bar.time) });
  }
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

export function validateCandleSequence(
  bars: Bar[],
  timeframe: string,
  nowTs = Math.floor(Date.now() / 1000),
): CandleValidation {
  const interval = timeframeSeconds(timeframe);
  const sorted = [...bars]
    .filter((bar) => bar && Number.isFinite(bar.time))
    .sort((a, b) => a.time - b.time);

  let duplicates = 0;
  let skippedIntervals = 0;
  let misaligned = 0;
  let futureBars = 0;

  for (let i = 0; i < sorted.length; i += 1) {
    const current = sorted[i];
    if (current.time % interval !== 0) misaligned += 1;
    if (current.time > nowTs + 5) futureBars += 1;
    if (i > 0) {
      const prev = sorted[i - 1];
      const diff = current.time - prev.time;
      if (diff <= 0) {
        duplicates += 1;
      } else if (diff > interval) {
        skippedIntervals += Math.max(0, Math.round(diff / interval) - 1);
      }
    }
  }

  const unique = dedupeAndSortBars(bars);
  duplicates += Math.max(0, bars.length - unique.length);

  return {
    duplicates,
    skippedIntervals,
    misaligned,
    futureBars,
    latestBarAgeSec: unique.length ? Math.max(0, nowTs - unique[unique.length - 1].time) : null,
  };
}

export function mergeRealtimeBar({ bars, timeframe, price, sourceTs, exchangeTs, candle }: RealtimeBarMergeInput): {
  bars: Bar[];
  updatedBar: Bar | null;
} {
  const currentBars = dedupeAndSortBars(bars);
  if (!currentBars.length || !Number.isFinite(price)) {
    return { bars: currentBars, updatedBar: null };
  }

  const previous = currentBars[currentBars.length - 1];
  const fallbackTs = alignToBucket(
    Math.floor((exchangeTs ?? sourceTs ?? Math.floor(Date.now() / 1000))),
    timeframe,
  );
  const nextTime =
    candle && typeof candle.time === "number" && Number.isFinite(candle.time)
      ? candle.time
      : fallbackTs;

  if (nextTime < previous.time) {
    return { bars: currentBars, updatedBar: null };
  }

  const candleClose = Number(candle?.close ?? price);
  const candleOpen = Number(candle?.open ?? (nextTime > previous.time ? previous.close : previous.open));
  const candleHigh = Number(candle?.high ?? Math.max(nextTime > previous.time ? previous.close : previous.high, candleClose));
  const candleLow = Number(candle?.low ?? Math.min(nextTime > previous.time ? previous.close : previous.low, candleClose));
  const candleVolume = candle?.volume != null && Number.isFinite(Number(candle.volume))
    ? Number(candle.volume)
    : (nextTime > previous.time ? 0 : previous.volume ?? 0);

  const nextBar: Bar = nextTime > previous.time
    ? {
        time: nextTime,
        open: candleOpen,
        high: candleHigh,
        low: candleLow,
        close: candleClose,
        volume: candleVolume,
      }
    : {
        ...previous,
        time: previous.time,
        open: candleOpen,
        high: candleHigh,
        low: candleLow,
        close: candleClose,
        volume: candleVolume,
      };

  const mergedBars = nextTime > previous.time
    ? [...currentBars, nextBar].slice(-500)
    : [...currentBars.slice(0, -1), nextBar];

  return { bars: mergedBars, updatedBar: nextBar };
}
