export interface CouncilOpinionSummary {
  role?: string;
  provider: string;
  action: string;
  confidence: number;
  rationale: string;
  veto?: boolean;
}

export interface TradeDecisionSummary {
  asset: string;
  action: string;
  rationale?: string;
  allocation_usd?: number;
  tp_price?: number;
  sl_price?: number;
  confidence?: number;
  deadlock?: boolean;
  correlation_warning?: string;
  council?: CouncilOpinionSummary[];
}

export interface DecisionSummary {
  ts?: string;
  trace_id?: string;
  reasoning_summary?: string;
  trade_decisions?: TradeDecisionSummary[];
  council?: {
    asset: string;
    opinions: CouncilOpinionSummary[];
    vote: string;
    confidence: number;
    deadlock: boolean;
  }[];
}

export interface FlattenedDecisionSummary extends TradeDecisionSummary {
  ts?: string;
  trace_id?: string;
}

function normalizeAsset(asset?: string) {
  return String(asset ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function humanizeDecisionRationale(rationale?: string) {
  const text = String(rationale ?? "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (
    lower === "tool loop cap" ||
    lower.includes("indicator analysis exceeded the tool limit")
  ) {
    return "The model could not complete a safe analysis on this tick, so no trade was executed.";
  }
  if (lower === "parse error" || lower === "ai_output_invalid") {
    return "The model response could not be parsed cleanly, so no trade was placed on this tick.";
  }
  if (lower === "ai_final_response_invalid") {
    return "The final AI response was not valid trading JSON, so no trade was executed.";
  }
  return text;
}

export function flattenDecisionsNewestFirst(
  decisions: DecisionSummary[],
  limit = 12,
): FlattenedDecisionSummary[] {
  return decisions
    .flatMap((decision) =>
      (decision.trade_decisions ?? []).map((tradeDecision) => {
        const councilEntry = decision.council?.find(
          (entry) => normalizeAsset(entry.asset) === normalizeAsset(tradeDecision.asset),
        );
        return {
          ts: decision.ts,
          trace_id: decision.trace_id,
          ...tradeDecision,
          council: tradeDecision.council ?? councilEntry?.opinions,
          deadlock: tradeDecision.deadlock ?? councilEntry?.deadlock,
          confidence: tradeDecision.confidence ?? councilEntry?.confidence,
        };
      }),
    )
    .slice(0, limit);
}
