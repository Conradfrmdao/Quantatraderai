CREATE TABLE IF NOT EXISTS "Position" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "assetClass" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "mode" TEXT NOT NULL DEFAULT 'paper',
    "symbol" TEXT NOT NULL,
    "side" TEXT NOT NULL,
    "quantity" DOUBLE PRECISION NOT NULL,
    "entryPrice" DOUBLE PRECISION NOT NULL,
    "currentPrice" DOUBLE PRECISION NOT NULL,
    "realizedPnl" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "unrealizedPnl" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "leverage" DOUBLE PRECISION,
    "liquidationPrice" DOUBLE PRECISION,
    "source" TEXT NOT NULL,
    "externalPositionId" TEXT,
    "traceId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'open',
    "openedAt" TIMESTAMP(3),
    "closedAt" TIMESTAMP(3),
    "lastSyncedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Position_pkey" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "TradeReceipt" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "positionKey" TEXT,
    "tradeId" TEXT NOT NULL,
    "traceId" TEXT NOT NULL,
    "venue" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "mode" TEXT NOT NULL DEFAULT 'paper',
    "quantity" DOUBLE PRECISION NOT NULL,
    "price" DOUBLE PRECISION NOT NULL,
    "allocationUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "pnl" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "riskSummary" TEXT NOT NULL,
    "receiptHash" TEXT NOT NULL,
    "receiptJson" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TradeReceipt_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Position_userId_venue_symbol_market_mode_key"
ON "Position"("userId", "venue", "symbol", "market", "mode");

CREATE INDEX IF NOT EXISTS "Position_userId_status_updatedAt_idx"
ON "Position"("userId", "status", "updatedAt");

CREATE INDEX IF NOT EXISTS "Position_userId_venue_market_mode_idx"
ON "Position"("userId", "venue", "market", "mode");

CREATE INDEX IF NOT EXISTS "Position_traceId_idx"
ON "Position"("traceId");

CREATE UNIQUE INDEX IF NOT EXISTS "TradeReceipt_tradeId_key"
ON "TradeReceipt"("tradeId");

CREATE INDEX IF NOT EXISTS "TradeReceipt_userId_createdAt_idx"
ON "TradeReceipt"("userId", "createdAt");

CREATE INDEX IF NOT EXISTS "TradeReceipt_userId_symbol_createdAt_idx"
ON "TradeReceipt"("userId", "symbol", "createdAt");

CREATE INDEX IF NOT EXISTS "TradeReceipt_traceId_idx"
ON "TradeReceipt"("traceId");

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'Position_userId_fkey'
    ) THEN
        ALTER TABLE "Position"
        ADD CONSTRAINT "Position_userId_fkey"
        FOREIGN KEY ("userId") REFERENCES "User"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'TradeReceipt_userId_fkey'
    ) THEN
        ALTER TABLE "TradeReceipt"
        ADD CONSTRAINT "TradeReceipt_userId_fkey"
        FOREIGN KEY ("userId") REFERENCES "User"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;
