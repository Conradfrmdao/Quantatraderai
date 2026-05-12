ALTER TABLE "Venue"
ADD COLUMN "market" TEXT;

UPDATE "Venue"
SET "market" = CASE
  WHEN "type" IN ('HYPERLIQUID', 'BYBIT') THEN 'futures'
  WHEN "type" IN ('OANDA', 'METATRADER') THEN 'forex'
  WHEN "type" IN ('ALPACA', 'IBKR') THEN 'stocks'
  WHEN "type" = 'POLYMARKET' THEN 'prediction'
  ELSE 'spot'
END
WHERE "market" IS NULL;

ALTER TABLE "Venue"
ALTER COLUMN "market" SET DEFAULT 'spot';

ALTER TABLE "Venue"
ALTER COLUMN "market" SET NOT NULL;

ALTER TABLE "AgentRun"
ALTER COLUMN "market" SET DEFAULT 'spot';
