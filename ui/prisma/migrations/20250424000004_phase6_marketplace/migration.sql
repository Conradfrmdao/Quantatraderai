-- Phase 6: StrategyListing for marketplace + leaderboard
-- Run with: cd ui && pnpm prisma migrate deploy

CREATE TABLE IF NOT EXISTS "StrategyListing" (
    "id"          TEXT             NOT NULL,
    "userId"      TEXT             NOT NULL,
    "name"        TEXT             NOT NULL,
    "description" TEXT,
    "config"      TEXT             NOT NULL DEFAULT '{}',
    "sharpe"      DOUBLE PRECISION NOT NULL DEFAULT 0,
    "totalReturn" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "maxDrawdown" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "isPublic"    BOOLEAN          NOT NULL DEFAULT false,
    "price"       DOUBLE PRECISION NOT NULL DEFAULT 0,
    "createdAt"   TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt"   TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "StrategyListing_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "StrategyListing_public_sharpe_idx" ON "StrategyListing"("isPublic", "sharpe" DESC);

ALTER TABLE "StrategyListing"
    ADD CONSTRAINT "StrategyListing_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
