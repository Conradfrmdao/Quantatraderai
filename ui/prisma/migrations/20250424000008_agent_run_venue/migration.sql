-- Add venue column to AgentRun so auto-resume picks the right venue adapter
ALTER TABLE "AgentRun" ADD COLUMN IF NOT EXISTS "venue" TEXT NOT NULL DEFAULT 'binance';
