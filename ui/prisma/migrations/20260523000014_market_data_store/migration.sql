CREATE TABLE IF NOT EXISTS "MarketCandle" (
    "id" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "assetClass" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
    "timestamp" TIMESTAMPTZ(3) NOT NULL,
    "open" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" DOUBLE PRECISION NOT NULL,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "MarketCandle_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "MarketDataBackfillJob" (
    "id" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "assetClass" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
    "startDate" TIMESTAMPTZ(3) NOT NULL,
    "endDate" TIMESTAMPTZ(3) NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "lastFetchedAt" TIMESTAMPTZ(3),
    "errorMessage" TEXT,
    "source" TEXT,
    "isLiveSync" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "MarketDataBackfillJob_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "MarketIndicatorSnapshot" (
    "id" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "assetClass" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
    "timestamp" TIMESTAMPTZ(3) NOT NULL,
    "indicatorsJson" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "MarketIndicatorSnapshot_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "MarketCandle_venue_symbol_timeframe_timestamp_key"
    ON "MarketCandle"("venue", "symbol", "timeframe", "timestamp");

CREATE INDEX IF NOT EXISTS "MarketCandle_venue_symbol_timeframe_timestamp_idx"
    ON "MarketCandle"("venue", "symbol", "timeframe", "timestamp");

CREATE INDEX IF NOT EXISTS "MarketCandle_assetClass_symbol_timeframe_timestamp_idx"
    ON "MarketCandle"("assetClass", "symbol", "timeframe", "timestamp");

CREATE UNIQUE INDEX IF NOT EXISTS "MarketDataBackfillJob_venue_symbol_timeframe_key"
    ON "MarketDataBackfillJob"("venue", "symbol", "timeframe");

CREATE INDEX IF NOT EXISTS "MarketDataBackfillJob_venue_symbol_timeframe_status_idx"
    ON "MarketDataBackfillJob"("venue", "symbol", "timeframe", "status");

CREATE UNIQUE INDEX IF NOT EXISTS "MarketIndicatorSnapshot_venue_symbol_timeframe_timestamp_key"
    ON "MarketIndicatorSnapshot"("venue", "symbol", "timeframe", "timestamp");

CREATE INDEX IF NOT EXISTS "MarketIndicatorSnapshot_venue_symbol_timeframe_timestamp_idx"
    ON "MarketIndicatorSnapshot"("venue", "symbol", "timeframe", "timestamp");
