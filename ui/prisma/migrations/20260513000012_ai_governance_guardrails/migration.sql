-- AI governance persistence: usage logs, decisions, and council votes

CREATE TABLE "AIUsageLog" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "agentRunId" TEXT,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "totalTokens" INTEGER NOT NULL DEFAULT 0,
    "estimatedCostUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "traceId" TEXT NOT NULL,
    "mode" TEXT NOT NULL DEFAULT 'paper',
    "venue" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AIUsageLog_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "AIDecision" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "agentRunId" TEXT,
    "venueId" TEXT,
    "traceId" TEXT NOT NULL,
    "mode" TEXT NOT NULL DEFAULT 'paper',
    "persona" TEXT,
    "symbol" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "finalAction" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "reasoningSummary" TEXT NOT NULL,
    "riskDecision" TEXT NOT NULL DEFAULT 'hold',
    "isCouncil" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AIDecision_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "AICouncilVote" (
    "id" TEXT NOT NULL,
    "decisionId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "voteAction" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "reasoningSummary" TEXT NOT NULL,
    "latencyMs" INTEGER NOT NULL DEFAULT 0,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "totalTokens" INTEGER NOT NULL DEFAULT 0,
    "estimatedCostUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "traceId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AICouncilVote_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "RuntimeCounter" (
    "id" TEXT NOT NULL,
    "value" INTEGER NOT NULL DEFAULT 0,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RuntimeCounter_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "AIUsageLog_userId_createdAt_idx" ON "AIUsageLog"("userId", "createdAt");
CREATE INDEX "AIUsageLog_userId_action_createdAt_idx" ON "AIUsageLog"("userId", "action", "createdAt");
CREATE INDEX "AIUsageLog_traceId_idx" ON "AIUsageLog"("traceId");

CREATE INDEX "AIDecision_userId_createdAt_idx" ON "AIDecision"("userId", "createdAt");
CREATE INDEX "AIDecision_userId_symbol_createdAt_idx" ON "AIDecision"("userId", "symbol", "createdAt");
CREATE INDEX "AIDecision_traceId_idx" ON "AIDecision"("traceId");

CREATE INDEX "AICouncilVote_decisionId_createdAt_idx" ON "AICouncilVote"("decisionId", "createdAt");
CREATE INDEX "AICouncilVote_userId_createdAt_idx" ON "AICouncilVote"("userId", "createdAt");
CREATE INDEX "AICouncilVote_traceId_idx" ON "AICouncilVote"("traceId");
CREATE INDEX "RuntimeCounter_expiresAt_idx" ON "RuntimeCounter"("expiresAt");

ALTER TABLE "AIUsageLog"
    ADD CONSTRAINT "AIUsageLog_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "AIUsageLog"
    ADD CONSTRAINT "AIUsageLog_agentRunId_fkey"
    FOREIGN KEY ("agentRunId") REFERENCES "AgentRun"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "AIDecision"
    ADD CONSTRAINT "AIDecision_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "AIDecision"
    ADD CONSTRAINT "AIDecision_agentRunId_fkey"
    FOREIGN KEY ("agentRunId") REFERENCES "AgentRun"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "AIDecision"
    ADD CONSTRAINT "AIDecision_venueId_fkey"
    FOREIGN KEY ("venueId") REFERENCES "Venue"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "AICouncilVote"
    ADD CONSTRAINT "AICouncilVote_decisionId_fkey"
    FOREIGN KEY ("decisionId") REFERENCES "AIDecision"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "AICouncilVote"
    ADD CONSTRAINT "AICouncilVote_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
