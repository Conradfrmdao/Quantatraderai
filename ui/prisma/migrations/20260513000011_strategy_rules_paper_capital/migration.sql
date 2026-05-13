ALTER TABLE "Venue"
ADD COLUMN "paperCapital" DOUBLE PRECISION NOT NULL DEFAULT 10000;

CREATE TABLE "StrategyRule" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "text" TEXT NOT NULL,
    "symbol" TEXT,
    "action" TEXT NOT NULL,
    "condition" TEXT NOT NULL,
    "indicator" TEXT NOT NULL,
    "operator" TEXT NOT NULL,
    "threshold" DOUBLE PRECISION NOT NULL,
    "allocationPct" DOUBLE PRECISION NOT NULL DEFAULT 3,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "StrategyRule_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "StrategyRule_userId_isActive_idx" ON "StrategyRule"("userId", "isActive");
CREATE INDEX "StrategyRule_userId_createdAt_idx" ON "StrategyRule"("userId", "createdAt");

ALTER TABLE "StrategyRule"
ADD CONSTRAINT "StrategyRule_userId_fkey"
FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
