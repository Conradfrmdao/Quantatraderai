-- Phase 10: Stripe billing — Plan enum + User billing fields
-- Run with: cd ui && pnpm prisma migrate deploy

-- Plan enum
DO $$ BEGIN
  CREATE TYPE "Plan" AS ENUM ('FREE','STARTER','PRO','ENTERPRISE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Add billing columns to User
ALTER TABLE "User"
    ADD COLUMN IF NOT EXISTS "plan"             "Plan"       NOT NULL DEFAULT 'FREE',
    ADD COLUMN IF NOT EXISTS "stripeCustomerId" TEXT,
    ADD COLUMN IF NOT EXISTS "stripeSubId"      TEXT,
    ADD COLUMN IF NOT EXISTS "planExpiresAt"    TIMESTAMP(3);

CREATE INDEX IF NOT EXISTS "User_plan_idx" ON "User"("plan");
