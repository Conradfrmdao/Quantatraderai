-- Phase 4: pgvector + DecisionEmbedding for RAG memory
-- Prerequisites: run this in Supabase SQL editor first:
--   CREATE EXTENSION IF NOT EXISTS vector;
-- Then deploy: cd ui && pnpm prisma migrate deploy

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS "DecisionEmbedding" (
    "id"             TEXT             NOT NULL,
    "userId"         TEXT             NOT NULL,
    "asset"          TEXT             NOT NULL,
    "action"         TEXT             NOT NULL,
    "contextSummary" TEXT             NOT NULL DEFAULT '',
    "rationale"      TEXT             NOT NULL DEFAULT '',
    "embedding"      vector(1536),
    "qualityScore"   DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "pnl"            DOUBLE PRECISION,
    "createdAt"      TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DecisionEmbedding_pkey" PRIMARY KEY ("id")
);

CREATE INDEX IF NOT EXISTS "DecisionEmbedding_userId_idx" ON "DecisionEmbedding"("userId");
CREATE INDEX IF NOT EXISTS "DecisionEmbedding_asset_idx"  ON "DecisionEmbedding"("asset");

-- IVFFlat ANN index — adjust lists based on row count (sqrt(rows) is a good start)
CREATE INDEX IF NOT EXISTS "DecisionEmbedding_embedding_idx"
    ON "DecisionEmbedding" USING ivfflat ("embedding" vector_cosine_ops) WITH (lists = 100);

ALTER TABLE "DecisionEmbedding"
    ADD CONSTRAINT "DecisionEmbedding_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
