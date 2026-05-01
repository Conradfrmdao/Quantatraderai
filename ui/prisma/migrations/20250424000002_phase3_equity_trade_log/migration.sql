-- Phase 3: EquityPoint (tick-by-tick equity history) + TradeLog (persistent diary)
-- Run with: cd ui && pnpm prisma migrate deploy

CREATE TABLE IF NOT EXISTS "EquityPoint" (
    "id"        TEXT          NOT NULL,
    "userId"    TEXT          NOT NULL,
    "equity"    DOUBLE PRECISION NOT NULL,
    "balance"   DOUBLE PRECISION NOT NULL,
    "pnl"       DOUBLE PRECISION NOT NULL DEFAULT 0,
    "tickCount" INTEGER       NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "EquityPoint_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "EquityPoint_userId_createdAt_idx" ON "EquityPoint"("userId", "createdAt");

ALTER TABLE "EquityPoint"
    ADD CONSTRAINT "EquityPoint_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;


CREATE TABLE IF NOT EXISTS "TradeLog" (
    "id"            TEXT             NOT NULL,
    "userId"        TEXT             NOT NULL,
    "symbol"        TEXT             NOT NULL,
    "action"        TEXT             NOT NULL,
    "quantity"      DOUBLE PRECISION NOT NULL,
    "price"         DOUBLE PRECISION NOT NULL,
    "allocationUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "pnl"           DOUBLE PRECISION NOT NULL DEFAULT 0,
    "source"        TEXT             NOT NULL DEFAULT 'agent',
    "rationale"     TEXT,
    "tpPrice"       DOUBLE PRECISION,
    "slPrice"       DOUBLE PRECISION,
    "createdAt"     TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "TradeLog_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "TradeLog_userId_createdAt_idx" ON "TradeLog"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "TradeLog_userId_symbol_idx"    ON "TradeLog"("userId", "symbol");

ALTER TABLE "TradeLog"
    ADD CONSTRAINT "TradeLog_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
