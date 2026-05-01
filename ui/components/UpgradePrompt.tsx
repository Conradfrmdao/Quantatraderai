"use client";
/**
 * UpgradePrompt — shown when a user hits a plan-gated feature (402 response).
 * Replaces error toasts with a premium-feeling upgrade call-to-action.
 */
import { motion } from "framer-motion";
import Link from "next/link";
import { Lock, Zap, ArrowRight } from "lucide-react";

interface Props {
  feature?:       string;   // feature name e.g. "AI Council", "Copy Trading"
  planRequired?:  string;   // "PRO" | "ENTERPRISE"
  message?:       string;   // override message
  compact?:       boolean;  // inline compact mode (for inside cards)
}

const PLAN_COLOR: Record<string, string> = {
  PRO:        "#a78bfa",
  ENTERPRISE: "#f97316",
  STARTER:    "#60a5fa",
};

const PLAN_FEATURES: Record<string, string[]> = {
  STARTER:    ["Live trading", "2 venues", "3 assets", "Telegram alerts", "Backtesting"],
  PRO:        ["AI Council (3 LLMs)", "RAG trade memory", "Copy trading", "TradingView webhooks", "Unlimited venues"],
  ENTERPRISE: ["White-label branding", "API access", "VaR compliance reports", "Priority support"],
};

export function UpgradePrompt({ feature, planRequired = "PRO", message, compact = false }: Props) {
  const color    = PLAN_COLOR[planRequired] ?? "#a78bfa";
  const features = PLAN_FEATURES[planRequired] ?? [];
  const priceMap: Record<string, string> = { STARTER: "$20/mo", PRO: "$99/mo", ENTERPRISE: "$199/mo" };

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "12px 16px", borderRadius: 12,
          background: `${color}0d`,
          border: `1px solid ${color}30`,
        }}
      >
        <Lock size={14} style={{ color, flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: 13, color: "#fff", fontWeight: 500 }}>
            {message ?? `${feature ?? "This feature"} requires the ${planRequired} plan`}
          </p>
        </div>
        <Link href="/billing" style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          padding: "6px 14px", borderRadius: 8,
          background: `${color}20`, border: `1px solid ${color}40`,
          color, fontSize: 12, fontWeight: 700, textDecoration: "none",
          whiteSpace: "nowrap",
        }}>
          Upgrade <ArrowRight size={11} />
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        padding: "48px 32px", textAlign: "center",
        background: `${color}08`,
        border: `1px solid ${color}20`,
        borderRadius: 20,
        maxWidth: 480, margin: "0 auto",
      }}
    >
      {/* Icon */}
      <div style={{
        width: 56, height: 56, borderRadius: "50%",
        background: `${color}18`, border: `2px solid ${color}30`,
        display: "flex", alignItems: "center", justifyContent: "center",
        marginBottom: 20,
      }}>
        <Lock size={22} style={{ color }} />
      </div>

      {/* Plan badge */}
      <span style={{
        fontSize: 10, fontWeight: 800, padding: "3px 12px", borderRadius: 20,
        background: `${color}18`, color, border: `1px solid ${color}35`,
        textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 16,
      }}>
        {planRequired} · {priceMap[planRequired] ?? ""}
      </span>

      <h2 style={{ fontSize: 20, fontWeight: 700, color: "#fff", marginBottom: 8 }}>
        {feature ?? "Premium Feature"}
      </h2>
      <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginBottom: 24, maxWidth: 340 }}>
        {message ?? `${feature ?? "This feature"} is available on the ${planRequired} plan. Upgrade to unlock it.`}
      </p>

      {/* Feature list */}
      {features.length > 0 && (
        <div style={{ width: "100%", marginBottom: 28 }}>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
            What you get with {planRequired}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {features.map(f => (
              <div key={f} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 8, background: "rgba(255,255,255,0.03)" }}>
                <Zap size={11} style={{ color, flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Link href="/billing" style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        padding: "12px 28px", borderRadius: 12,
        background: `${color}20`, border: `1px solid ${color}40`,
        color, fontSize: 14, fontWeight: 700, textDecoration: "none",
        transition: "all 0.2s",
      }}>
        Upgrade to {planRequired} <ArrowRight size={14} />
      </Link>
    </motion.div>
  );
}

/**
 * Hook: fetch a plan-gated endpoint and show UpgradePrompt if 402.
 * Returns { data, upgradeNeeded, planRequired, feature, error, loading }
 */
export function useGatedFetch<T>(url: string, options?: RequestInit) {
  const [state, setState] = (require("react") as typeof import("react")).useState<{
    data: T | null; upgradeNeeded: boolean; planRequired: string;
    feature: string; error: string | null; loading: boolean;
  }>({ data: null, upgradeNeeded: false, planRequired: "PRO", feature: "", error: null, loading: true });

  (require("react") as typeof import("react")).useEffect(() => {
    fetch(url, options)
      .then(async r => {
        if (r.status === 402) {
          const d = await r.json().catch(() => ({})) as { plan_required?: string; feature?: string; error?: string };
          setState(s => ({ ...s, loading: false, upgradeNeeded: true, planRequired: d.plan_required ?? "PRO", feature: d.feature ?? "", error: d.error ?? null }));
        } else if (r.ok) {
          const d = await r.json() as T;
          setState(s => ({ ...s, loading: false, data: d }));
        } else {
          setState(s => ({ ...s, loading: false, error: `Error ${r.status}` }));
        }
      })
      .catch(e => setState(s => ({ ...s, loading: false, error: String(e) })));
  }, [url]);

  return state;
}
