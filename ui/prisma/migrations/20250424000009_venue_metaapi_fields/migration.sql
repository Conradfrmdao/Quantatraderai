-- Venue: MetaAPI token + per-venue webhook secret
ALTER TABLE "Venue"
    ADD COLUMN IF NOT EXISTS "metaApiToken"     TEXT,
    ADD COLUMN IF NOT EXISTS "metaApiAccountId" TEXT,
    ADD COLUMN IF NOT EXISTS "webhookSecret"    TEXT;
