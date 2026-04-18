"use client";
import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  Shield,
  Zap,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { StatCard }       from "@/components/StatCard";
import { StatusBar }      from "@/components/StatusBar";
import { PositionsTable } from "@/components/PositionsTable";
import { DecisionsFeed }  from "@/components/DecisionsFeed";
import { RiskPanel }      from "@/components/RiskPanel";
import { EquityChart }    from "@/components/EquityChart";
import SectionWithMockup  from "@/components/ui/section-with-mockup";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000";

function usePolled<T>(path: string, interval = 8000) {
  const [data, setData] = useState<T | null>(null);
  const fetch_ = useCallback(() => {
    fetch(`${API}${path}`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, [path]);
  useEffect(() => {
    fetch_();
    const id = setInterval(fetch_, interval);
    return () => clearInterval(id);
  }, [fetch_, interval]);
  return { data, refresh: fetch_ };
}

interface AccountData   { balance: number; equity: number; initial_equity: number; total_return_pct: number; open_positions: number; sharpe: number }
interface PositionsData { positions: { symbol: string; quantity: number; entry_price: number; current_price: number; unrealized_pnl: number; leverage: number; liquidation_price: number }[] }
interface StatusData    { status: string; provider: string; model: string; venue: string; tick_count: number; uptime_seconds: number; assets: string[] }
interface RiskData      { max_position_pct: string; max_leverage: string; mandatory_sl_pct: string; max_loss_per_position_pct: string; daily_loss_circuit_breaker_pct: string; max_total_exposure_pct: string; max_concurrent_positions: string }
interface DecisionsData { decisions: { ts: string; trade_decisions: { asset: string; action: string; rationale: string; tp_price: number; sl_price: number; allocation_usd: number }[] }[] }

export default function Dashboard() {
  const account   = usePolled<AccountData>  ("/api/account",   8000);
  const positions = usePolled<PositionsData>("/api/positions", 8000);
  const status    = usePolled<StatusData>   ("/api/status",   15000);
  const risk      = usePolled<RiskData>     ("/api/risk",     60000);
  const decisions = usePolled<DecisionsData>("/api/decisions",10000);

  const [equityHistory, setEquityHistory] = useState<{ t: string; equity: number }[]>([]);
  useEffect(() => {
    if (!decisions.data?.decisions || !account.data?.equity) return;
    setEquityHistory((prev) => {
      const point = {
        t: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        equity: account.data!.equity,
      };
      const next = [...prev, point].slice(-40);
      return next;
    });
  }, [decisions.data, account.data]);

  const acc      = account.data;
  const pos      = positions.data?.positions ?? [];
  const totalPnL = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const isUp     = (acc?.total_return_pct ?? 0) >= 0;
  const running  = status.data?.status === "running";

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>

      {/* ── Header ─────────────────────────────────────────────────── */}
      <motion.header
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
          padding: "0 28px",
          height: 60,
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "rgba(0,0,0,0.8)",
          position: "sticky",
          top: 0,
          zIndex: 50,
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 10,
              background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(139,92,246,0.4)",
            }}
          >
            <Zap size={16} color="#fff" />
          </div>
          <div>
            <h1
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: "#fff",
                letterSpacing: "-0.02em",
              }}
            >
              QuntaTradeAI
            </h1>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {!running && (
            <motion.span
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ repeat: Infinity, duration: 2 }}
              style={{
                fontSize: 11,
                color: "var(--yellow)",
                background: "rgba(245,158,11,0.08)",
                border: "1px solid rgba(245,158,11,0.2)",
                padding: "4px 12px",
                borderRadius: 20,
                fontWeight: 500,
              }}
            >
              Agent offline — run: poetry run python src/main.py
            </motion.span>
          )}
          <button
            onClick={() => {
              account.refresh();
              positions.refresh();
              status.refresh();
              decisions.refresh();
            }}
            style={{
              background: "rgba(255,255,255,0.05)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "6px 12px",
              cursor: "pointer",
              color: "var(--muted)",
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              transition: "background 0.2s",
            }}
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </motion.header>

      {/* ── Dashboard ──────────────────────────────────────────────── */}
      <main style={{ padding: "28px 28px 0", maxWidth: 1400, margin: "0 auto" }}>

        {/* Status bar */}
        <div style={{ marginBottom: 24 }}>
          <StatusBar data={status.data} />
        </div>

        {/* Stat cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
            gap: 14,
            marginBottom: 24,
          }}
        >
          <StatCard
            label="Portfolio Equity"
            value={acc ? `$${acc.equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
            sub={acc ? `${isUp ? "▲" : "▼"} ${Math.abs(acc.total_return_pct).toFixed(2)}% total return` : undefined}
            icon={TrendingUp}
            trend={isUp ? "up" : "down"}
            glow
            delay={0}
          />
          <StatCard
            label="Unrealised PnL"
            value={totalPnL ? `${totalPnL >= 0 ? "+" : ""}$${totalPnL.toFixed(2)}` : "$0.00"}
            sub={acc ? `Available: $${acc.balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined}
            icon={totalPnL >= 0 ? TrendingUp : TrendingDown}
            trend={totalPnL >= 0 ? "up" : "down"}
            delay={0.07}
          />
          <StatCard
            label="Open Positions"
            value={pos.length.toString()}
            sub={`Max ${risk.data?.max_concurrent_positions ?? "—"} allowed`}
            icon={Layers}
            trend="neutral"
            delay={0.14}
          />
          <StatCard
            label="Sharpe Ratio"
            value={acc ? acc.sharpe.toFixed(3) : "—"}
            sub="Risk-adjusted return"
            icon={Activity}
            trend={acc && acc.sharpe > 0 ? "up" : "neutral"}
            delay={0.21}
          />
        </div>

        {/* Main grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 360px",
            gap: 18,
            marginBottom: 18,
          }}
        >
          {/* Left */}
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Equity curve */}
            <motion.section
              className="card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.25 }}
              style={{ padding: "22px 24px" }}
            >
              <p
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  color: "var(--muted)",
                  marginBottom: 16,
                }}
              >
                Equity Curve
              </p>
              <EquityChart data={equityHistory} />
            </motion.section>

            {/* Positions */}
            <motion.section
              className="card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.32 }}
            >
              <div
                style={{
                  padding: "20px 24px 14px",
                  borderBottom: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <Layers size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)", letterSpacing: "0.02em" }}>
                  Open Positions
                </span>
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: 11,
                    color: "var(--muted)",
                    background: "rgba(255,255,255,0.05)",
                    padding: "2px 10px",
                    borderRadius: 20,
                  }}
                >
                  {pos.length}
                </span>
              </div>
              <PositionsTable positions={pos} />
            </motion.section>
          </div>

          {/* Right */}
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Risk config */}
            <motion.section
              className="card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.35 }}
              style={{ padding: "22px 24px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
                <Shield size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>
                  Risk Config
                </span>
              </div>
              <RiskPanel risk={risk.data} />
            </motion.section>

            {/* AI Decisions */}
            <motion.section
              className="card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.42 }}
              style={{ padding: "22px 24px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
                <Zap size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>
                  AI Decisions
                </span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--muted)" }}>
                  auto-refreshes
                </span>
              </div>
              <DecisionsFeed decisions={decisions.data?.decisions ?? []} />
            </motion.section>
          </div>
        </div>
      </main>

      {/* ── 21st.dev feature sections ──────────────────────────────── */}
      <div style={{ borderTop: "1px solid var(--border)", marginTop: 40 }}>
        <SectionWithMockup
          title={
            <>
              Multi-venue AI trading,
              <br />
              powered by Groq & Claude.
            </>
          }
          description={
            <>
              QuntaTradeAI connects to Hyperliquid, Binance, and 100+ exchanges
              via a single abstraction layer. Each trade decision is made by an
              LLM with full technical context — RSI, MACD, ATR, funding rates —
              and enforced by conservative risk rules before any order is placed.
            </>
          }
          primaryImageSrc="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&q=80&auto=format&fit=crop"
          secondaryImageSrc="https://images.unsplash.com/photo-1642543492481-44e81e3914a7?w=800&q=80&auto=format&fit=crop"
        />

        <SectionWithMockup
          reverseLayout
          title={
            <>
              Risk-first architecture
              <br />
              before every order.
            </>
          }
          description={
            <>
              Every trade is validated against configurable limits: 3% max
              position, 2× leverage cap, mandatory stop-losses, and a daily
              circuit breaker that halts new trades if drawdown exceeds 4%.
              Edit <code style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>risk.yaml</code> to tune limits per venue and asset class.
            </>
          }
          primaryImageSrc="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&q=80&auto=format&fit=crop"
          secondaryImageSrc="https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=800&q=80&auto=format&fit=crop"
        />
      </div>

      {/* ── Footer ─────────────────────────────────────────────────── */}
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "24px 28px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "rgba(255,255,255,0.01)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: 8,
              background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Zap size={13} color="#fff" />
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.6)" }}>
            QuntaTradeAI
          </span>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)" }}>
          ⚠ For educational use. Not financial advice. Trade at your own risk.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            Powered by Groq · Hyperliquid · Binance · OANDA
          </span>
          <ChevronRight size={12} style={{ color: "var(--muted)" }} />
        </div>
      </footer>
    </div>
  );
}
