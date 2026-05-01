-- Phase 9: CopyRelationship for copy trading
-- Run with: cd ui && pnpm prisma migrate deploy

CREATE TABLE IF NOT EXISTS "CopyRelationship" (
    "id"          TEXT             NOT NULL,
    "leaderId"    TEXT             NOT NULL,
    "followerId"  TEXT             NOT NULL,
    "maxAllocPct" DOUBLE PRECISION NOT NULL DEFAULT 3.0,
    "isActive"    BOOLEAN          NOT NULL DEFAULT true,
    "createdAt"   TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "CopyRelationship_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "CopyRelationship_unique" UNIQUE ("leaderId","followerId")
);

CREATE INDEX IF NOT EXISTS "CopyRelationship_leaderId_active_idx" ON "CopyRelationship"("leaderId","isActive");

ALTER TABLE "CopyRelationship"
    ADD CONSTRAINT "CopyRelationship_leaderId_fkey"
    FOREIGN KEY ("leaderId") REFERENCES "User"("id") ON DELETE CASCADE;

ALTER TABLE "CopyRelationship"
    ADD CONSTRAINT "CopyRelationship_followerId_fkey"
    FOREIGN KEY ("followerId") REFERENCES "User"("id") ON DELETE CASCADE;
