'use client';

import Link from "next/link";
import { motion } from "framer-motion";
import { LogoWordmark } from "@/components/Logo";
import { ArrowLeft } from "lucide-react";

const LAST_UPDATED = "18 April 2026";
const COMPANY = "QuantaTrade AI";
const CONTACT_EMAIL = "legal@quntatrade.ai";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section style={{ marginBottom: 48 }}>
    <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 14, letterSpacing: "-0.02em" }}>
      {title}
    </h2>
    <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 14, lineHeight: 1.9 }}>
      {children}
    </div>
  </section>
);

const P = ({ children }: { children: React.ReactNode }) => (
  <p style={{ marginBottom: 12 }}>{children}</p>
);

const Li = ({ children }: { children: React.ReactNode }) => (
  <li style={{ marginBottom: 8, paddingLeft: 16, position: "relative" }}>
    <span style={{ position: "absolute", left: 0, color: "rgba(255,255,255,0.3)" }}>·</span>
    {children}
  </li>
);

export default function TermsPage() {
  return (
    <div style={{ background: "#000", color: "#fff", minHeight: "100vh" }}>

      {/* Navbar */}
      <nav style={{
        position: "sticky", top: 0, zIndex: 50,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "rgba(0,0,0,0.9)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        padding: "0 32px", height: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <LogoWordmark size={28} />
        <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "rgba(255,255,255,0.4)", textDecoration: "none" }}>
          <ArrowLeft size={14} /> Back to home
        </Link>
      </nav>

      <main style={{ maxWidth: 760, margin: "0 auto", padding: "64px 32px 96px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>

          <div style={{ marginBottom: 48 }}>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)" }}>Legal</span>
            <h1 style={{ fontSize: "clamp(28px, 4vw, 42px)", fontWeight: 800, letterSpacing: "-0.03em", marginTop: 8, marginBottom: 10 }}>
              Terms &amp; Conditions
            </h1>
            <p style={{ fontSize: 13, color: "rgba(255,255,255,0.3)" }}>Last updated: {LAST_UPDATED}</p>
          </div>

          {/* CRITICAL WARNING */}
          <div style={{
            border: "1px solid rgba(255,255,255,0.12)",
            background: "rgba(255,255,255,0.03)",
            borderRadius: 16, padding: "20px 24px", marginBottom: 48,
          }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.8)", marginBottom: 8 }}>
              ⚠ Important Notice
            </p>
            <p style={{ fontSize: 13, color: "rgba(255,255,255,0.45)", lineHeight: 1.7 }}>
              {COMPANY} is a software tool for educational and research purposes only. It does not constitute
              financial advice, investment advice, trading advice, or any other advice. All trading involves
              substantial risk of loss. Past performance of any AI model or strategy is not indicative of
              future results. Never trade with money you cannot afford to lose.
            </p>
          </div>

          <Section title="1. Acceptance of Terms">
            <P>
              By accessing or using {COMPANY} (&quot;the Service&quot;, &quot;the Platform&quot;, &quot;the Software&quot;), you
              (&quot;User&quot;, &quot;you&quot;) agree to be bound by these Terms and Conditions (&quot;Terms&quot;). If you do
              not agree to all of these Terms, you must not access or use the Service.
            </P>
            <P>
              These Terms constitute a legally binding agreement between you and {COMPANY} (&quot;Company&quot;,
              &quot;we&quot;, &quot;us&quot;, &quot;our&quot;). We reserve the right to modify these Terms at any time. Continued
              use of the Service after any modification constitutes acceptance of the revised Terms.
            </P>
          </Section>

          <Section title="2. Nature of Service — Not Financial Advice">
            <P>
              <strong style={{ color: "rgba(255,255,255,0.75)" }}>{COMPANY} is not a registered investment adviser, broker-dealer, financial planner, or any
              regulated financial entity in any jurisdiction.</strong> The Service is an automated software
              platform for educational and research purposes.
            </P>
            <P>
              Nothing on this platform constitutes, or should be construed as:
            </P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>Financial advice, investment advice, or trading advice</Li>
              <Li>A recommendation to buy, sell, or hold any financial instrument</Li>
              <Li>A solicitation of any investment</Li>
              <Li>An offer or sale of any security, derivative, or commodity</Li>
            </ul>
            <P>
              All AI-generated trade signals, decisions, and analysis are provided solely for
              informational and educational purposes. You should consult a qualified, licensed financial
              adviser before making any investment or trading decisions.
            </P>
          </Section>

          <Section title="3. Risk Warning">
            <P>
              <strong style={{ color: "rgba(255,255,255,0.75)" }}>Trading financial instruments including cryptocurrencies,
              forex, derivatives, and leveraged products carries a high level of risk and may not be
              suitable for all investors.</strong> You may lose some or all of your invested capital. You should
              not trade with money you cannot afford to lose.
            </P>
            <P>Specific risks associated with {COMPANY} include but are not limited to:</P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>AI / Model Risk:</strong> AI models can and do make incorrect predictions. No AI system has a perfect trading record. Model outputs are probabilistic and not guarantees of profit.</Li>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>Leverage Risk:</strong> Leveraged trading amplifies both gains and losses. A small adverse market movement can result in the loss of your entire position.</Li>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>Technology Risk:</strong> Software bugs, API failures, exchange outages, internet connectivity issues, or latency may cause orders to execute incorrectly or fail entirely.</Li>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>Market Risk:</strong> Markets can gap, become illiquid, or move against positions faster than automated systems can respond.</Li>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>Regulatory Risk:</strong> Automated trading may be restricted or prohibited in certain jurisdictions. You are solely responsible for ensuring your use of the Service complies with applicable laws.</Li>
              <Li><strong style={{ color: "rgba(255,255,255,0.6)" }}>Counterparty Risk:</strong> {COMPANY} does not control or insure third-party exchanges or brokers. Exchange insolvency or withdrawal restrictions are outside our control.</Li>
            </ul>
          </Section>

          <Section title="4. User Eligibility">
            <P>You must be at least 18 years of age to use the Service. By using the Service you represent and warrant that:</P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>You are at least 18 years old</Li>
              <Li>You have the legal capacity to enter into a binding agreement</Li>
              <Li>Your use of the Service is not prohibited by applicable law in your jurisdiction</Li>
              <Li>You understand and accept the risks associated with automated and algorithmic trading</Li>
              <Li>You are not a resident of any jurisdiction where access to or use of the Service is prohibited</Li>
            </ul>
          </Section>

          <Section title="5. Account Registration and Security">
            <P>
              You are responsible for maintaining the confidentiality of your account credentials, API keys,
              and private keys. You agree to immediately notify us of any unauthorised use of your account.
            </P>
            <P>
              <strong style={{ color: "rgba(255,255,255,0.75)" }}>API keys, private keys, and wallet credentials stored or
              used within the Service are your sole responsibility.</strong> We strongly recommend using API
              keys with the minimum required permissions and with IP restrictions enabled. Never grant
              withdrawal permissions to any API key used with {COMPANY}.
            </P>
          </Section>

          <Section title="6. Automated Trading and AI Limitations">
            <P>
              The Service uses multiple large language models (LLMs) and AI systems to generate trade signals.
              You acknowledge and agree that:
            </P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>AI-generated decisions are not guaranteed to be profitable, accurate, or suitable for your circumstances</Li>
              <Li>Historical performance of AI models within the platform does not guarantee future results</Li>
              <Li>The AI council architecture (multiple models voting on decisions) reduces but does not eliminate model error</Li>
              <Li>You are solely responsible for all trades executed by the automated system on your behalf</Li>
              <Li>You must monitor the system and retain the ability to halt automated trading at any time</Li>
              <Li>Default risk parameters are conservative but may not be sufficient to prevent loss in all market conditions</Li>
            </ul>
          </Section>

          <Section title="7. Third-Party Services">
            <P>
              The Service integrates with third-party exchanges (Hyperliquid, Binance, OANDA, and others via CCXT),
              AI providers (Anthropic, Groq, Google, Ollama, OpenRouter), and data sources. {COMPANY} is not
              responsible for the availability, accuracy, or reliability of any third-party service.
            </P>
            <P>
              Your use of third-party services is governed by their respective terms of service. Ensure you
              comply with all applicable exchange terms, particularly regarding automated and algorithmic trading.
            </P>
          </Section>

          <Section title="8. Prohibited Uses">
            <P>You agree not to use the Service to:</P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>Violate any applicable law or regulation, including securities laws and anti-money laundering regulations</Li>
              <Li>Engage in market manipulation, wash trading, spoofing, or any other prohibited trading practice</Li>
              <Li>Circumvent exchange terms of service or rate limits through abuse of the platform</Li>
              <Li>Reverse engineer, decompile, or attempt to extract the source code of the Service</Li>
              <Li>Resell, sublicense, or commercially distribute the Service without written authorisation</Li>
              <Li>Use the Service to trade on behalf of third parties without appropriate authorisation</Li>
            </ul>
          </Section>

          <Section title="9. Intellectual Property">
            <P>
              All software, code, algorithms, designs, trademarks, and content comprising the Service are
              the exclusive property of {COMPANY} or its licensors. These Terms do not grant you any right,
              title, or interest in any intellectual property owned or licensed by {COMPANY}.
            </P>
          </Section>

          <Section title="10. Disclaimers — &quot;AS IS&quot; Basis">
            <P>
              <strong style={{ color: "rgba(255,255,255,0.75)" }}>THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS AVAILABLE&quot; WITHOUT WARRANTIES OF ANY KIND,
              EITHER EXPRESS OR IMPLIED.</strong> TO THE FULLEST EXTENT PERMITTED BY APPLICABLE LAW, {COMPANY.toUpperCase()}
              DISCLAIMS ALL WARRANTIES INCLUDING, WITHOUT LIMITATION:
            </P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT</Li>
              <Li>ANY WARRANTY THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR SECURE</Li>
              <Li>ANY WARRANTY AS TO THE ACCURACY, RELIABILITY, OR COMPLETENESS OF ANY AI-GENERATED OUTPUT</Li>
              <Li>ANY WARRANTY THAT DEFECTS WILL BE CORRECTED</Li>
            </ul>
          </Section>

          <Section title="11. Limitation of Liability">
            <P>
              <strong style={{ color: "rgba(255,255,255,0.75)" }}>TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL {COMPANY.toUpperCase()},
              ITS DIRECTORS, EMPLOYEES, PARTNERS, AGENTS, SUPPLIERS, OR AFFILIATES BE LIABLE FOR:</strong>
            </P>
            <ul style={{ listStyle: "none", marginBottom: 12 }}>
              <Li>Any trading losses, including losses arising from AI-generated signals or automated order execution</Li>
              <Li>Loss of profits, revenue, data, goodwill, or other intangible losses</Li>
              <Li>Indirect, incidental, special, consequential, or punitive damages</Li>
              <Li>Damages resulting from exchange API failures, connectivity issues, or third-party service outages</Li>
              <Li>Losses arising from unauthorised access to your account or API keys</Li>
            </ul>
            <P>
              In jurisdictions that do not allow the exclusion of certain warranties or limitation of
              liability, our liability shall be limited to the maximum extent permitted by law.
            </P>
          </Section>

          <Section title="12. Indemnification">
            <P>
              You agree to defend, indemnify, and hold harmless {COMPANY} and its affiliates, officers,
              directors, employees, and agents from and against any claims, damages, obligations, losses,
              liabilities, costs, or debt arising from: (a) your use of the Service; (b) your violation
              of these Terms; (c) your violation of any third-party rights; or (d) any trading activity
              conducted through the Service.
            </P>
          </Section>

          <Section title="13. Demo and Paper Trading">
            <P>
              The Service includes demo and paper-trading simulation modes. While we endeavour to make
              simulated environments accurate, simulated results may differ materially from live trading
              due to liquidity, slippage, and other real-world market conditions. Profitable demo performance
              does not guarantee profitable live performance.
            </P>
          </Section>

          <Section title="14. Privacy">
            <P>
              Your use of the Service is also governed by our Privacy Policy. We collect minimal data
              necessary to operate the Service. We do not store your API keys, private keys, or trading
              credentials on our servers. See our Privacy Policy for full details.
            </P>
          </Section>

          <Section title="15. Termination">
            <P>
              We reserve the right to suspend or terminate your access to the Service at any time and for
              any reason without notice. Upon termination, your right to use the Service immediately ceases.
              All provisions of these Terms that by their nature should survive termination shall survive.
            </P>
          </Section>

          <Section title="16. Governing Law &amp; Dispute Resolution">
            <P>
              These Terms shall be governed by and construed in accordance with applicable law. Any dispute
              arising out of or in connection with these Terms shall first be attempted to be resolved
              through good-faith negotiation. If negotiation fails, disputes shall be resolved by binding
              arbitration, except where prohibited by applicable law.
            </P>
          </Section>

          <Section title="17. Changes to Terms">
            <P>
              We may update these Terms at any time. We will notify users of material changes by updating
              the &quot;Last updated&quot; date above and, where practical, by in-app notification. Your continued
              use of the Service after any change constitutes acceptance.
            </P>
          </Section>

          <Section title="18. Contact">
            <P>
              Questions regarding these Terms should be directed to:{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} style={{ color: "rgba(255,255,255,0.6)", textDecoration: "underline" }}>
                {CONTACT_EMAIL}
              </a>
            </P>
          </Section>

          <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 32, marginTop: 16, display: "flex", gap: 24 }}>
            <Link href="/" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>← Home</Link>
            <Link href="/docs" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>Docs</Link>
            <Link href="/sign-up" style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textDecoration: "none" }}>Sign up</Link>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
