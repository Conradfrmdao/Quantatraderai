"use client";
import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { useSession } from "@clerk/nextjs";
import Link from "next/link";
import {
  TrendingUp, TrendingDown, Shield, Brain, Activity, BarChart2,
  ArrowLeft, Target, Zap, AlertTriangle,
} from "lucide-react";

interface TrustMetrics {
  total_trades:       number;
  win_rate_pct:       number;
  wins:               number;
  losses:             number;
  gross_pnl:          number;
  avg_win:            number;
  avg_loss:           number;
  max_drawdown_pct:   number;
  sharpe:             number;
  ai_accuracy_pct:    number | null;
  profit_curve:       { i: number; equity: number }[];
  running:            boolean;
}

function ScoreRing({ value, label, color }: { value: number; label: string; color: string }) {
  const r = 36;
  const circ = 2 * Math.PI * r;
  const filled = (value / 100) * circ;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <svg width={88} height={88} viewBox="0 0 88 88">
        <circle cx={44} cy={44} r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={7} />
        <circle cx={44} cy={44} r={r} fill="none" stroke={color} strokeWidth={7}
          strokeDasharray={`${filled} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 44 44)"
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
        <text x={44} y={44} textAnchor="middle" dominantBaseline="middle"
          fill="#fff" fontSize={16} fontWeight={700} fontFamily="system-ui">
          {value.toFixed(0)}%
        </text>
      </svg>
      <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
        {label}
      </span>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, sub, color = "#888" }:
  { icon: React.ElementType; label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 12, padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <Icon size={13} style={{ color }} />
        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          {label}
        </span>
      </div>
      <p style={{ fontSize: 22, fontWeight: 700, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </p>
      {sub && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginTop: 2 }}>{sub}</p>}
    </div>
  );
}

function MiniChart({ curve }: { curve: { i: number; equity: number }[] }) {
  if (curve.length < 2) {
    return (
      <div style={{ height: 80, display: "flex", alignItems: "center", justifyContent: "center",
        color: "rgba(255,255,255,0.2)", fontSize: 12 }}>
        No trade history yet
      </div>
    );
  }
  const min  = Math.min(...curve.map(p => p.equity));
  const max  = Math.max(...curve.map(p => p.equity));
  const w    = 340;
  const h    = 80;
  const range = max - min || 1;
  const pts  = curve.map((p, i) => {
    const x = (i / (curve.length - 1)) * w;
    const y = h - ((p.equity - min) / range) * (h - 10) - 5;
    return `${x},${y}`;
  }).join(" ");

  const endEq = curve[curve.length - 1].equity;
  const startEq = curve[0].equity;
  const color   = endEq >= startEq ? "#4ade80" : "#ef4444";

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 80 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function TrustDashboard() {
  const { session } = useSession();
  const [metrics, setMetrics] = useState<TrustMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!session) return;
    try {
      const res  = await fetch("/api/agent/trust/metrics", { credentials: "same-origin" });
      const data = await res.json();
      setMetrics(data);
    } catch { /* backend may be offline */ }
    setLoading(false);
  }, [session]);

  useEffect(() => { load(); const id = setInterval(load, 15_000); return () => clearInterval(id); }, [load]);

  const m = metrics;
  const trustScore = m
    ? Math.round(
        ((m.win_rate_pct ?? 0) * 0.4) +
        (Math.min((m.sharpe ?? 0) * 20, 30)) +
        (Math.max(0, 30 - (m.max_drawdown_pct ?? 0)) * 0.6) +
        ((m.ai_accuracy_pct ?? 0) ? (m.ai_accuracy_pct ?? 0) * 0.1 : 0)
      )
    : 0;

  return (
    <div style={{ minHeight: "100vh", background: "#080808", padding: "24px 20px", maxWidth: 760, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28 }}>
        <Link href="/dashboard" style={{ color: "rgba(255,255,255,0.35)", display: "flex" }}>
          <ArrowLeft size={16} />
        </Link>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>Trust Dashboard</h1>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            Real performance — win rate, drawdown, AI accuracy
          </p>
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: 60, color: "rgba(255,255,255,0.3)" }}>
          Loading metrics…
        </div>
      )}

      {!loading && !m && (
        <div style={{ textAlign: "center", padding: 60, color: "rgba(255,255,255,0.3)" }}>
          Backend offline — start the agent to collect data.
        </div>
      )}

      {!loading && m && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
          {/* Trust Score */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 16, padding: "20px 24px", marginBottom: 20,
            display: "flex", alignItems: "center", gap: 24 }}>
            <ScoreRing value={Math.min(trustScore, 99)} label="Trust Score"
              color={trustScore >= 70 ? "#4ade80" : trustScore >= 50 ? "#fbbf24" : "#ef4444"} />
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.6)", lineHeight: 1.6 }}>
                {trustScore >= 70
                  ? "Strong performance. AI is trading within expected parameters."
                  : trustScore >= 50
                  ? "Moderate performance. Monitor drawdown and adjust risk settings."
                  : "Caution — below target. Consider reducing position size or pausing."}
              </p>
              {m.running && (
                <div style={{ display: "inline-flex", alignItems: "center", gap: 5, marginTop: 8,
                  background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.2)",
                  borderRadius: 6, padding: "3px 8px" }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4ade80",
                    animation: "pulse 2s infinite" }} />
                  <span style={{ fontSize: 10, color: "#4ade80", fontWeight: 600 }}>AGENT LIVE</span>
                </div>
              )}
            </div>
            <ScoreRing value={(m.win_rate_pct ?? 0)} label="Win Rate"
              color={(m.win_rate_pct ?? 0) >= 55 ? "#4ade80" : (m.win_rate_pct ?? 0) >= 45 ? "#fbbf24" : "#ef4444"} />
          </div>

          {/* Profit Curve */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 12, padding: "16px 20px", marginBottom: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)",
                textTransform: "uppercase", letterSpacing: "0.07em" }}>
                Profit Curve (last 50 trades)
              </span>
              <span style={{ fontSize: 12, fontWeight: 700,
                color: (m.gross_pnl ?? 0) >= 0 ? "#4ade80" : "#ef4444" }}>
                {(m.gross_pnl ?? 0) >= 0 ? "+" : ""}{(m.gross_pnl ?? 0).toFixed(2)} USD
              </span>
            </div>
            <MiniChart curve={m.profit_curve} />
          </div>

          {/* Metrics grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
            <MetricCard icon={BarChart2} label="Sharpe Ratio" value={(m.sharpe ?? 0).toFixed(2)}
              sub={(m.sharpe ?? 0) >= 1.5 ? "Excellent" : (m.sharpe ?? 0) >= 0.5 ? "Good" : "Low"}
              color={(m.sharpe ?? 0) >= 1 ? "#4ade80" : "#fbbf24"} />
            <MetricCard icon={AlertTriangle} label="Max Drawdown"
              value={`${(m.max_drawdown_pct ?? 0).toFixed(1)}%`}
              sub={(m.max_drawdown_pct ?? 0) < 10 ? "Safe" : (m.max_drawdown_pct ?? 0) < 20 ? "Watch closely" : "Dangerous"}
              color={(m.max_drawdown_pct ?? 0) < 10 ? "#4ade80" : (m.max_drawdown_pct ?? 0) < 20 ? "#fbbf24" : "#ef4444"} />
            <MetricCard icon={TrendingUp} label="Avg Win" value={`$${(m.avg_win ?? 0).toFixed(2)}`}
              sub={`${m.wins ?? 0} winning trades`} color="#4ade80" />
            <MetricCard icon={TrendingDown} label="Avg Loss" value={`$${Math.abs(m.avg_loss ?? 0).toFixed(2)}`}
              sub={`${m.losses ?? 0} losing trades`} color="#ef4444" />
            <MetricCard icon={Activity} label="Total Trades"
              value={(m.total_trades ?? 0).toString()} color="#818cf8" />
            {m.ai_accuracy_pct !== null && (
              <MetricCard icon={Brain} label="AI Accuracy"
                value={`${(m.ai_accuracy_pct ?? 0).toFixed(1)}%`}
                sub="High-confidence calls"
                color={(m.ai_accuracy_pct ?? 0) >= 60 ? "#4ade80" : "#fbbf24"} />
            )}
          </div>

          {/* Disclaimer */}
          <div style={{ background: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.15)",
            borderRadius: 10, padding: "12px 14px",
            display: "flex", alignItems: "flex-start", gap: 8 }}>
            <Shield size={13} style={{ color: "#fbbf24", flexShrink: 0, marginTop: 1 }} />
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", lineHeight: 1.6 }}>
              <strong style={{ color: "rgba(255,255,255,0.6)" }}>Not financial advice.</strong>{" "}
              Past performance does not guarantee future results. All metrics reflect simulated or
              live paper trades unless live trading is explicitly enabled.
            </p>
          </div>
        </motion.div>
      )}
    </div>
  );
}
