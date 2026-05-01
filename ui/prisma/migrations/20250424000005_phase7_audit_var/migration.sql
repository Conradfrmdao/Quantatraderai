-- Phase 7: AuditLog (immutable append-only) + StrategyListing
-- Run with: cd ui && pnpm prisma migrate deploy

CREATE TABLE IF NOT EXISTS "AuditLog" (
    "id"        TEXT         NOT NULL,
    "userId"    TEXT         NOT NULL,
    "event"     TEXT         NOT NULL,
    "symbol"    TEXT,
    "action"    TEXT,
    "data"      TEXT         NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "AuditLog_userId_createdAt_idx" ON "AuditLog"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "AuditLog_event_idx"            ON "AuditLog"("event");

ALTER TABLE "AuditLog"
    ADD CONSTRAINT "AuditLog_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

-- Immutability: revoke DELETE/UPDATE from the application role
-- Replace 'your_app_role' with your actual Supabase/Postgres role name.
-- REVOKE DELETE, UPDATE ON "AuditLog" FROM your_app_role;
-- (Uncomment and customise once you know the role name.)
