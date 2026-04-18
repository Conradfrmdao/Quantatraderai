"use client";
import { useEffect, useState, useCallback } from "react";
import { TrendingUp, TrendingDown, Activity, Layers, Shield, Zap, RefreshCw } from "lucide-react";
import { StatCard } from "@/components/StatCard";
import { StatusBar } from "@/components/StatusBar";
import { PositionsTable } from "@/components/PositionsTable";
import { DecisionsFeed } from "@/components/DecisionsFeed";
import { RiskPanel } from "@/components/RiskPanel";
import { EquityChart } from "@/components/EquityChart";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000";

function usePolled<T>(path: string, interval = 8000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  const fetch_ = useCallback(() => {
    fetch(`${API}${path}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setError(false); })
      .catch(() => setError(true));
  }, [path]);
  useEffect(() => { fetch_(); const id = setInterval(fetch_, interval); return () => clearInterval(id); }, [fetch_, interval]);
  return { data, error, refresh: fetch_ };
}

interface AccountData { balance: number; equity: number; initial_equity: number; total_return_pct: number; open_positions: number; sharpe: number }
interface PositionsData { positions: { symbol: string; quantity: number; entry_price: number; current_price: number; unrealized_pnl: number; leverage: number; liquidation_price: number }[] }
interface StatusData { status: string; provider: string; model: string; venue: string; tick_count: number; uptime_seconds: number; assets: string[] }
interface RiskData { max_position_pct: string; max_leverage: string; mandatory_sl_pct: string; max_loss_per_position_pct: string; daily_loss_circuit_breaker_pct: string; max_total_exposure_pct: string; max_concurrent_positions: string }
interface DecisionsData { decisions: { ts: string; trade_decisions: { asset: string; action: string; rationale: string; tp_price: number; sl_price: number; allocation_usd: number }[] }[] }

export default function Dashboard() {
  const account = usePolled<AccountData>("/api/account", 8000);
  const positions = usePolled<PositionsData>("/api/positions", 8000);
  const status = usePolled<StatusData>("/api/status", 15000);
  const risk = usePolled<RiskData>("/api/risk", 60000);
  const decisions = usePolled<DecisionsData>("/api/decisions", 10000);

  // Build equity history from diary decisions for the chart
  const [equityHistory, setEquityHistory] = useState<{ t: string; equity: number }[]>([]);
  useEffect(() => {
    if (!decisions.data?.decisions) return;
    const pts = decisions.data.decisions
      .filter((d) => d.ts)
      .slice(-30)
      .map((d) => ({
        t: new Date(d.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        equity: account.data?.equity ?? 0,
      }));
    if (pts.length) setEquityHistory(pts);
  }, [decisions.data, account.data]);

  const acc = account.data;
  const pos = positions.data?.positions ?? [];
  const totalPnL = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const isUp = (acc?.total_return_pct ?? 0) >= 0;
  const connected = status.data?.status === "running";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      {/* Header */}
      <header style={{
        padding: "16px 28px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--surface)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 9,
            background: "linear-gradient(135deg,#3b82f6,#8b5cf6)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Zap size={17} color="#fff" />
          </div>
          <div>
            <h1 className="gradient-text" style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em" }}>
              QuntaTradeAI
            </h1>
            <p style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Multi-venue AI Trading
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {!connected && (
            <span style={{ fontSize: 11, color: "var(--red)", background: "rgba(244,63,94,0.1)", padding: "4px 10px", borderRadius: 20, fontWeight: 600 }}>
              Agent offline — start python src/main.py
            </span>
          )}
          <button
            onClick={() => { account.refresh(); positions.refresh(); status.refresh(); decisions.refresh(); }}
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", cursor: "pointer", color: "var(--muted)", display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </header>

      <main style={{ padding: "24px 28px", maxWidth: 1400, margin: "0 auto" }}>
        {/* Status bar */}
        <div style={{ marginBottom: 24 }}>
          <StatusBar data={status.data} />
        </div>

        {/* Stat cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 24 }}>
          <StatCard
            label="Portfolio Equity"
            value={acc ? `$${acc.equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
            sub={acc ? `${isUp ? "▲" : "▼"} ${Math.abs(acc.total_return_pct).toFixed(2)}% all-time` : undefined}
            icon={TrendingUp}
            trend={isUp ? "up" : "down"}
            glow
          />
          <StatCard
            label="Unrealised PnL"
            value={totalPnL ? `${totalPnL >= 0 ? "+" : ""}$${totalPnL.toFixed(2)}` : "—"}
            sub={acc ? `Balance: $${acc.balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined}
            icon={totalPnL >= 0 ? TrendingUp : TrendingDown}
            trend={totalPnL >= 0 ? "up" : "down"}
          />
          <StatCard
            label="Open Positions"
            value={pos.length.toString()}
            sub={acc ? `Max ${acc.open_positions ?? "—"} allowed` : undefined}
            icon={Layers}
            trend="neutral"
          />
          <StatCard
            label="Sharpe Ratio"
            value={acc ? acc.sharpe.toFixed(3) : "—"}
            sub="Risk-adjusted return"
            icon={Activity}
            trend={acc && acc.sharpe > 0 ? "up" : "neutral"}
          />
        </div>

        {/* Main grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20, marginBottom: 20 }}>
          {/* Left column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Equity curve */}
            <section className="card" style={{ padding: "18px 20px" }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 16 }}>
                Equity Curve
              </h2>
              <EquityChart data={equityHistory} />
            </section>

            {/* Positions */}
            <section className="card">
              <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
                <Layers size={14} style={{ color: "var(--accent)" }} />
                <h2 style={{ fontSize: 13, fontWeight: 700 }}>Open Positions</h2>
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", background: "var(--surface-2)", padding: "2px 8px", borderRadius: 20 }}>
                  {pos.length}
                </span>
              </div>
              <PositionsTable positions={pos} />
            </section>
          </div>

          {/* Right column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Risk config */}
            <section className="card" style={{ padding: "18px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <Shield size={14} style={{ color: "var(--accent)" }} />
                <h2 style={{ fontSize: 13, fontWeight: 700 }}>Risk Config</h2>
              </div>
              <RiskPanel risk={risk.data} />
            </section>

            {/* AI Decisions */}
            <section className="card" style={{ padding: "18px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <Zap size={14} style={{ color: "var(--accent)" }} />
                <h2 style={{ fontSize: 13, fontWeight: 700 }}>AI Decisions</h2>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--muted)" }}>last 12</span>
              </div>
              <DecisionsFeed decisions={decisions.data?.decisions ?? []} />
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
