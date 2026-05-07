"use client";
import { useEffect, useState, useRef } from "react";
import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, Check, User, Zap, BarChart2, TrendingUp, Shield,
  ChevronRight, Info, X, Rocket,
} from "lucide-react";
import { LogoWordmark } from "@/components/Logo";

// ── Storage keys — namespaced per userId to prevent cross-user data leakage ─
const _ukey = (base: string, uid?: string | null) => uid ? `${base}:${uid}` : base;

export function markOnboardingDone(userId?: string | null) {
  try { localStorage.setItem(_ukey("qt:onboarding_done_v2", userId), "1"); } catch { /* private mode */ }
}
export function hasCompletedOnboarding(userId?: string | null) {
  try { return !!localStorage.getItem(_ukey("qt:onboarding_done_v2", userId)); } catch { return false; }
}

// ── Steps for BEGINNER mode ─────────────────────────────────────────────────
const BEGINNER_STEPS = [
  { id: 1, icon: User,       title: "Welcome — let's get you set up",  sub: "Takes about 2 minutes" },
  { id: 2, icon: Shield,     title: "Paper trading first",             sub: "No real money risk while you learn" },
  { id: 3, icon: Zap,        title: "Choose a plan",                   sub: "Start free — upgrade anytime" },
  { id: 4, icon: TrendingUp, title: "Pick your exchange",              sub: "We'll walk you through connecting it" },
  { id: 5, icon: BarChart2,  title: "Your trading goal",               sub: "Personalises the AI for you" },
  { id: 6, icon: Check,      title: "You're ready",                    sub: "Let's go" },
];

// ── Steps for EXPERT (skip) mode ────────────────────────────────────────────
const EXPERT_STEPS = [
  { id: 1, icon: User,       title: "Quick setup",   sub: "Just 2 fields" },
  { id: 2, icon: TrendingUp, title: "Your exchange", sub: "Pick one to pre-fill settings" },
  { id: 3, icon: Check,      title: "Done",          sub: "Straight to your dashboard" },
];

// ── Styles ───────────────────────────────────────────────────────────────────
const inputStyle: React.CSSProperties = {
  width: "100%", padding: "11px 14px", borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)",
  color: "#fff", fontSize: 14, outline: "none",
};
const labelStyle: React.CSSProperties = {
  display: "block", fontSize: 12, color: "rgba(255,255,255,0.45)", fontWeight: 500, marginBottom: 6,
};

// ── Tooltip helper ───────────────────────────────────────────────────────────
function Tip({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      {children}
      <button
        onClick={() => setOpen(o => !o)}
        style={{ marginLeft: 5, background: "none", border: "none", cursor: "pointer",
          color: "rgba(255,255,255,0.3)", padding: 0, display: "inline-flex" }}>
        <Info size={12} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.15 }}
            style={{
              position: "absolute", bottom: "calc(100% + 8px)", left: "50%",
              transform: "translateX(-50%)", zIndex: 100,
              background: "#1a1a1a", border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 10, padding: "10px 12px", width: 240,
              boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#4ade80" }}>{label}</span>
              <button onClick={() => setOpen(false)} style={{ background: "none", border: "none",
                cursor: "pointer", color: "rgba(255,255,255,0.3)", padding: 0 }}>
                <X size={10} />
              </button>
            </div>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.55 }}>
              {children}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  );
}

// ── Dot progress bar ─────────────────────────────────────────────────────────
function StepDots({ current, total }: { current: number; total: number }) {
  return (
    <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 28 }}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} style={{
          width: i + 1 === current ? 20 : 6, height: 6, borderRadius: 3,
          background: i + 1 <= current ? "#4ade80" : "rgba(255,255,255,0.1)",
          transition: "all 0.3s",
        }} />
      ))}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function OnboardingPage() {
  const { user, isLoaded } = useUser();
  const router = useRouter();

  // Mode: null = not chosen, "beginner" = full wizard, "expert" = 3-step express
  const [mode,       setMode]       = useState<null | "beginner" | "expert">(null);
  const [step,       setStep]       = useState(1);
  const [firstName,  setFirstName]  = useState("");
  const [lastName,   setLastName]   = useState("");
  const [goal,       setGoal]       = useState("");
  const [venueType,  setVenueType]  = useState("BINANCE");
  const [planChoice, setPlanChoice] = useState<"FREE" | "STARTER" | "PRO">("FREE");
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState("");

  const STEPS = mode === "expert" ? EXPERT_STEPS : BEGINNER_STEPS;
  const totalSteps = STEPS.length;

  // Auto-skip users who already completed onboarding
  useEffect(() => {
    if (!isLoaded || !user) return;
    if (hasCompletedOnboarding()) {
      router.replace("/dashboard");
    }
  }, [isLoaded, user, router]);

  const next = () => { setError(""); setStep(s => Math.min(s + 1, totalSteps)); };
  const back = () => { setError(""); setStep(s => Math.max(s - 1, 1)); };

  const skipToDashboard = async () => {
    markOnboardingDone();
    router.replace("/dashboard");
  };

  const finish = async () => {
    if (!firstName.trim()) { setError("Enter your first name to continue."); return; }
    setSaving(true);
    try {
      await user!.update({ firstName: firstName.trim(), lastName: lastName.trim() || undefined });
      try {
        const uid = user?.id ?? null;
        localStorage.setItem(_ukey("qt:onboarding", uid), JSON.stringify({
          venueType, goal, planChoice, mode, completedAt: Date.now(),
        }));
        markOnboardingDone(uid);
      } catch { /* private mode */ }
      await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" }).catch(() => {});
      if (planChoice !== "FREE" && mode === "beginner") {
        router.replace(`/billing?intent=upgrade&plan=${planChoice}&onboarding=1`);
      } else {
        router.replace(`/settings?tab=venues&onboarding=1&venue=${venueType}`);
      }
    } catch {
      setError("Something went wrong — please try again.");
      setSaving(false);
    }
  };

  if (!isLoaded || (user?.firstName && hasCompletedOnboarding())) {
    return (
      <div style={{ background: "#000", minHeight: "100vh", display: "flex",
        alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "rgba(255,255,255,0.3)", fontSize: 14 }}>Loading…</span>
      </div>
    );
  }

  // ── MODE SELECTION SCREEN ─────────────────────────────────────────────────
  if (mode === null) {
    return (
      <div style={{ position: "relative", minHeight: "100vh", background: "#050505",
        color: "#fff", display: "flex", flexDirection: "column" }}>
        <div style={{ position: "fixed", inset: 0, pointerEvents: "none",
          background: "radial-gradient(ellipse 60% 60% at 50% 0%, rgba(74,222,128,0.07) 0%, transparent 70%)" }} />

        <nav style={{ position: "relative", zIndex: 10, display: "flex", alignItems: "center",
          padding: "0 24px", height: 56, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
          <LogoWordmark size={26} />
        </nav>

        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
          padding: "32px 20px", position: "relative", zIndex: 10 }}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }} style={{ width: "100%", maxWidth: 460 }}>

            <div style={{ textAlign: "center", marginBottom: 32 }}>
              <div style={{ width: 60, height: 60, borderRadius: "50%",
                background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.25)",
                display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                <Rocket size={26} style={{ color: "#4ade80" }} />
              </div>
              <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 8 }}>
                Welcome to QuantatraderAI
              </h1>
              <p style={{ fontSize: 14, color: "rgba(255,255,255,0.45)", lineHeight: 1.6 }}>
                How familiar are you with AI trading platforms?
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Beginner path */}
              <motion.button
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={() => setMode("beginner")}
                style={{
                  padding: "20px 22px", borderRadius: 16, cursor: "pointer", textAlign: "left",
                  background: "rgba(74,222,128,0.06)", border: "1px solid rgba(74,222,128,0.2)",
                  color: "inherit", width: "100%",
                }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <p style={{ fontSize: 15, fontWeight: 700, color: "#4ade80", marginBottom: 4 }}>
                      🌱 I&apos;m new to trading bots
                    </p>
                    <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", lineHeight: 1.5 }}>
                      Walk me through everything — what is paper trading, how do API keys
                      work, what does the AI actually do.
                    </p>
                  </div>
                  <ChevronRight size={16} style={{ color: "#4ade80", flexShrink: 0, marginLeft: 12 }} />
                </div>
                <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {["6 steps", "~3 min", "Full explanations"].map(t => (
                    <span key={t} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4,
                      background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.15)",
                      color: "rgba(74,222,128,0.8)" }}>{t}</span>
                  ))}
                </div>
              </motion.button>

              {/* Expert path */}
              <motion.button
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={() => setMode("expert")}
                style={{
                  padding: "20px 22px", borderRadius: 16, cursor: "pointer", textAlign: "left",
                  background: "rgba(129,140,248,0.06)", border: "1px solid rgba(129,140,248,0.2)",
                  color: "inherit", width: "100%",
                }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <p style={{ fontSize: 15, fontWeight: 700, color: "#818cf8", marginBottom: 4 }}>
                      ⚡ I know trading — just set me up fast
                    </p>
                    <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", lineHeight: 1.5 }}>
                      Skip the explanations. Name, pick an exchange, go.
                    </p>
                  </div>
                  <ChevronRight size={16} style={{ color: "#818cf8", flexShrink: 0, marginLeft: 12 }} />
                </div>
                <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
                  {["3 steps", "< 60 sec"].map(t => (
                    <span key={t} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4,
                      background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.15)",
                      color: "rgba(129,140,248,0.8)" }}>{t}</span>
                  ))}
                </div>
              </motion.button>

              {/* Hard skip */}
              <button onClick={skipToDashboard}
                style={{ padding: "10px 0", fontSize: 12, color: "rgba(255,255,255,0.25)",
                  background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                Skip all of this → go straight to dashboard
              </button>
            </div>
          </motion.div>
        </div>
      </div>
    );
  }

  // ── WIZARD STEPS ─────────────────────────────────────────────────────────
  const currentStepMeta = STEPS[step - 1];
  const isLastStep = step === totalSteps;

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "#050505",
      color: "#fff", display: "flex", flexDirection: "column" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse 60% 60% at 50% 0%, rgba(74,222,128,0.06) 0%, transparent 70%)" }} />

      <nav style={{ position: "relative", zIndex: 10, display: "flex", alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px", height: 56, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <LogoWordmark size={26} />
        {/* Skip button always visible */}
        <button onClick={skipToDashboard}
          style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", background: "none",
            border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
          Skip setup <ChevronRight size={11} />
        </button>
      </nav>

      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        padding: "32px 20px", position: "relative", zIndex: 10 }}>
        <div style={{ width: "100%", maxWidth: 460 }}>

          {/* Mode badge */}
          <div style={{ textAlign: "center", marginBottom: 16 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
              textTransform: "uppercase", padding: "3px 10px", borderRadius: 6,
              background: mode === "expert" ? "rgba(129,140,248,0.1)" : "rgba(74,222,128,0.1)",
              border: `1px solid ${mode === "expert" ? "rgba(129,140,248,0.2)" : "rgba(74,222,128,0.2)"}`,
              color: mode === "expert" ? "#818cf8" : "#4ade80" }}>
              {mode === "expert" ? "⚡ Express setup" : "🌱 Guided setup"}
            </span>
          </div>

          <StepDots current={step} total={totalSteps} />

          <AnimatePresence mode="wait">
            <motion.div key={`${mode}-${step}`}
              initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22 }}>

              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
                {(() => { const Icon = currentStepMeta.icon; return <Icon size={22} style={{ color: "#4ade80" }} />; })()}
                <div>
                  <p style={{ fontSize: 18, fontWeight: 700 }}>{currentStepMeta.title}</p>
                  <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>{currentStepMeta.sub}</p>
                </div>
              </div>

              <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 18, padding: "24px 22px" }}>

                {/* ── BEGINNER STEP 1 / EXPERT STEP 1: Name ────────────────── */}
                {step === 1 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {mode === "beginner" && (
                      <div style={{ padding: "10px 14px", background: "rgba(74,222,128,0.05)",
                        border: "1px solid rgba(74,222,128,0.12)", borderRadius: 10, marginBottom: 4 }}>
                        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.6 }}>
                          QuantatraderAI is an <strong style={{ color: "rgba(255,255,255,0.8)" }}>autonomous AI trading agent</strong>.
                          Once started, it monitors markets 24/7 and places trades on your behalf.
                          You are always in control — you can stop it instantly at any time.
                        </p>
                      </div>
                    )}
                    <div>
                      <label style={labelStyle}>First Name *</label>
                      <input autoFocus style={inputStyle} value={firstName}
                        onChange={e => setFirstName(e.target.value)} placeholder="e.g. Alex" />
                    </div>
                    <div>
                      <label style={labelStyle}>Last Name <span style={{ opacity: 0.4 }}>(optional)</span></label>
                      <input style={inputStyle} value={lastName}
                        onChange={e => setLastName(e.target.value)} placeholder="e.g. Johnson" />
                    </div>
                  </div>
                )}

                {/* ── BEGINNER STEP 2: Paper Trading explanation ──────────── */}
                {mode === "beginner" && step === 2 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ padding: "14px 16px", background: "rgba(74,222,128,0.06)",
                      border: "1px solid rgba(74,222,128,0.15)", borderRadius: 12 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "#4ade80", marginBottom: 6 }}>
                        What is paper trading?
                      </p>
                      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.7 }}>
                        Paper trading is <strong style={{ color: "rgba(255,255,255,0.8)" }}>simulated trading with fake money</strong>.
                        The AI makes all the same decisions and you see all the same results —
                        but no real money changes hands.
                      </p>
                      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.7, marginTop: 8 }}>
                        This is how you learn the system, test strategies, and build confidence
                        <strong style={{ color: "#4ade80" }}> before risking a single dollar</strong>.
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {[
                        { label: "✅ Recommended", sub: "Paper trading first", val: true },
                        { label: "⚠️ Live trading", sub: "Real money at risk", val: false },
                      ].map(o => (
                        <div key={String(o.val)} style={{ flex: 1, padding: "12px 14px", borderRadius: 10,
                          background: "rgba(255,255,255,0.03)",
                          border: `1px solid rgba(255,255,255,${o.val ? "0.15" : "0.06"})` }}>
                          <p style={{ fontSize: 13, fontWeight: 600, color: o.val ? "#4ade80" : "rgba(255,255,255,0.5)" }}>
                            {o.label}
                          </p>
                          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 3 }}>{o.sub}</p>
                        </div>
                      ))}
                    </div>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", lineHeight: 1.5 }}>
                      We will start you in paper mode. You can switch to live trading in Settings
                      whenever you&apos;re ready.
                    </p>
                  </div>
                )}

                {/* ── BEGINNER STEP 3: Plan ────────────────────────────────── */}
                {mode === "beginner" && step === 3 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {[
                      { plan: "FREE",    label: "Free",    price: "$0",     desc: "Paper trading, 1 venue, Groq AI" },
                      { plan: "STARTER", label: "Starter", price: "$20/mo", desc: "Live trading, 2 venues, alerts" },
                      { plan: "PRO",     label: "Pro",     price: "$99/mo", desc: "Everything, AI council, RAG memory", hot: true },
                    ].map(p => {
                      const selected = planChoice === p.plan;
                      return (
                        <button key={p.plan} type="button"
                          onClick={() => setPlanChoice(p.plan as "FREE" | "STARTER" | "PRO")}
                          style={{ padding: "14px 16px", borderRadius: 12, cursor: "pointer",
                            background: selected ? (p.hot ? "rgba(74,222,128,0.12)" : "rgba(255,255,255,0.06)")
                              : (p.hot ? "rgba(74,222,128,0.06)" : "rgba(255,255,255,0.02)"),
                            border: `1px solid ${selected ? (p.hot ? "rgba(74,222,128,0.45)" : "rgba(255,255,255,0.25)")
                              : (p.hot ? "rgba(74,222,128,0.2)" : "rgba(255,255,255,0.07)")}`,
                            textAlign: "left", color: "inherit" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div>
                              {p.hot && <span style={{ fontSize: 9, fontWeight: 700, color: "#4ade80",
                                textTransform: "uppercase", letterSpacing: "0.1em" }}>Popular · </span>}
                              <span style={{ fontSize: 14, fontWeight: 600, color: "#fff" }}>{p.label}</span>
                              {selected && <span style={{ marginLeft: 8, fontSize: 10, color: "#4ade80" }}>● selected</span>}
                            </div>
                            <span style={{ fontSize: 14, fontWeight: 600, color: p.hot ? "#4ade80" : "#fff" }}>{p.price}</span>
                          </div>
                          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginTop: 4 }}>{p.desc}</p>
                        </button>
                      );
                    })}
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", textAlign: "center", marginTop: 4 }}>
                      💡 Start Free — upgrade whenever you&apos;re ready. No credit card required for Free.
                    </p>
                  </div>
                )}

                {/* ── VENUE STEP (beginner step 4 / expert step 2) ─────────── */}
                {((mode === "beginner" && step === 4) || (mode === "expert" && step === 2)) && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {mode === "beginner" && (
                      <div style={{ marginBottom: 4 }}>
                        <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginBottom: 8 }}>
                          An <strong style={{ color: "rgba(255,255,255,0.8)" }}>exchange</strong> is where
                          cryptocurrency or stocks are bought and sold.
                          QuantatraderAI connects to your exchange account using an{" "}
                          <Tip label="What is an API key?">
                            An API key is like a password that lets our AI read your balances and place
                            trades. You create it in your exchange&apos;s settings. We recommend enabling
                            &quot;Trade&quot; permission only — never &quot;Withdraw&quot;.
                          </Tip>
                          {" "}API key.
                        </p>
                      </div>
                    )}
                    {[
                      { id: "BINANCE",     label: "Binance",      sub: "Crypto futures + spot",  url: "https://www.binance.com/en/my/settings/api-management",   perms: 'Enable Spot & Margin Trading — DISABLE Withdrawals' },
                      { id: "HYPERLIQUID", label: "Hyperliquid",  sub: "Crypto perpetuals",       url: "https://app.hyperliquid.xyz/settings/api",                 perms: 'API wallet only — never paste your main wallet key' },
                      { id: "BYBIT",       label: "Bybit",        sub: "Crypto spot + perps",    url: "https://www.bybit.com/app/user/api-management",            perms: 'Trade permission — disable withdrawals + IP whitelist' },
                      { id: "OANDA",       label: "OANDA",        sub: "Forex + CFDs",            url: "https://www.oanda.com/us-en/trading/accounts/",            perms: 'Personal access token from My Account → API Access' },
                      { id: "ALPACA",      label: "Alpaca",       sub: "US Stocks + Crypto",      url: "https://app.alpaca.markets/paper-trading/overview",        perms: 'Paper: paper.alpaca.markets — Live: app.alpaca.markets' },
                    ].map(v => (
                      <div key={v.id} style={{ marginBottom: 6 }}>
                        <button onClick={() => setVenueType(v.id)}
                          style={{ padding: '10px 14px', borderRadius: 10, cursor: 'pointer',
                            textAlign: 'left', width: '100%',
                            background: venueType === v.id ? 'rgba(74,222,128,0.08)' : 'rgba(255,255,255,0.02)',
                            border: `1px solid ${venueType === v.id ? 'rgba(74,222,128,0.3)' : 'rgba(255,255,255,0.07)'}`,
                            display: 'flex', alignItems: 'center', gap: 10 }}>
                          {venueType === v.id && <Check size={11} style={{ color: '#4ade80', flexShrink: 0 }} />}
                          <div>
                            <span style={{ fontSize: 13, fontWeight: venueType === v.id ? 700 : 400,
                              color: venueType === v.id ? '#4ade80' : '#fff' }}>{v.label}</span>
                            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginLeft: 8 }}>{v.sub}</span>
                          </div>
                        </button>
                        {venueType === v.id && (
                          <div style={{ marginTop: 4, padding: '10px 14px',
                            background: 'rgba(74,222,128,0.04)', border: '1px solid rgba(74,222,128,0.12)',
                            borderRadius: '0 0 10px 10px', borderTop: 'none' }}>
                            <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 8, lineHeight: 1.5 }}>
                              <strong style={{ color: 'rgba(255,255,255,0.75)' }}>Required permission:</strong> {v.perms}
                            </p>
                            <a href={v.url} target='_blank' rel='noopener noreferrer'
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                                fontSize: 11, color: '#4ade80', textDecoration: 'none',
                                background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.25)',
                                padding: '5px 12px', borderRadius: 6, fontWeight: 600 }}>
                              Open {v.label} API settings ↗
                            </a>
                          </div>
                        )}
                      </div>
                    ))}
                    <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', marginTop: 4 }}>
                      Click your exchange to see the exact permission needed and a direct link.
                    </p>
                  </div>
                )}

                {/* ── BEGINNER STEP 5: Goal ────────────────────────────────── */}
                {mode === "beginner" && step === 5 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", marginBottom: 4, lineHeight: 1.6 }}>
                      This shapes how the AI thinks about risk and position sizing — it personalises
                      the strategy specifically for you.
                    </p>
                    {[
                      { val: "grow",       label: "Grow steadily",    sub: "Balanced risk, 10-30% annual target" },
                      { val: "aggressive", label: "Aggressive growth", sub: "Higher risk, max return" },
                      { val: "income",     label: "Passive income",    sub: "Low risk, stable cash flow" },
                      { val: "learning",   label: "Learning / paper",  sub: "I'm here to explore, no real money yet" },
                    ].map(g => (
                      <button key={g.val} onClick={() => setGoal(g.val)}
                        style={{ padding: "12px 14px", borderRadius: 10, cursor: "pointer", textAlign: "left",
                          background: goal === g.val ? "rgba(167,139,250,0.08)" : "rgba(255,255,255,0.02)",
                          border: `1px solid ${goal === g.val ? "rgba(167,139,250,0.3)" : "rgba(255,255,255,0.07)"}` }}>
                        <p style={{ fontSize: 13, fontWeight: 600, color: goal === g.val ? "#a78bfa" : "#fff" }}>{g.label}</p>
                        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>{g.sub}</p>
                      </button>
                    ))}
                  </div>
                )}

                {/* ── DONE STEP (beginner 6 / expert 3) ───────────────────── */}
                {isLastStep && (
                  <div style={{ textAlign: "center", padding: "8px 0" }}>
                    <div style={{ width: 56, height: 56, borderRadius: "50%",
                      background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.3)",
                      display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                      <Check size={24} style={{ color: "#4ade80" }} />
                    </div>
                    <p style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>
                      You&apos;re all set, {firstName || "Trader"}!
                    </p>
                    <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.7 }}>
                      {mode === "beginner"
                        ? `Next: connect your ${venueType.charAt(0) + venueType.slice(1).toLowerCase()} API key in Settings. We'll show you exactly how.`
                        : `Head straight to Settings and connect your ${venueType.charAt(0) + venueType.slice(1).toLowerCase()} API key.`}
                    </p>
                    {mode === "beginner" && (
                      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 6, textAlign: "left" }}>
                        {[
                          "Connect your API key in Settings",
                          "Start the agent in paper mode",
                          "Watch the Decision Timeline",
                          "Switch to live when you're confident",
                        ].map((t, i) => (
                          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                            fontSize: 12, color: "rgba(255,255,255,0.45)" }}>
                            <span style={{ width: 18, height: 18, borderRadius: "50%",
                              background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.2)",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 9, color: "#4ade80", flexShrink: 0, fontWeight: 700 }}>
                              {i + 1}
                            </span>
                            {t}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {error && <p style={{ color: "#f87171", fontSize: 13, marginTop: 10 }}>{error}</p>}
              </div>

              {/* Nav buttons */}
              <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
                {step > 1 && (
                  <button onClick={back}
                    style={{ flex: 1, padding: "11px 0", borderRadius: 10, background: "transparent",
                      border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.5)",
                      fontSize: 13, cursor: "pointer" }}>
                    Back
                  </button>
                )}
                <button
                  onClick={isLastStep
                    ? finish
                    : (step === 1 && !firstName.trim() ? () => setError("Enter your first name") : next)}
                  disabled={saving}
                  style={{ flex: 2, padding: "11px 0", borderRadius: 10,
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    background: "#fff", color: "#000", border: "none",
                    fontSize: 13, fontWeight: 700, cursor: saving ? "default" : "pointer",
                    opacity: saving ? 0.7 : 1 }}>
                  {saving ? "Saving…" : isLastStep ? "Go to Dashboard →" : <>Next <ArrowRight size={13} /></>}
                </button>
              </div>

              {/* Hard skip from any step */}
              {!isLastStep && (
                <button onClick={skipToDashboard}
                  style={{ display: "block", width: "100%", textAlign: "center", marginTop: 12,
                    fontSize: 11, color: "rgba(255,255,255,0.2)", background: "none",
                    border: "none", cursor: "pointer", textDecoration: "underline" }}>
                  Skip and go to dashboard
                </button>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
