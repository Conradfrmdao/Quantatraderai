/**
 * Plan limits enforcement.
 * Called by API routes before allowing premium actions.
 */

export type Plan = "FREE" | "STARTER" | "PRO" | "ENTERPRISE";

export interface PlanLimits {
  maxVenues:    number;
  maxAssets:    number;
  liveTrading:  boolean;
  backtesting:  boolean;
  aiCouncil:    boolean;
  aiModels:     number;
  aiPrimary:    string;
  aiSecondary:  string | null;
  aiDormant:    string | null;
  ragMemory:    boolean;
  copyTrading:  boolean;
  marketplace:  boolean;
  whiteLabel:   boolean;
  apiAccess:    boolean;
}

export const PLAN_LIMITS: Record<Plan, PlanLimits> = {
  FREE: {
    maxVenues: 1, maxAssets: 1,
    liveTrading: false, backtesting: false, aiCouncil: false, aiModels: 1, aiPrimary: "Groq", aiSecondary: null, aiDormant: null, ragMemory: false,
    copyTrading: false, marketplace: false, whiteLabel: false, apiAccess: false,
  },
  STARTER: {
    maxVenues: 2, maxAssets: 3,
    liveTrading: true, backtesting: true,  aiCouncil: false, aiModels: 1, aiPrimary: "Groq", aiSecondary: "Gemini verifier", aiDormant: null, ragMemory: false,
    copyTrading: false, marketplace: false, whiteLabel: false, apiAccess: false,
  },
  PRO: {
    maxVenues: 999, maxAssets: 999,
    liveTrading: true, backtesting: true, aiCouncil: true, aiModels: 2, aiPrimary: "Groq", aiSecondary: "Gemini", aiDormant: null, ragMemory: true,
    copyTrading: true, marketplace: true, whiteLabel: false, apiAccess: false,
  },
  ENTERPRISE: {
    maxVenues: 999, maxAssets: 999,
    liveTrading: true, backtesting: true, aiCouncil: true, aiModels: 3, aiPrimary: "Groq", aiSecondary: "Gemini", aiDormant: "Bedrock reserved", ragMemory: true,
    copyTrading: true, marketplace: true, whiteLabel: true, apiAccess: true,
  },
};

export function getPlanLimits(plan: Plan): PlanLimits {
  return PLAN_LIMITS[plan] ?? PLAN_LIMITS.FREE;
}

export function checkLimit(plan: Plan, feature: keyof PlanLimits, value?: number): boolean {
  const limits = getPlanLimits(plan);
  const limit  = limits[feature];
  if (typeof limit === "boolean") return limit;
  if (typeof limit === "number" && value !== undefined) return value <= limit;
  return true;
}

export const PLAN_PRICING = [
  { plan: "FREE",       price: 0,    label: "Free",       features: ["Paper trading only", "1 venue", "1 asset", "1 AI model: Groq"] },
  { plan: "STARTER",    price: 20,   label: "Starter",    features: ["Live trading", "2 venues", "3 assets", "Groq primary + Gemini verifier", "Backtesting"] },
  { plan: "PRO",        price: 99,   label: "Pro",        features: ["Unlimited venues + assets", "2-model AI council: Groq + Gemini", "RAG memory", "Copy trading", "TradingView webhooks"] },
  { plan: "ENTERPRISE", price: 199,  label: "Enterprise", features: ["Everything in Pro", "3-model architecture", "Groq + Gemini active", "Bedrock reserved until enabled", "Priority support"] },
];
