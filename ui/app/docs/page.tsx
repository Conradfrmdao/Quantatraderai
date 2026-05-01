'use client';

import Link from "next/link";
import { motion } from "framer-motion";
import { LogoWordmark } from "@/components/Logo";
import { ArrowRight, ChevronRight } from "lucide-react";

const Section = ({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) => (
  <section id={id} style={{ marginBottom: 56 }}>
    <h2 style={{ fontSize: 22, fontWeight: 700, color: "#fff", marginBottom: 16, letterSpacing: "-0.02em", borderLeft: "2px solid rgba(255,255,255,0.2)", paddingLeft: 16 }}>
      {title}
    </h2>
    <div style={{ color: "rgba(255,255,255,0.48)", fontSize: 14, lineHeight: 1.9, paddingLeft: 18 }}>
      {children}
    </div>
  </section>
);

const P = ({ children }: { children: React.ReactNode }) => <p style={{ marginBottom: 14 }}>{children}</p>;

const Li = ({ children }: { children: React.ReactNode }) => (
  <li style={{ marginBottom: 8, paddingLeft: 16, position: "relative" }}>
    <span style={{ position: "absolute", left: 0, color: "rgba(255,255,255,0.25)" }}>→</span>
    {children}
  </li>
);

const Step = ({ n, title, children }: { n: number; title: string; children: React.ReactNode }) => (
  <li style={{ display: "flex", gap: 16, marginBottom: 28 }}>
    <span style={{
      minWidth: 28, height: 28, borderRadius: "50%",
      border: "1px solid rgba(255,255,255,0.15)",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 12, fontWeight: 700, color: "rgba(255,255,255,0.5)",
      flexShrink: 0, marginTop: 1,
    }}>{n}</span>
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.75)", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13, color: "rgba(255,255,255,0.42)", lineHeight: 1.8 }}>{children}</div>
    </div>
  </li>
);

const Tip = ({ children }: { children: React.ReactNode }) => (
  <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 12, padding: "14px 18px", marginTop: 12 }}>
    <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", margin: 0, lineHeight: 1.7 }}>{children}</p>
  </div>
);

const TOC = [
  { id: "how-it-works",  label: "How QuntaTradeAI Works" },
  { id: "ai-council",    label: "The AI Council" },
  { id: "venues",        label: "Supported Venues" },
  { id: "quickstart",   label: "Getting Started" },
  { id: "connect",       label: "Connecting Your Exchange" },
  { id: "risk",          label: "Risk Configuration" },
  { id: "paper",         label: "Paper Trading" },
  { id: "live",          label: "Going Live" },
  { id: "faq",           label: "FAQ" },
];

export default function DocsPage() {
  return (
    <div style={{ background: "#000", color: "#fff", minHeight: "100vh" }}>
      <nav style={{
        position: "sticky", top: 0, zIndex: 50,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "rgba(0,0,0,0.9)", backdropFilter: "blur(20px)",
        padding: "0 32px", height: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <LogoWordmark size={28} />
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <Link href="/terms" style={{ fontSize: 13, color: "rgba(255,255,255,0.35)", textDecoration: "none" }}>Terms</Link>
          <Link href="/dashboard" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "rgba(255,255,255,0.35)", textDecoration: "none" }}>
            Dashboard <ArrowRight size={13} />
          </Link>
        </div>
      </nav>

      <div style={{ maxWidth: 1060, margin: "0 auto", padding: "56px 32px 96px", display: "grid", gridTemplateColumns: "200px 1fr", gap: 56, alignItems: "start" }}>

        {/* Sidebar TOC */}
        <aside style={{ position: "sticky", top: 80 }}>
          <p style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.25)", marginBottom: 12 }}>
            On this page
          </p>
          <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {TOC.map(t => (
              <a key={t.id} href={`#${t.id}`} style={{ fontSize: 13, color: "rgba(255,255,255,0.35)", textDecoration: "none", padding: "4px 0", display: "flex", alignItems: "center", gap: 6, transition: "color .15s" }}>
                <ChevronRight size={12} style={{ opacity: 0.4 }} />{t.label}
              </a>
            ))}
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", marginTop: 12, paddingTop: 12 }}>
              <Link href="/terms" style={{ fontSize: 12, color: "rgba(255,255,255,0.2)", textDecoration: "none" }}>Terms &amp; Conditions →</Link>
            </div>
          </nav>
        </aside>

        {/* Main content */}
        <motion.main initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>

          <div style={{ marginBottom: 52 }}>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)" }}>Documentation</span>
            <h1 style={{ fontSize: "clamp(26px, 4vw, 38px)", fontWeight: 800, letterSpacing: "-0.03em", marginTop: 8, marginBottom: 10 }}>
              QuntaTradeAI Docs
            </h1>
            <p style={{ fontSize: 15, color: "rgba(255,255,255,0.38)", lineHeight: 1.6 }}>
              Everything you need to connect your exchange, configure risk, and let the AI trade on your behalf — no technical background required.
            </p>
          </div>

          {/* ── How it works ── */}
          <Section id="how-it-works" title="How QuntaTradeAI Works">
            <P>
              QuntaTradeAI is a fully autonomous trading agent that connects to your exchange accounts
              and trades on your behalf around the clock. Every few minutes the system:
            </P>
            <ul style={{ listStyle: "none", marginBottom: 16 }}>
              <Li>Pulls live price data, order book depth, and funding rates for every asset you selected</Li>
              <Li>Computes a full suite of technical indicators — RSI, MACD, ATR, Bollinger Bands, EMA</Li>
              <Li>Submits the full market picture to a panel of AI models for independent analysis</Li>
              <Li>Reaches a consensus decision and validates it against your personal risk limits</Li>
              <Li>Places the order (or skips, if the risk check fails) and logs the reasoning</Li>
            </ul>
            <P>
              Once set up, the agent runs continuously without any action from you. You watch the
              dashboard, review decisions, and adjust settings at any time.
            </P>
          </Section>

          {/* ── AI Council ── */}
          <Section id="ai-council" title="The AI Council — Collective Intelligence">
            <P>
              Most AI trading tools rely on a single model. QuntaTradeAI uses a{" "}
              <strong style={{ color: "rgba(255,255,255,0.7)" }}>multi-model consensus architecture</strong>.
              Several independent AI agents, each with different training data and reasoning styles,
              analyse the same market snapshot simultaneously and vote on what to do.
            </P>

            <div style={{ border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "20px 24px", marginBottom: 20, background: "rgba(255,255,255,0.02)" }}>
              <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 14 }}>
                Active AI Agents
              </p>
              {[
                { name: "Claude (Anthropic)",        note: "Constitutional reasoning, strong risk assessment" },
                { name: "LLaMA 3.3 70B via Groq",   note: "Ultra-fast inference, broad financial training" },
                { name: "Gemini Pro (Google)",        note: "Macro-economic awareness, multi-modal context" },
                { name: "OpenRouter gateway",         note: "50+ additional models available as fallback" },
              ].map(a => (
                <div key={a.name} style={{ display: "flex", gap: 12, marginBottom: 10 }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: "rgba(255,255,255,0.4)", flexShrink: 0, marginTop: 5 }} />
                  <div>
                    <span style={{ fontSize: 13, color: "rgba(255,255,255,0.7)", fontWeight: 600 }}>{a.name}</span>
                    <span style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", marginLeft: 8 }}>— {a.note}</span>
                  </div>
                </div>
              ))}
            </div>

            <P>
              Each agent independently returns a structured decision — buy, sell, or hold — along
              with a confidence score, suggested allocation, and its reasoning. The consensus engine then:
            </P>
            <ul style={{ listStyle: "none", marginBottom: 16 }}>
              <Li>Weights each vote by that model&apos;s recent accuracy on the same asset class</Li>
              <Li>Discards outlier votes that deviate significantly from the group</Li>
              <Li>Requires a 60% supermajority before any buy or sell is executed</Li>
              <Li>Defaults to hold when consensus cannot be reached — protecting your capital by inaction</Li>
            </ul>
            <P>
              This eliminates single-model blind spots, reduces false signals, and produces decisions with
              meaningfully higher confidence than any individual model alone. Every decision and its
              rationale is visible in real time on your dashboard.
            </P>
          </Section>

          {/* ── Venues ── */}
          <Section id="venues" title="Supported Venues">
            <P>Connect any combination of these exchanges and brokers — simultaneously if you wish:</P>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
              {[
                { name: "Hyperliquid",       type: "Crypto Perpetuals",         badge: "Decentralised" },
                { name: "Binance Futures",   type: "Crypto USD-M Perps",        badge: "Centralised" },
                { name: "Binance Spot",      type: "Crypto Spot Trading",       badge: "Centralised" },
                { name: "OANDA",             type: "Forex — 70+ pairs",         badge: "Regulated" },
                { name: "MetaTrader 4/5",    type: "Forex / CFDs / Indices",    badge: "MetaAPI" },
                { name: "Alpaca",            type: "US Stocks + Crypto",        badge: "Commission-free" },
                { name: "IBKR",              type: "Stocks / Options / Futures", badge: "Advanced" },
                { name: "Polymarket",        type: "Binary Prediction Markets", badge: "Polygon" },
                { name: "100+ via CCXT",     type: "Bybit, OKX, Kraken, KuCoin…", badge: "Multi" },
              ].map(v => (
                <div key={v.name} style={{ border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, padding: "14px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.75)" }}>{v.name}</div>
                    <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)", background: "rgba(255,255,255,0.05)", padding: "2px 8px", borderRadius: 20 }}>{v.badge}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.35)" }}>{v.type}</div>
                </div>
              ))}
            </div>
            <P>
              You connect each venue through the <strong style={{ color: "rgba(255,255,255,0.6)" }}>Settings → Connected Venues</strong> page
              using only an API key and secret — no other setup required.
            </P>
          </Section>

          {/* ── Quick Start ── */}
          <Section id="quickstart" title="Getting Started — Four Steps">
            <ol style={{ listStyle: "none", marginBottom: 0 }}>
              <Step n={1} title="Create your account">
                Sign up with your email at the top of this page. You&apos;ll be guided through a short onboarding
                to personalise your experience. No credit card required.
              </Step>
              <Step n={2} title="Connect your exchange">
                Go to <strong style={{ color: "rgba(255,255,255,0.6)" }}>Settings → Connected Venues</strong> and
                add your API key for any supported exchange. Your keys are encrypted end-to-end and never stored
                in plain text. See the next section for how to generate a safe API key on each platform.
              </Step>
              <Step n={3} title="Review your risk limits">
                Go to <strong style={{ color: "rgba(255,255,255,0.6)" }}>Settings → Risk Settings</strong>.
                The defaults are conservative — 3% max position, 2x leverage, 2.5% mandatory stop-loss.
                Adjust only once you understand how the system behaves in your market conditions.
              </Step>
              <Step n={4} title="Start the agent">
                Return to the <strong style={{ color: "rgba(255,255,255,0.6)" }}>Dashboard</strong> and click
                <strong style={{ color: "rgba(255,255,255,0.6)" }}> Start Agent</strong>. Enable Paper Trading
                first to watch the agent make real decisions with no capital at risk.
              </Step>
            </ol>
          </Section>

          {/* ── Connect venues ── */}
          <Section id="connect" title="Connecting Your Exchange — API Key Guide">
            <P>
              QuntaTradeAI connects to exchanges via API keys. You always stay in control — the agent can
              only place and close orders, <strong style={{ color: "rgba(255,255,255,0.7)" }}>never withdraw funds</strong>.
              Follow the guide for your exchange:
            </P>

            {[
              {
                name: "Hyperliquid",
                steps: [
                  "Go to app.hyperliquid.xyz and connect your wallet.",
                  "Navigate to Settings → API and click Generate API Wallet. This creates a key scoped only to trading — it cannot withdraw funds from your account.",
                  "Copy the generated private key and your main account address.",
                  "Paste both into Settings → Connected Venues → Add Venue (type: Hyperliquid).",
                  "Start with the Testnet toggle ON to validate the connection before using real funds.",
                ],
                tip: "The Hyperliquid API wallet is revocable at any time from Settings → API on their platform.",
              },
              {
                name: "Binance",
                steps: [
                  "Log in to binance.com. Go to Account → API Management and click Create API.",
                  "Enable Spot & Margin Trading and Enable Futures only. Never enable withdrawal permissions.",
                  "Restrict the key to your IP address under IP Access Restriction for extra security.",
                  "Copy the API Key and Secret Key (the secret is shown only once).",
                  "Paste both into Settings → Connected Venues → Add Venue (type: Binance).",
                ],
                tip: "Use the Binance Futures Testnet first — it's a free sandbox with play-money balances that behaves exactly like the live exchange.",
              },
              {
                name: "OANDA (Forex)",
                steps: [
                  "Go to oanda.com and open a free Practice Account — no ID or funding required.",
                  "Log in and go to My Account → Manage API Access.",
                  "Click Generate under Personal Access Token and copy the token.",
                  "Find your Account ID on the OANDA dashboard (a number like 101-001-12345678-001).",
                  "Paste both into Settings → Connected Venues → Add Venue (type: OANDA). Leave mode set to Practice.",
                ],
                tip: "OANDA practice accounts mirror live market conditions exactly. Trade with them for at least a week before switching to a live account.",
              },
              {
                name: "MetaTrader 4/5 (via MetaAPI)",
                steps: [
                  "Sign up free at app.metaapi.cloud. No credit card required for the basic tier.",
                  "In the MetaAPI dashboard, click 'Add MT account' and select your broker from the list.",
                  "Enter your MT4 or MT5 login credentials. MetaAPI connects to your broker on your behalf.",
                  "Once the account is synchronised, copy your MetaAPI Token and MT Account ID from the dashboard.",
                  "Paste both into Settings → Connected Venues → Add Venue (type: MetaTrader).",
                ],
                tip: "MetaAPI supports over 500 brokers including IC Markets, Pepperstone, XM, and IG. A free MetaAPI account includes 1 demo MT account at no cost.",
              },
              {
                name: "Alpaca (US Stocks & Crypto)",
                steps: [
                  "Create a free account at app.alpaca.markets. Paper trading is enabled immediately.",
                  "In the Alpaca dashboard, go to Overview and click 'Your API Keys' on the right side.",
                  "Click 'Generate New Key'. Copy both the API Key ID and Secret Key (the secret is shown once).",
                  "For paper trading, use the paper keys (URL contains 'paper-api.alpaca.markets').",
                  "Paste both into Settings → Connected Venues → Add Venue (type: Alpaca).",
                ],
                tip: "Alpaca paper trading is free and mirrors live market data. Switch to a live account by depositing funds and generating a live key from the same dashboard.",
              },
              {
                name: "Interactive Brokers (IBKR)",
                steps: [
                  "Download and install Trader Workstation (TWS) or IB Gateway from interactivebrokers.com.",
                  "Log in to TWS / IB Gateway and go to Edit → Global Configuration → API → Settings.",
                  "Enable 'ActiveX and Socket Clients'. Note the port (default 7497 for paper, 7496 for live).",
                  "Set 'Client ID' to 0 or any unique number (used to identify the app connection).",
                  "In QuntaTradeAI Settings → Connected Venues, add IBKR and set host (127.0.0.1), port, and client ID.",
                ],
                tip: "IBKR requires TWS or IB Gateway to be running on the same machine as the QuntaTradeAI backend. It is not compatible with cloud-only deployments. Use IB Gateway (lighter than TWS) for server use.",
              },
              {
                name: "Polymarket (Prediction Markets)",
                steps: [
                  "Create a fresh Ethereum wallet (e.g. MetaMask → 'Create new account'). Do NOT use your main wallet.",
                  "Fund this new wallet with USDC on Polygon (Matic chain). You can bridge from Ethereum at app.polymarket.com.",
                  "Export the private key from MetaMask: Account Details → Show Private Key. It starts with 0x.",
                  "Paste the private key into Settings → Connected Venues → Add Venue (type: Polymarket).",
                  "Start with Paper mode — no funds are moved while paper trading is active.",
                ],
                tip: "Always use a dedicated trading wallet for Polymarket — never paste the private key of a wallet that holds significant funds. Your key is encrypted with AES-256-GCM before storage. Connect Wallet (MetaMask in-browser) is coming soon to avoid pasting keys entirely.",
              },
              {
                name: "Other Exchanges (Kraken, OKX, Bybit, KuCoin, Gate.io…)",
                steps: [
                  "Create an API key on your chosen exchange — enable trade permissions only, no withdrawals.",
                  "IP-whitelist the key where the exchange allows it.",
                  "Add it in Settings → Connected Venues → Add Venue, choose the correct exchange from the CCXT dropdown.",
                  "Some exchanges (Coinbase, OKX) also require a Passphrase — enter it in the optional Passphrase field.",
                ],
                tip: "Over 100 exchanges are supported. If yours is not shown as a native option, select CCXT and pick your exchange from the list.",
              },
            ].map(v => (
              <div key={v.name} style={{ marginBottom: 36 }}>
                <p style={{ fontSize: 14, fontWeight: 700, color: "rgba(255,255,255,0.7)", marginBottom: 12 }}>{v.name}</p>
                <ol style={{ listStyle: "none" }}>
                  {v.steps.map((s, i) => <Step key={i} n={i + 1} title="">{s}</Step>)}
                </ol>
                <Tip>💡 {v.tip}</Tip>
              </div>
            ))}
          </Section>

          {/* ── Risk ── */}
          <Section id="risk" title="Risk Configuration — Protect Your Capital">
            <P>
              Every order the agent attempts is validated against your personal risk rules before it
              reaches the exchange. If any rule is violated, the order is blocked and logged — no exceptions.
            </P>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
              {[
                { label: "Max position size",        value: "3% of equity", note: "Limits any single trade" },
                { label: "Max leverage",             value: "2×",           note: "Caps borrowed exposure" },
                { label: "Mandatory stop-loss",      value: "2.5%",         note: "Every trade must have one" },
                { label: "Auto-close threshold",     value: "−8%",          note: "Closes if position falls here" },
                { label: "Daily circuit breaker",    value: "−4%",          note: "Halts trading for the day" },
                { label: "Max open positions",       value: "5",            note: "No more than 5 at once" },
              ].map(r => (
                <div key={r.label} style={{ border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, padding: "14px 16px" }}>
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", marginBottom: 4 }}>{r.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 2 }}>{r.value}</div>
                  <div style={{ fontSize: 11, color: "rgba(255,255,255,0.25)" }}>{r.note}</div>
                </div>
              ))}
            </div>

            <P>
              These defaults are intentionally conservative. You can change any of them in
              <strong style={{ color: "rgba(255,255,255,0.6)" }}> Settings → Risk Settings</strong>.
              Changes take effect immediately — the running agent picks them up on the next tick.
            </P>
            <Tip>
              ⚠️ We strongly recommend leaving these at their defaults until you have at least two weeks of
              paper trading history to review. The defaults are designed to survive a bad week without
              significant capital loss.
            </Tip>
          </Section>

          {/* ── Paper trading ── */}
          <Section id="paper" title="Paper Trading — Test Without Risk">
            <P>
              <strong style={{ color: "rgba(255,255,255,0.7)" }}>
                QuntaTradeAI lets you run the full system — live AI council, real market data, real signals —
                without risking any money.
              </strong>{" "}
              In paper trading mode, every decision is logged and simulated positions are tracked on the
              dashboard exactly as they would be in a live account. Nothing touches your exchange balance.
            </P>
            <ul style={{ listStyle: "none", marginBottom: 16 }}>
              <Li>Toggle paper mode per venue in <strong style={{ color: "rgba(255,255,255,0.6)" }}>Settings → Connected Venues</strong> — flip the Paper / Live switch</Li>
              <Li>The dashboard shows virtual PnL, open positions, and all AI decisions in real time</Li>
              <Li>Paper mode and live mode can run simultaneously on different venues</Li>
              <Li>All risk rules still apply in paper mode — so the behaviour you observe is identical to live</Li>
            </ul>
            <Tip>
              💡 Run paper trading for at least 2 weeks before going live. Watch how the agent handles a
              volatile day, a trending market, and a choppy sideways period before trusting it with
              real capital.
            </Tip>
          </Section>

          {/* ── Going live ── */}
          <Section id="live" title="Going Live — Checklist">
            <P>Before switching any venue from Paper to Live, confirm:</P>
            <ul style={{ listStyle: "none", marginBottom: 16 }}>
              <Li>You have reviewed at least 2 weeks of paper trading decisions and are satisfied with the strategy</Li>
              <Li>Your risk limits in Settings are set to values you are comfortable with</Li>
              <Li>Your API key has <strong style={{ color: "rgba(255,255,255,0.6)" }}>no withdrawal permissions</strong> — trading only</Li>
              <Li>You have funded your exchange account with an amount you can afford to lose entirely</Li>
              <Li>You understand that past paper performance does not guarantee future live results</Li>
            </ul>
            <P>
              When ready, go to <strong style={{ color: "rgba(255,255,255,0.6)" }}>Settings → Connected Venues</strong>,
              find your venue, and flip the switch from Paper to Live. The agent will begin placing real orders
              on the next tick.
            </P>
            <Tip>
              ⚠️ Start with the smallest viable capital allocation. You can always add more once you have
              confirmed the system is behaving as expected on your account.
            </Tip>
          </Section>

          {/* ── FAQ ── */}
          <Section id="faq" title="FAQ">
            {[
              {
                q: "Do I need any technical knowledge to use QuntaTradeAI?",
                a: "No. Setup takes about 5 minutes — create an account, connect your exchange API key, and click Start Agent. Everything else is automatic.",
              },
              {
                q: "Are my API keys safe?",
                a: "Yes. Keys are encrypted end-to-end with AES-256-GCM before being stored. They are never visible to our servers in plain text, and only used to place orders on your behalf.",
              },
              {
                q: "Can the agent withdraw my funds?",
                a: "No, and you should ensure it never can. When generating an API key on any exchange, enable trade permissions only — never enable withdrawals. Our guide above walks through this for each exchange.",
              },
              {
                q: "What happens if the AI models disagree?",
                a: "The consensus engine requires a 60% supermajority to act. If the AI council cannot agree, the agent holds and logs the disagreement. Your capital is protected by inaction.",
              },
              {
                q: "Can I trade forex and crypto at the same time?",
                a: "Yes. Connect multiple venues and they all run simultaneously. Each venue has its own paper/live toggle, risk profile, and AI decisions shown on the dashboard.",
              },
              {
                q: "What happens if an exchange goes down or loses connection?",
                a: "The agent catches the error, skips that tick, and retries automatically on the next interval. Open positions are not affected. You will see the error logged in the dashboard.",
              },
              {
                q: "Can I stop the agent at any time?",
                a: "Yes. Click Stop Agent on the dashboard at any time. Open positions remain open — the agent simply stops placing new orders until you restart it.",
              },
              {
                q: "What is the minimum amount I need to start?",
                a: "There is no minimum set by QuntaTradeAI. Each exchange has its own minimum order size (typically $10–$50 per trade). With a 3% max position size, you would need at least $300–$1,000 to place a meaningful first trade.",
              },
            ].map(({ q, a }) => (
              <div key={q} style={{ marginBottom: 24, paddingBottom: 24, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <p style={{ fontSize: 14, fontWeight: 600, color: "rgba(255,255,255,0.65)", marginBottom: 8 }}>{q}</p>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.38)", lineHeight: 1.7 }}>{a}</p>
              </div>
            ))}
          </Section>

          <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 32, display: "flex", gap: 24, flexWrap: "wrap" }}>
            <Link href="/" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>← Home</Link>
            <Link href="/dashboard" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>Dashboard →</Link>
            <Link href="/terms" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>Terms &amp; Conditions</Link>
          </div>

        </motion.main>
      </div>
    </div>
  );
}
