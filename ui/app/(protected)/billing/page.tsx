"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Check, Zap, CreditCard } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useToast } from "@/components/Toast";
import { useIsMobile } from "@/hooks/useIsMobile";

type Plan = "FREE" | "STARTER" | "PRO" | "ENTERPRISE";

const PLANS = [
  {
    plan: "FREE" as Plan, label: "Free", price: "$0",
    description: "Try the platform with paper trading",
    features: ["Paper trading only", "1 venue", "1 asset", "Groq AI decisions", "Basic dashboard"],
    cta: "Current plan",
  },
  {
    plan: "STARTER" as Plan, label: "Starter", price: "$20/mo",
    description: "Go live with real money",
    features: ["Live trading", "2 venues", "3 assets", "Telegram alerts", "Backtesting", "Trade journal"],
    cta: "Upgrade to Starter",
  },
  {
    plan: "PRO" as Plan, label: "Pro", price: "$99/mo",
    description: "Everything, no limits",
    features: ["Unlimited venues + assets", "AI council (3 LLMs)", "RAG trade memory", "Copy trading", "TradingView webhooks", "MTF confluence + news intel"],
    cta: "Upgrade to Pro",
    highlight: true,
  },
  {
    plan: "ENTERPRISE" as Plan, label: "Enterprise", price: "$199/mo",
    description: "White-label + API for institutions",
    features: ["Everything in Pro", "White-label branding", "REST API access", "VaR / compliance reports", "Priority support", "Custom AI models"],
    cta: "Contact us",
  },
];

interface BillingInfo {
  plan: Plan; subId: string | null; expiresAt: string | null; provider: string;
  usage?: { venues: number; tradesLogged: number; copyFollowing: number };
}

const PLAN_VENUE_LIMIT: Record<Plan, number> = { FREE: 1, STARTER: 2, PRO: 999, ENTERPRISE: 999 };

export default function BillingPage() {
  const isMobile = useIsMobile();
  const [billing, setBilling]   = useState<BillingInfo | null>(null);
  const [loading, setLoading]   = useState(true);
  const [upgrading, setUpgrading] = useState<Plan | null>(null);
  const toast = useToast();

  useEffect(() => {
    fetch("/api/billing").then(r => r.json()).then((d: BillingInfo) => { setBilling(d); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const upgrade = async (plan: Plan) => {
    if (plan === "ENTERPRISE") { window.location.href = "mailto:godlovesconrad@gmail.com?subject=Enterprise enquiry"; return; }
    setUpgrading(plan);
    try {
      const res  = await fetch("/api/billing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan }) });
      const data = await res.json() as { checkoutUrl?: string; error?: string };
      if (data.checkoutUrl) window.location.href = data.checkoutUrl;
      else toast(data.error ?? "Checkout failed. Please try again.", "error");
    } finally { setUpgrading(null); }
  };

  const cancel = async () => {
    if (!confirm("Cancel your subscription? You'll be downgraded to Free at the end of your billing period.")) return;
    const res = await fetch("/api/billing", { method: "DELETE" });
    if (res.ok) { setBilling(b => b ? { ...b, plan: "FREE", subId: null } : b); }
  };

  const current = billing?.plan ?? "FREE";

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56, borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12, background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)", position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Billing</span>
        {billing && (
          <span style={{ marginLeft: "auto", padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: current === "FREE" ? "rgba(255,255,255,0.06)" : "rgba(74,222,128,0.1)", color: current === "FREE" ? "var(--muted)" : "var(--green)" }}>
            {current}
          </span>
        )}
      </header>

      <main style={{ padding: isMobile ? "24px 12px 60px" : "40px 40px 60px", maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ marginBottom: 36 }}>
          <h1 style={{ fontSize: 24, fontWeight: 600, color: "#fff", marginBottom: 8 }}>Plans & Billing</h1>
          {billing?.expiresAt ? null : billing?.plan === "FREE" ? (
            <p style={{ fontSize: 13, color: "var(--muted)" }}>Upgrade to start live trading.</p>
          ) : null}
          {billing?.expiresAt && (
            <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
              Current period ends: {new Date(billing.expiresAt).toLocaleDateString()}
              {billing.subId && <button onClick={cancel} style={{ marginLeft: 12, fontSize: 11, color: "var(--red)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>Cancel</button>}
            </p>
          )}
        </div>

        {/* Usage strip */}
        {billing?.usage && (
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(3,1fr)", gap: 10, marginBottom: 32 }}>
            {[
              {
                label: "Venues connected",
                value: billing.usage.venues,
                limit: PLAN_VENUE_LIMIT[billing.plan],
              },
              { label: "Trades logged",  value: billing.usage.tradesLogged,  limit: null },
              { label: "Copy following", value: billing.usage.copyFollowing, limit: null },
            ].map(m => {
              const pct = m.limit ? Math.min((m.value / m.limit) * 100, 100) : 0;
              const near = m.limit && pct >= 80;
              return (
                <div key={m.label} style={{
                  background: "rgba(255,255,255,0.02)",
                  border: `1px solid ${near ? "rgba(251,191,36,0.2)" : "rgba(255,255,255,0.06)"}`,
                  borderRadius: 12, padding: "14px 18px",
                }}>
                  <p style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase",
                    letterSpacing: "0.08em", marginBottom: 6 }}>{m.label}</p>
                  <p style={{ fontSize: 18, fontWeight: 600, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
                    {m.value}{m.limit && m.limit < 999 && ` / ${m.limit}`}
                  </p>
                  {m.limit && m.limit < 999 && (
                    <div style={{ height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden", marginTop: 8 }}>
                      <div style={{ width: `${pct}%`, height: "100%",
                        background: near ? "#fbbf24" : "#4ade80", borderRadius: 2 }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(4,1fr)", gap: 16 }}>
          {PLANS.map((p, i) => (
            <motion.div key={p.plan}
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
              style={{
                background: p.highlight ? "rgba(74,222,128,0.06)" : "rgba(255,255,255,0.03)",
                border: `1px solid ${p.highlight ? "rgba(74,222,128,0.25)" : current === p.plan ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.07)"}`,
                borderRadius: 16, padding: "24px 20px", display: "flex", flexDirection: "column", gap: 0,
              }}
            >
              {p.highlight && <div style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>Most popular</div>}
              <p style={{ fontSize: 16, fontWeight: 700, color: "#fff", marginBottom: 4 }}>{p.label}</p>
              <p style={{ fontSize: 24, fontWeight: 500, color: p.highlight ? "var(--green)" : "#fff", marginBottom: 8, fontVariantNumeric: "tabular-nums" }}>{p.price}</p>
              <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 20, lineHeight: 1.5 }}>{p.description}</p>
              <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
                {p.features.map(f => (
                  <li key={f} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "rgba(255,255,255,0.7)" }}>
                    <Check size={12} style={{ color: "var(--green)", marginTop: 1, flexShrink: 0 }} /> {f}
                  </li>
                ))}
              </ul>
              {current === p.plan ? (
                <div style={{ textAlign: "center", fontSize: 12, color: "var(--muted)", padding: "8px 0", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}>Current plan</div>
              ) : (
                <button
                  onClick={() => upgrade(p.plan)}
                  disabled={upgrading === p.plan || loading}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                    background: p.highlight ? "rgba(74,222,128,0.15)" : "rgba(255,255,255,0.08)",
                    border: `1px solid ${p.highlight ? "rgba(74,222,128,0.35)" : "rgba(255,255,255,0.15)"}`,
                    borderRadius: 8, padding: "10px 0", fontSize: 13, fontWeight: 600, cursor: "pointer",
                    color: p.highlight ? "var(--green)" : "#fff", opacity: upgrading ? 0.6 : 1,
                    transition: "all 0.2s",
                  }}
                >
                  {p.plan === "ENTERPRISE" ? <Zap size={12} /> : <CreditCard size={12} />}
                  {upgrading === p.plan ? "Redirecting…" : p.cta}
                </button>
              )}
            </motion.div>
          ))}
        </div>
      </main>
    </div>
  );
}
