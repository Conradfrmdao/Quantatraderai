import { describe, expect, it } from "vitest";

import {
  alignToBucket,
  describeFeedFreshness,
  formatTimestamp,
  mergeRealtimeBar,
  resolveDisplayTimezone,
  validateCandleSequence,
} from "@/lib/chart-sync";

describe("chart-sync timezones", () => {
  it("defaults local rendering to the browser timezone", () => {
    const baseTs = Math.floor(Date.UTC(2025, 4, 10, 18, 43, 0) / 1000);
    const formatted = formatTimestamp(baseTs, {
      mode: "local",
      browserTimeZone: "Africa/Kampala",
      exchangeTimeZone: "UTC",
    });
    expect(formatted).toContain("09:43");
    expect(formatted).toContain("PM");
  });

  it("supports explicit UTC and exchange timezone formatting", () => {
    expect(resolveDisplayTimezone("utc", "Africa/Kampala", "America/New_York")).toBe("UTC");
    expect(resolveDisplayTimezone("exchange", "Africa/Kampala", "America/New_York")).toBe("America/New_York");

    const baseTs = Math.floor(Date.UTC(2025, 4, 10, 18, 43, 0) / 1000);
    const utc = formatTimestamp(baseTs, {
      mode: "utc",
      browserTimeZone: "Africa/Kampala",
      exchangeTimeZone: "America/New_York",
    });
    const exchange = formatTimestamp(baseTs, {
      mode: "exchange",
      browserTimeZone: "Africa/Kampala",
      exchangeTimeZone: "America/New_York",
    });
    expect(utc).toContain("06:43");
    expect(exchange).toContain("02:43");
  });
});

describe("chart-sync freshness", () => {
  it("marks feeds stale after ten seconds", () => {
    const nowMs = 100_000;
    expect(describeFeedFreshness(nowMs - 2_000, nowMs)).toBe("live");
    expect(describeFeedFreshness(nowMs - 6_000, nowMs)).toBe("delayed");
    expect(describeFeedFreshness(nowMs - 12_000, nowMs)).toBe("stale");
  });
});

describe("chart-sync candles", () => {
  it("aligns timestamps to timeframe buckets", () => {
    expect(alignToBucket(1_715_727_703, "1m")).toBe(1_715_727_660);
    expect(alignToBucket(1_715_727_703, "5m")).toBe(1_715_727_600);
  });

  it("detects duplicate, skipped, misaligned, and future bars", () => {
    const validation = validateCandleSequence([
      { time: 60, open: 1, high: 1, low: 1, close: 1 },
      { time: 120, open: 1, high: 1, low: 1, close: 1 },
      { time: 120, open: 1, high: 1, low: 1, close: 1 },
      { time: 250, open: 1, high: 1, low: 1, close: 1 },
      { time: 420, open: 1, high: 1, low: 1, close: 1 },
      { time: 1_000, open: 1, high: 1, low: 1, close: 1 },
    ], "1m", 500);

    expect(validation.duplicates).toBeGreaterThan(0);
    expect(validation.misaligned).toBeGreaterThan(0);
    expect(validation.skippedIntervals).toBeGreaterThan(0);
    expect(validation.futureBars).toBeGreaterThan(0);
  });

  it("merges realtime updates into the active 1m candle", () => {
    const bars = [
      { time: 1_715_727_660, open: 100, high: 102, low: 99, close: 101 },
      { time: 1_715_727_720, open: 101, high: 103, low: 100, close: 102 },
    ];

    const first = mergeRealtimeBar({
      bars,
      timeframe: "1m",
      price: 104,
      sourceTs: 1_715_727_759,
    });

    expect(first.updatedBar?.time).toBe(1_715_727_720);
    expect(first.updatedBar?.close).toBe(104);
    expect(first.updatedBar?.high).toBe(104);

    const second = mergeRealtimeBar({
      bars: first.bars,
      timeframe: "1m",
      price: 105,
      sourceTs: 1_715_727_780,
    });

    expect(second.updatedBar?.time).toBe(1_715_727_780);
    expect(second.bars).toHaveLength(3);
    expect(second.updatedBar?.open).toBe(104);
  });
});
