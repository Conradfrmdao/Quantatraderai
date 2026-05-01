"use client";
import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import {
  Users, DollarSign, TrendingUp, Activity, ArrowLeft,
  Shield, RefreshCw, AlertTriangle, Zap, BarChart2,
  Clock, Server, Radio,
} from "lucide-react";

interface AdminStats {
  users: {
    total: number; paying: number; new_24h: number;
    new_7d: number; new_30d: number;
    by_plan: Record<string, number>;
  };
  revenue: {
    mrr_usd: number; arr_usd: number;
    by_plan: Record<string, number>;
  };
  activity: {
    trades_24h: number; trades_7d: number;
    active_agents_db: number; active_agents_live: number;
    ws_clients: number; server_uptime_s: number;
  };
  recent_signups: { clerkId: string; email: string; plan: string; createdAt: string }[];
  active_agents: { clerkId: string; venue: string; symbols: string[]; isPaper: boolean; startedAt: string }[];
  recent_events: { userId: string; event: string; symbol: string | null; action: string | null; createdAt: string }[];
  top_traders: { userId: string; _count: { id: number } }[];
  server: Record<string, unknown>;
}

const PLAN_COLOR: Record<string, string> = {
  FREE: "rgba(255,255,255,0.35)", STARTER: "#818cf8", PRO: "#4ade80", ENTERPRISE: "#fbbf24",
};

function fmt(n: number) { return n.toLocaleString("en-US"); }
function fmtUsd(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}
function fmtTime(ts: string) {
  try { return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return ts; }
}
function fmtUptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function BigStat({ icon: Icon, label, value, sub, color = "#fff" }:
  { icon: React.ElementType; label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 14, padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Icon size={13} style={{ color: "rgba(255,255,255,0.3)" }} />
        <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase", letterSpacing: "0.07em" }}>{label}</span>
      </div>
      <p style={{ fontSize: 28, fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>{value}</p>
      {sub && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginTop: 4 }}>{sub}</p>}
    </div>
  );
}

export default function AdminPage() {
  const [stats, setStats]   = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res  = await fetch("/api/admin/stats", { credentials: "same-origin" });
      if (res.status === 403) { setError("Access denied — admin only"); setLoading(false); return; }
      if (!res.ok) { setError(`Error ${res.status}`); setLoading(false); return; }
      setStats(await res.json());
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load, refresh]);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "#080808", display: "flex", alignItems: "center",
      justifyContent: "center", color: "rgba(255,255,255,0.3)", fontSize: 14 }}>
      Loading admin stats…
    </div>
  );

  if (error) return (
    <div style={{ minHeight: "100vh", background: "#080808", display: "flex", alignItems: "center",
      justifyContent: "center", flexDirection: "column", gap: 12 }}>
      <AlertTriangle size={32} style={{ color: "#ef4444" }} />
      <p style={{ color: "#ef4444", fontSize: 16 }}>{error}</p>
      <Link href="/dashboard" style={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>← Back to dashboard</Link>
    </div>
  );

  const s = stats!;

  return (
    <div style={{ minHeight: "100vh", background: "#080808", padding: "28px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 28, maxWidth: 1200, margin: "0 auto 28px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link href="/dashboard" style={{ color: "rgba(255,255,255,0.3)", display: "flex" }}>
            <ArrowLeft size={16} />
          </Link>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#fff" }}>Admin Dashboard</h1>
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
              QuntaTradeAI Platform Overview — real-time
            </p>
          </div>
        </div>
        <button onClick={() => setRefresh(r => r + 1)}
          style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "7px 12px",
            color: "rgba(255,255,255,0.5)", fontSize: 12, cursor: "pointer" }}>
          <RefreshCw size={11} /> Refresh
        </button>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto" }}>

        {/* ── Revenue row ──────────────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          <BigStat icon={DollarSign} label="MRR" value={fmtUsd(s.revenue.mrr_usd)}
            sub="Monthly recurring revenue" color="#4ade80" />
          <BigStat icon={TrendingUp} label="ARR" value={fmtUsd(s.revenue.arr_usd)}
            sub="Annualised" color="#4ade80" />
          <BigStat icon={Users} label="Paying users" value={fmt(s.users.paying)}
            sub={`of ${fmt(s.users.total)} total`} color="#818cf8" />
          <BigStat icon={Activity} label="Live agents" value={String(s.activity.active_agents_live || s.activity.active_agents_db)}
            sub={`${s.activity.ws_clients} WS clients connected`} color="#fbbf24" />
        </div>

        {/* ── User metrics + server row ─────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          <BigStat icon={Users} label="New today" value={fmt(s.users.new_24h)} color="#fff" />
          <BigStat icon={Users} label="New 7d" value={fmt(s.users.new_7d)} color="#fff" />
          <BigStat icon={BarChart2} label="Trades 24h" value={fmt(s.activity.trades_24h)} color="#fff" />
          <BigStat icon={Server} label="Server uptime"
            value={fmtUptime(s.activity.server_uptime_s)} color="#4ade80" />
        </div>

        {/* ── Plan breakdown ─────────────────────────────────────────────────── */}
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 14, padding: "18px 20px", marginBottom: 20 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
            textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 14 }}>
            Users by plan
          </p>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {Object.entries(s.users.by_plan).map(([plan, count]) => (
              <div key={plan} style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 80 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: PLAN_COLOR[plan] ?? "#888",
                  textTransform: "uppercase", letterSpacing: "0.08em" }}>{plan}</span>
                <span style={{ fontSize: 26, fontWeight: 800, color: "#fff",
                  fontVariantNumeric: "tabular-nums" }}>{fmt(count)}</span>
                <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                  {s.revenue.by_plan[plan] > 0 ? `${fmtUsd(s.revenue.by_plan[plan])}/mo` : "free"}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>

          {/* Recent signups */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 14, padding: "16px 18px" }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
              textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 12 }}>
              Recent signups
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {s.recent_signups.slice(0, 10).map((u, i) => (
                <div key={u.clerkId} style={{ display: "flex", justifyContent: "space-between",
                  alignItems: "center", padding: "6px 0",
                  borderBottom: i < 9 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                  <div>
                    <p style={{ fontSize: 12, color: "#fff", fontWeight: 500 }}>{u.email}</p>
                    <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>{fmtTime(u.createdAt)}</p>
                  </div>
                  <span style={{ fontSize: 9, fontWeight: 700, color: PLAN_COLOR[u.plan] ?? "#888",
                    background: `${PLAN_COLOR[u.plan] ?? "#888"}18`,
                    border: `1px solid ${PLAN_COLOR[u.plan] ?? "#888"}30`,
                    padding: "2px 6px", borderRadius: 4 }}>{u.plan}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Live agents */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 14, padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#4ade80",
                animation: s.active_agents.length > 0 ? undefined : "none" }} />
              <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
                textTransform: "uppercase", letterSpacing: "0.07em" }}>
                Live agents ({s.active_agents.length})
              </p>
            </div>
            {s.active_agents.length === 0 ? (
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.25)", padding: "8px 0" }}>
                No agents currently running
              </p>
            ) : s.active_agents.slice(0, 8).map((a, i) => (
              <div key={a.clerkId + i} style={{ padding: "6px 0",
                borderBottom: i < s.active_agents.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <p style={{ fontSize: 11, color: "#fff", fontWeight: 500 }}>
                    {a.symbols?.join(", ") ?? "—"}
                  </p>
                  <span style={{ fontSize: 9, color: a.isPaper ? "#818cf8" : "#ef4444",
                    fontWeight: 700 }}>{a.isPaper ? "PAPER" : "LIVE"}</span>
                </div>
                <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>
                  {a.venue} · since {fmtTime(a.startedAt)}
                </p>
              </div>
            ))}
          </div>

          {/* Recent events */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 14, padding: "16px 18px" }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
              textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 12 }}>
              Recent activity
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {s.recent_events.slice(0, 10).map((e, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between",
                  alignItems: "flex-start", padding: "5px 0",
                  borderBottom: i < 9 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                  <div>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
                      <span style={{ fontWeight: 600, color: "#fff" }}>{e.event}</span>
                      {e.symbol && ` · ${e.symbol}`}
                      {e.action && ` · ${e.action}`}
                    </p>
                    <p style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>
                      {fmtTime(e.createdAt)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <p style={{ textAlign: "center", fontSize: 11, color: "rgba(255,255,255,0.15)", marginTop: 12 }}>
          Admin access only · All times UTC · Auto-refreshes on click
        </p>
      </div>
    </div>
  );
}
