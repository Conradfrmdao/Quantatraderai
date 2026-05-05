'use client';

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, ChevronRight } from "lucide-react";
import dynamic from "next/dynamic";
import { InfiniteSlider } from "@/components/ui/infinite-slider";
import { APP_NAME } from "@/lib/constants";
import { Spotlight } from "@/components/ui/spotlight";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

const NeuralBackground = dynamic(
  () => import("@/components/ui/neural-background").then((m) => m.NeuralBackground),
  { ssr: false }
);

const NAV_LINKS = [
  { label: "Dashboard",   href: "/dashboard" },
  { label: "Risk Engine", href: "/dashboard" },
  { label: "Pricing",     href: "#pricing" },
  { label: "Docs",        href: "/docs" },
];

const SLIDER_ITEMS = [
  "Hyperliquid", "Binance Futures", "OANDA Forex", "Polymarket",
  "100+ via CCXT", "Groq LLaMA", "Claude Sonnet", "Gemini Pro",
  "Risk-First Architecture", "Multi-Venue", "Live PnL Tracking",
  "Automated Stop-Loss", "Backtesting Engine", "Prediction Markets",
];

const FEATURES = [
  {
    title: "Multi-Venue Execution",
    body: "Trade Hyperliquid perps, Binance futures, OANDA forex, Polymarket prediction markets, and 100+ exchanges from a single agent — each via a venue-agnostic interface.",
  },
  {
    title: "Risk-First Architecture",
    body: "Every order passes through configurable guardrails: 3% max position, 2× leverage cap, mandatory stop-losses, and a daily circuit breaker at −4%.",
  },
  {
    title: "AI Council — Collective Intelligence",
    body: "Claude 4, Groq LLaMA, Gemini Pro, and local Ollama models — each trained on years of distinct market data — independently analyse every signal. Their outputs are weighted, cross-checked, and aggregated into a single consensus decision. A supermajority is required to act; if the council disagrees, the system holds and protects your capital.",
  },
  {
    title: "Demo & Paper Trading",
    body: "Run the full AI council against live market data without risking a dollar. Switch between paper trading, exchange testnet, and live with one config flag — so you can see exactly how the system behaves before committing real capital.",
  },
  {
    title: "Backtesting Suite",
    body: "Replay any strategy on years of historical OHLCV data through the identical pipeline used in production — same AI council, same risk rules, same indicators. No separate code paths, no optimistic back-fit.",
  },
];

const btnPrimary: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 8,
  background: "#ffffff", color: "#000000",
  fontWeight: 600, fontSize: 14, padding: "12px 28px",
  borderRadius: 12, border: "none", cursor: "pointer",
  textDecoration: "none", letterSpacing: "-0.01em",
  transition: "opacity .15s", whiteSpace: "nowrap" as const,
};
const btnOutline: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 8,
  background: "transparent", color: "rgba(255,255,255,0.75)",
  fontWeight: 500, fontSize: 14, padding: "12px 28px",
  borderRadius: 12, border: "1px solid rgba(255,255,255,0.15)",
  cursor: "pointer", textDecoration: "none",
  transition: "border-color .15s, color .15s", whiteSpace: "nowrap" as const,
};
const btnGhost: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 6,
  background: "transparent", color: "rgba(255,255,255,0.5)",
  fontWeight: 500, fontSize: 14, padding: "8px 16px",
  borderRadius: 10, border: "none", cursor: "pointer",
  textDecoration: "none", transition: "color .15s", whiteSpace: "nowrap" as const,
};

export function HeroSection() {
  const isMobile = useIsMobile();
  return (
    <div style={{ background: "#000", color: "#fff" }}>

      {/* ── Sticky navbar — outside the hero section, persists while scrolling ── */}
      <motion.nav
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
          position: "sticky", top: 0, zIndex: 50,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          background: "rgba(0,0,0,0.88)",
          backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div style={{ maxWidth: 1100, margin: "0 auto", padding: isMobile ? "0 16px" : "0 32px", height: 60, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <LogoWordmark size={32} />
          {!isMobile && (
            <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
              {NAV_LINKS.map((n) => (
                <Link key={n.label} href={n.href} style={{ fontSize: 14, color: "rgba(255,255,255,0.45)", textDecoration: "none" }}>
                  {n.label}
                </Link>
              ))}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Link href="/sign-in" style={btnGhost}>Sign in</Link>
            <Link href="/sign-up" style={{ ...btnPrimary, padding: isMobile ? "10px 16px" : "12px 28px", fontSize: isMobile ? 13 : 14 }}>
              {isMobile ? "Start" : "Get Started"} <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </motion.nav>

      {/* ══════════════════════════════════════════════════════════════
          FIRST SECTION — neural background lives ONLY inside here
      ══════════════════════════════════════════════════════════════ */}
      <section style={{ position: "relative", overflow: "hidden", minHeight: "calc(100vh - 60px)", display: "flex", alignItems: "center", justifyContent: "center" }}>

        {/* Neural network (absolute — clipped to this section) */}
        <div style={{ position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none" }}>
          <NeuralBackground className="w-full h-full" />
          {/* Gradient to fade bottom edge into the next section */}
          <div style={{
            position: "absolute", inset: 0,
            background: "radial-gradient(ellipse 130% 90% at 50% 40%, rgba(0,0,0,0.18) 0%, rgba(0,0,0,0.72) 70%, #000 100%)",
          }} />
        </div>

        {/* Aceternity spotlight sweep (absolute, clipped here too) */}
        <div style={{ position: "absolute", inset: 0, zIndex: 1, pointerEvents: "none", overflow: "hidden" }}>
          <Spotlight className="-top-40 left-0 md:left-60 md:-top-20" fill="white" />
        </div>

        {/* Subtle grid (absolute) */}
        <div style={{
          pointerEvents: "none", position: "absolute", inset: 0, zIndex: 1,
          backgroundImage: "linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }} />

        {/* Hero copy */}
        <div style={{ position: "relative", zIndex: 10, textAlign: "center", padding: isMobile ? "48px 20px 56px" : "72px 32px 80px", maxWidth: 960, margin: "0 auto", width: "100%" }}>

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              borderRadius: 999, border: "1px solid rgba(255,255,255,0.09)",
              background: "rgba(255,255,255,0.03)",
              padding: "6px 16px", fontSize: 12, fontWeight: 500, color: "rgba(255,255,255,0.5)",
              marginBottom: 36,
            }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#fff", opacity: 0.6, display: "inline-block" }} />
              Multi-venue · Risk-first · LLM-powered
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            style={{ fontSize: "clamp(44px, 7vw, 80px)", fontWeight: 800, lineHeight: 1.04, letterSpacing: "-0.04em", marginBottom: 28 }}
          >
            The AI Agent That{" "}
            <span style={{ color: "rgba(255,255,255,0.35)" }}>Trades While You Sleep.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.35 }}
            style={{ fontSize: 17, color: "rgba(255,255,255,0.38)", lineHeight: 1.65, maxWidth: 560, marginBottom: 40, margin: "0 auto 40px" }}
          >
            {APP_NAME} connects to Hyperliquid, Binance, OANDA, and 100+ exchanges.
            Every decision is made by an LLM with full technical context and enforced
            by conservative risk rules before any order hits the wire.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.5 }}
            style={{ display: "flex", alignItems: "center", gap: isMobile ? 10 : 14, flexWrap: "wrap", justifyContent: "center", marginBottom: isMobile ? 40 : 64 }}
          >
            <Link href="/sign-up" style={{ ...btnPrimary, padding: "14px 32px", fontSize: 15, borderRadius: 14 }}>
              Start Free <ArrowRight size={16} />
            </Link>
            <Link href="/dashboard" style={{ ...btnOutline, padding: "14px 32px", fontSize: 15, borderRadius: 14 }}>
              Open Dashboard
            </Link>
            <Link href="#pricing" style={{ ...btnGhost, padding: "14px 20px", fontSize: 14, borderRadius: 14, border: "1px solid rgba(255,255,255,0.08)" }}>
              View Plans
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.7 }}
            style={{ display: "flex", alignItems: "center", gap: isMobile ? 28 : 56, flexWrap: "wrap", justifyContent: "center" }}
          >
            {[
              { n: "100+", label: "Exchanges" },
              { n: "5",    label: "LLM Providers" },
              { n: "24/7", label: "Autonomous" },
              { n: "≤ 2×", label: "Leverage Cap" },
            ].map(({ n, label }) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.03em" }}>{n}</div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>
      {/* ══════════════════════════════════════════════════════════════
          BELOW THE FOLD — plain black, no neural bg
      ══════════════════════════════════════════════════════════════ */}

      {/* Infinite slider */}
      <div style={{ position: "relative", padding: "32px 0", overflow: "hidden", background: "#000" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 120, zIndex: 10, background: "linear-gradient(to right, #000, transparent)" }} />
        <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 120, zIndex: 10, background: "linear-gradient(to left, #000, transparent)" }} />
        <InfiniteSlider duration={28} gap={40}>
          {SLIDER_ITEMS.map((item) => (
            <span key={item} style={{ display: "flex", alignItems: "center", gap: 10, whiteSpace: "nowrap", fontSize: 13, fontWeight: 500, color: "rgba(255,255,255,0.2)", userSelect: "none" }}>
              <span style={{ width: 4, height: 4, borderRadius: "50%", background: "rgba(255,255,255,0.2)", flexShrink: 0 }} />
              {item}
            </span>
          ))}
        </InfiniteSlider>
      </div>

      {/* Feature cards */}
      <section id="features" style={{ padding: isMobile ? "48px 16px" : "80px 32px", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          style={{ fontSize: "clamp(28px, 4vw, 42px)", fontWeight: 700, textAlign: "center", marginBottom: 12, letterSpacing: "-0.03em" }}
        >
          Built for serious traders and new ones.
        </motion.h2>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.1 }}
          style={{ textAlign: "center", color: "rgba(255,255,255,0.3)", fontSize: 16, marginBottom: 48 }}
        >
          Every layer designed to protect capital first and grow it second.
        </motion.p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))", gap: 18 }}>
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              style={{ borderRadius: 20, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)", padding: "32px 28px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <ChevronRight size={14} style={{ color: "rgba(255,255,255,0.25)" }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  {f.title}
                </span>
              </div>
              <p style={{ color: "rgba(255,255,255,0.35)", fontSize: 14, lineHeight: 1.7 }}>{f.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Pricing ───────────────────────────────────────────── */}
      <section id="pricing" style={{ padding: isMobile ? "48px 16px" : "80px 32px", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <motion.h2
          initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }} transition={{ duration: 0.6 }}
          style={{ fontSize: "clamp(28px, 4vw, 42px)", fontWeight: 700, textAlign: "center", marginBottom: 12, letterSpacing: "-0.03em" }}
        >
          Simple, transparent pricing.
        </motion.h2>
        <motion.p
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }}
          viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.1 }}
          style={{ textAlign: "center", color: "rgba(255,255,255,0.3)", fontSize: 16, marginBottom: 52 }}
        >
          Start free. Scale when you&apos;re ready.
        </motion.p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", gap: 16 }}>
          {[
            {
              name: "Free",
              price: "$0",
              period: "forever",
              tag: null,
              desc: "Learn the system risk-free.",
              features: [
                "Paper trading & testnet only",
                "1 venue (Hyperliquid testnet)",
                "Up to 2 assets",
                "1 AI agent (Groq LLaMA)",
                "30-day backtesting",
                "Community support",
              ],
              cta: "Start Free",
              href: "/sign-up",
              highlight: false,
            },
            {
              name: "Starter",
              price: "$20",
              period: "/ month",
              tag: null,
              desc: "Your first live deployment.",
              features: [
                "Live trading on 1 venue",
                "Up to 5 assets",
                "2 AI agents (Groq + Gemini)",
                "90-day backtesting",
                "Email alerts",
                "Dashboard access",
              ],
              cta: "Get Starter",
              href: "/sign-up",
              highlight: false,
            },
            {
              name: "Pro",
              price: "$99",
              period: "/ month",
              tag: "Most Popular",
              desc: "Full council, multi-venue.",
              features: [
                "Live trading on 3 venues",
                "Up to 15 assets",
                "Full AI council (3 agents)",
                "1-year backtesting",
                "Telegram + email alerts",
                "Per-venue risk config",
                "Priority support",
              ],
              cta: "Get Pro",
              href: "/sign-up",
              highlight: true,
            },
            {
              name: "Enterprise",
              price: "$199",
              period: "/ month",
              tag: null,
              desc: "Unlimited scale and control.",
              features: [
                "Unlimited venues",
                "Unlimited assets",
                "Full AI council (5+ agents)",
                "Custom model weighting",
                "Unlimited backtesting",
                "All alert channels",
                "Dedicated support",
              ],
              cta: "Get Enterprise",
              href: "/sign-up",
              highlight: false,
            },
          ].map((tier, i) => (
            <motion.div
              key={tier.name}
              initial={{ opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.5, delay: i * 0.08 }}
              style={{
                borderRadius: 22,
                border: tier.highlight ? "1px solid rgba(255,255,255,0.3)" : "1px solid rgba(255,255,255,0.07)",
                background: tier.highlight ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.02)",
                padding: "30px 26px",
                display: "flex", flexDirection: "column", gap: 0,
                position: "relative",
              }}
            >
              {tier.tag && (
                <span style={{
                  position: "absolute", top: -11, left: "50%", transform: "translateX(-50%)",
                  background: "#fff", color: "#000", fontSize: 10, fontWeight: 700,
                  padding: "3px 12px", borderRadius: 999, letterSpacing: "0.08em",
                  textTransform: "uppercase", whiteSpace: "nowrap",
                }}>{tier.tag}</span>
              )}

              <div style={{ marginBottom: 20 }}>
                <p style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.35)", marginBottom: 10 }}>{tier.name}</p>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 6 }}>
                  <span style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.04em" }}>{tier.price}</span>
                  <span style={{ fontSize: 13, color: "rgba(255,255,255,0.35)" }}>{tier.period}</span>
                </div>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>{tier.desc}</p>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: 18, marginBottom: 24, flex: 1 }}>
                {tier.features.map(f => (
                  <div key={f} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
                    <span style={{ color: "rgba(255,255,255,0.35)", fontSize: 14, marginTop: 1, flexShrink: 0 }}>✓</span>
                    <span style={{ fontSize: 13, color: "rgba(255,255,255,0.45)", lineHeight: 1.45 }}>{f}</span>
                  </div>
                ))}
              </div>

              <Link href={tier.href} style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                padding: "12px 0", borderRadius: 12, textDecoration: "none",
                fontWeight: 600, fontSize: 14, transition: "opacity .15s",
                background: tier.highlight ? "#fff" : "transparent",
                color: tier.highlight ? "#000" : "rgba(255,255,255,0.6)",
                border: tier.highlight ? "none" : "1px solid rgba(255,255,255,0.12)",
              }}>
                {tier.cta} {tier.highlight && <ArrowRight size={14} />}
              </Link>
            </motion.div>
          ))}
        </div>

        <p style={{ textAlign: "center", fontSize: 12, color: "rgba(255,255,255,0.2)", marginTop: 28 }}>
          All plans include a 14-day free trial. No credit card required to start.
        </p>
      </section>

      {/* CTA strip */}
      <section style={{ position: "relative", padding: isMobile ? "48px 20px" : "80px 32px", textAlign: "center" }}>
        <div style={{ pointerEvents: "none", position: "absolute", inset: 0, background: "radial-gradient(ellipse 60% 80% at 50% 50%, rgba(255,255,255,0.03) 0%, transparent 70%)" }} />
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          style={{ position: "relative" }}
        >
          <h2 style={{ fontSize: "clamp(32px, 5vw, 52px)", fontWeight: 800, marginBottom: 16, letterSpacing: "-0.04em" }}>
            Ready to automate?
          </h2>
          <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 16, maxWidth: 400, margin: "0 auto 36px" }}>
            Configure your venue, set your risk limits, and let the AI run.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <Link href="/sign-up" style={{ ...btnPrimary, padding: "14px 32px", fontSize: 15, borderRadius: 14 }}>
              Get Started Free <ArrowRight size={16} />
            </Link>
            <Link href="/dashboard" style={{ ...btnOutline, padding: "14px 32px", fontSize: 15, borderRadius: 14 }}>
              Open Dashboard
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: "1px solid rgba(255,255,255,0.06)", padding: isMobile ? "20px 16px" : "28px 32px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <LogoWordmark size={26} />
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.2)" }}>
            Groq · Hyperliquid · Binance · OANDA
          </span>
        </div>
      </footer>
    </div>
  );
}
