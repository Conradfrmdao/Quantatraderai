-- Phase 1: Add AgentRun table + new VenueType values
-- Run with: cd ui && pnpm prisma migrate deploy

-- Add new venue type enum values (PostgreSQL does not support removing values)
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'METATRADER';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'BYBIT';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'OKX';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'KRAKEN';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'COINBASE';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'ALPACA';
ALTER TYPE "VenueType" ADD VALUE IF NOT EXISTS 'IBKR';

-- AgentRun: one persistent record per user tracking agent state across restarts
CREATE TABLE IF NOT EXISTS "AgentRun" (
    "id"        TEXT          NOT NULL,
    "userId"    TEXT          NOT NULL,
    "symbols"   TEXT[]        NOT NULL DEFAULT '{}',
    "timeframe" TEXT          NOT NULL DEFAULT '1h',
    "isPaper"   BOOLEAN       NOT NULL DEFAULT true,
    "market"    TEXT          NOT NULL DEFAULT 'futures',
    "isRunning" BOOLEAN       NOT NULL DEFAULT true,
    "startedAt" TIMESTAMP(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "stoppedAt" TIMESTAMP(3),
    CONSTRAINT "AgentRun_pkey" PRIMARY KEY ("id")
);

-- One active run per user (upsert-friendly)
CREATE UNIQUE INDEX IF NOT EXISTS "AgentRun_userId_key" ON "AgentRun"("userId");
CREATE INDEX        IF NOT EXISTS "AgentRun_isRunning_idx" ON "AgentRun"("isRunning");

-- Foreign key to User
ALTER TABLE "AgentRun"
    ADD CONSTRAINT "AgentRun_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
