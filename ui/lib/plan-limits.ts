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
  ragMemory:    boolean;
  copyTrading:  boolean;
  marketplace:  boolean;
  whiteLabel:   boolean;
  apiAccess:    boolean;
}

export const PLAN_LIMITS: Record<Plan, PlanLimits> = {
  FREE: {
    maxVenues: 1, maxAssets: 1,
    liveTrading: false, backtesting: false, aiCouncil: false, ragMemory: false,
    copyTrading: false, marketplace: false, whiteLabel: false, apiAccess: false,
  },
  STARTER: {
    maxVenues: 2, maxAssets: 3,
    liveTrading: true, backtesting: true,  aiCouncil: false, ragMemory: false,
    copyTrading: false, marketplace: false, whiteLabel: false, apiAccess: false,
  },
  PRO: {
    maxVenues: 999, maxAssets: 999,
    liveTrading: true, backtesting: true, aiCouncil: true, ragMemory: true,
    copyTrading: true, marketplace: true, whiteLabel: false, apiAccess: false,
  },
  ENTERPRISE: {
    maxVenues: 999, maxAssets: 999,
    liveTrading: true, backtesting: true, aiCouncil: true, ragMemory: true,
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
  { plan: "FREE",       price: 0,    label: "Free",       features: ["Paper trading only", "1 venue", "1 asset", "Groq AI"] },
  { plan: "STARTER",    price: 20,   label: "Starter",    features: ["Live trading", "2 venues", "3 assets", "Telegram alerts", "Backtesting"] },
  { plan: "PRO",        price: 99,   label: "Pro",        features: ["Unlimited venues + assets", "AI council (3 LLMs)", "RAG memory", "Copy trading", "TradingView webhooks"] },
  { plan: "ENTERPRISE", price: 199,  label: "Enterprise", features: ["Everything in Pro", "White-label", "API access", "Priority support", "Custom models"] },
];
