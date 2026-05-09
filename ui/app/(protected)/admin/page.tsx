"use client";
import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  Users, DollarSign, TrendingUp, Activity, ArrowLeft,
  Shield, RefreshCw, AlertTriangle, Brain, BarChart2,
  Server, Search, ChevronRight, X, Check, CreditCard,
  Clock, Zap, ArrowUpRight, Mail, Edit2,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface AdminStats {
  users: { total: number; paying: number; new_24h: number; new_7d: number; by_plan: Record<string, number> };
  revenue: { mrr_usd: number; arr_usd: number; by_plan: Record<string, number> };
  activity: { trades_24h: number; active_agents_live: number; ws_clients: number; server_uptime_s: number };
  recent_signups: { clerkId: string; email: string; plan: string; createdAt: string }[];
  active_agents: { userId: string; venue: string; symbols: string[]; isPaper: boolean; startedAt: string }[];
  recent_events: { userId: string; event: string; symbol: string | null; action: string | null; createdAt: string }[];
}

interface UserRow {
  id: string; clerkId: string; email: string; name: string | null;
  plan: string; stripeCustomerId: string | null; stripeSubId: string | null;
  planExpiresAt: string | null; createdAt: string;
  _count: { tradeLogs: number };
}

interface UserDetail {
  user: UserRow & {
    tradeLogs: { id: string; symbol: string; action: string; price: number; pnl: number | null; createdAt: string }[];
    venues:    { id: string; type: string; displayName: string; isPaper: boolean }[];
    auditLogs: { event: string; action: string | null; createdAt: string }[];
  };
  invoices: { id: string; amount: number; currency: string; status: string; created: number; description: string | null; hostedUrl: string | null }[];
  stats: { totalTrades: number; totalPnl: number; winRate: number; totalRevenue: number; venueCount: number };
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const PLAN_COLOR: Record<string, string> = {
  FREE: "rgba(255,255,255,0.3)", STARTER: "#818cf8", PRO: "#4ade80", ENTERPRISE: "#fbbf24",
};
const PLAN_PRICE: Record<string, number> = { FREE: 0, STARTER: 20, PRO: 99, ENTERPRISE: 299 };

function fmt(n: number)    { return n.toLocaleString("en-US"); }
function fmtUsd(n: number) { return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function fmtDate(ts: string | number) {
  try { return new Date(typeof ts === "number" ? ts * 1000 : ts).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return String(ts); }
}
function fmtUptime(s: number) { const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60); return h > 0 ? h + "h " + m + "m" : m + "m"; }

function PlanBadge({ plan }: { plan: string }) {
  return (
    <span style={{ fontSize: 9, fontWeight: 700, color: PLAN_COLOR[plan] ?? "#888",
      background: (PLAN_COLOR[plan] ?? "#888") + "18", border: "1px solid " + (PLAN_COLOR[plan] ?? "#888") + "30",
      padding: "2px 7px", borderRadius: 4, letterSpacing: "0.06em", textTransform: "uppercase" as const }}>
      {plan}
    </span>
  );
}

function Stat({ icon: Icon, label, value, sub, color = "#fff" }:
  { icon: React.ElementType; label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 14, padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Icon size={13} style={{ color: "rgba(255,255,255,0.3)" }} />
        <span style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase" as const, letterSpacing: "0.07em" }}>{label}</span>
      </div>
      <p style={{ fontSize: 26, fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>{value}</p>
      {sub && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginTop: 3 }}>{sub}</p>}
    </div>
  );
}

// ── User Detail Slide-over ────────────────────────────────────────────────────
function UserDetailPanel({ userId, onClose }: { userId: string; onClose: () => void }) {
  const [detail, setDetail]         = useState<UserDetail | null>(null);
  const [loading, setLoading]       = useState(true);
  const [overridePlan, setOverride] = useState("");
  const [reason, setReason]         = useState("");
  const [saving, setSaving]         = useState(false);
  const [saved, setSaved]           = useState(false);

  useEffect(() => {
    fetch("/api/admin/users/" + userId, { credentials: "same-origin" })
      .then(r => r.json())
      .then(d => { setDetail(d); setOverride(d.user.plan); setLoading(false); })
      .catch(() => setLoading(false));
  }, [userId]);

  async function applyOverride() {
    if (!overridePlan || !reason.trim()) return;
    setSaving(true);
    const res = await fetch("/api/admin/users/" + userId, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan: overridePlan, reason }),
    });
    if (res.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000); }
    setSaving(false);
  }

  const d = detail;
  const isSameplan = d && overridePlan === d.user.plan;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      style={{ position: "fixed", inset: 0, zIndex: 200, background: "rgba(0,0,0,0.85)",
        backdropFilter: "blur(8px)", display: "flex", justifyContent: "flex-end" }}
      onClick={onClose}>
      <motion.div initial={{ x: 60 }} animate={{ x: 0 }} exit={{ x: 60 }}
        transition={{ duration: 0.22 }}
        onClick={e => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 540, background: "#0c0c0c",
          borderLeft: "1px solid rgba(255,255,255,0.1)", overflowY: "auto",
          padding: "24px 24px 40px" }}>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <p style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>User Detail</p>
          <button onClick={onClose} style={{ background: "none", border: "none",
            cursor: "pointer", color: "rgba(255,255,255,0.3)" }}><X size={16} /></button>
        </div>

        {loading && <p style={{ color: "rgba(255,255,255,0.3)" }}>Loading…</p>}

        {!loading && d && (
          <div>
            {/* Identity */}
            <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 12, padding: "16px 18px", marginBottom: 16 }}>
              <p style={{ fontSize: 15, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
                {d.user.name ?? d.user.email}
              </p>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginBottom: 8 }}>{d.user.email}</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <PlanBadge plan={d.user.plan} />
                {d.user.stripeSubId
                  ? <span style={{ fontSize: 10, color: "#4ade80" }}>● Active Stripe subscription</span>
                  : d.user.plan !== "FREE"
                    ? <span style={{ fontSize: 10, color: "#fbbf24" }}>⚠ No Stripe sub — manually overridden</span>
                    : null}
              </div>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginTop: 8 }}>
                {"Joined " + fmtDate(d.user.createdAt)}
                {d.user.stripeCustomerId ? " · Stripe: " + d.user.stripeCustomerId : ""}
              </p>
            </div>

            {/* Stats */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 20 }}>
              {[
                { l: "Revenue",  v: fmtUsd(d.stats.totalRevenue),          c: "#4ade80" },
                { l: "Trades",   v: fmt(d.stats.totalTrades),              c: "#fff" },
                { l: "Win %",    v: d.stats.winRate.toFixed(0) + "%",       c: d.stats.winRate >= 50 ? "#4ade80" : "#ef4444" },
                { l: "Venues",   v: String(d.stats.venueCount),             c: "#818cf8" },
              ].map(s => (
                <div key={s.l} style={{ background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)", borderRadius: 10, padding: "10px 12px" }}>
                  <p style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", textTransform: "uppercase" as const,
                    letterSpacing: "0.07em", marginBottom: 3 }}>{s.l}</p>
                  <p style={{ fontSize: 16, fontWeight: 700, color: s.c,
                    fontVariantNumeric: "tabular-nums" }}>{s.v}</p>
                </div>
              ))}
            </div>

            {/* ── CUSTOMER SUPPORT: Manual Plan Override ─────────────── */}
            <div style={{ background: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.2)",
              borderRadius: 12, padding: "16px 18px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12 }}>
                <Edit2 size={12} style={{ color: "#fbbf24" }} />
                <p style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24" }}>Manual Plan Override</p>
                <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>customer support tool</span>
              </div>
              <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", lineHeight: 1.6, marginBottom: 12 }}>
                Use this when a user paid but Stripe didn&apos;t update their plan, or when you want to
                grant/remove access as customer support. All overrides are audit-logged.
              </p>
              <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
                {["FREE", "STARTER", "PRO", "ENTERPRISE"].map(p => (
                  <button key={p} onClick={() => setOverride(p)}
                    style={{ padding: "5px 12px", borderRadius: 7, fontSize: 11, cursor: "pointer",
                      fontWeight: overridePlan === p ? 700 : 400,
                      background: overridePlan === p ? (PLAN_COLOR[p] ?? "#fff") + "20" : "rgba(255,255,255,0.04)",
                      border: "1px solid " + (overridePlan === p ? (PLAN_COLOR[p] ?? "rgba(255,255,255,0.3)") : "rgba(255,255,255,0.1)"),
                      color: overridePlan === p ? (PLAN_COLOR[p] ?? "#fff") : "rgba(255,255,255,0.5)" }}>
                    {p} {PLAN_PRICE[p] > 0 ? "($" + PLAN_PRICE[p] + "/mo)" : "(free)"}
                  </button>
                ))}
              </div>
              <input
                placeholder="Reason — e.g. Stripe webhook failed, user sent payment proof"
                value={reason} onChange={e => setReason(e.target.value)}
                style={{ width: "100%", padding: "8px 12px", borderRadius: 8, fontSize: 12,
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
                  color: "#fff", outline: "none", marginBottom: 10, boxSizing: "border-box" as const }}
              />
              <button onClick={applyOverride}
                disabled={saving || !reason.trim() || !!isSameplan}
                style={{ padding: "9px 20px", borderRadius: 8, fontSize: 12, fontWeight: 700,
                  cursor: (saving || !reason.trim() || !!isSameplan) ? "not-allowed" : "pointer",
                  background: saved ? "rgba(74,222,128,0.2)" : "rgba(251,191,36,0.15)",
                  border: "1px solid " + (saved ? "rgba(74,222,128,0.4)" : "rgba(251,191,36,0.3)"),
                  color: saved ? "#4ade80" : "#fbbf24",
                  opacity: (saving || !reason.trim() || !!isSameplan) ? 0.5 : 1 }}>
                {saved ? "✓ Updated" : saving ? "Saving…" : "Apply: set to " + overridePlan}
              </button>
              {isSameplan && !saved && (
                <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", marginTop: 5 }}>
                  Already on {d.user.plan}
                </p>
              )}
            </div>

            {/* Payment History */}
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
                textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 10 }}>
                {"Payment History (" + d.invoices.length + ")"}
              </p>
              {d.invoices.length === 0 ? (
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.25)" }}>
                  {d.user.stripeCustomerId ? "No invoices in Stripe" : "No Stripe customer"}
                </p>
              ) : d.invoices.map((inv, i) => (
                <div key={inv.id} style={{ display: "flex", justifyContent: "space-between",
                  alignItems: "center", padding: "8px 0",
                  borderBottom: i < d.invoices.length - 1 ? "1px solid rgba(255,255,255,0.05)" : "none" }}>
                  <div>
                    <p style={{ fontSize: 13, color: "#fff", fontWeight: 600 }}>
                      {fmtUsd(inv.amount)} {inv.currency}
                      <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 400,
                        color: inv.status === "paid" ? "#4ade80" : "#ef4444" }}>
                        {inv.status.toUpperCase()}
                      </span>
                    </p>
                    <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                      {fmtDate(inv.created)}{inv.description ? " · " + inv.description : ""}
                    </p>
                  </div>
                  {inv.hostedUrl && (
                    <a href={inv.hostedUrl} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 10, color: "#818cf8", textDecoration: "none",
                        display: "flex", alignItems: "center", gap: 3 }}>
                      View <ArrowUpRight size={9} />
                    </a>
                  )}
                </div>
              ))}
            </div>

            {/* Recent trades */}
            {(d.user.tradeLogs ?? []).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
                  textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 8 }}>
                  Recent Trades
                </p>
                {(d.user.tradeLogs ?? []).slice(0, 8).map((t, i) => (
                  <div key={t.id} style={{ display: "flex", justifyContent: "space-between",
                    padding: "5px 0", borderBottom: i < 7 ? "1px solid rgba(255,255,255,0.04)" : "none",
                    fontSize: 12 }}>
                    <span style={{ color: t.action === "buy" ? "#4ade80" : "#ef4444",
                      fontWeight: 600, minWidth: 36 }}>{t.action.toUpperCase()}</span>
                    <span style={{ color: "#fff", flex: 1, marginLeft: 8 }}>{t.symbol}</span>
                    {t.pnl !== null && (
                      <span style={{ color: t.pnl >= 0 ? "#4ade80" : "#ef4444",
                        fontVariantNumeric: "tabular-nums" }}>
                        {t.pnl >= 0 ? "+" : ""}{fmtUsd(t.pnl)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Venues */}
            {(d.user.venues ?? []).length > 0 && (
              <div>
                <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
                  textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 8 }}>
                  Connected Venues
                </p>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {(d.user.venues ?? []).map(v => (
                    <span key={v.id} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 6,
                      background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                      color: "rgba(255,255,255,0.6)" }}>
                      {v.displayName || v.type} {v.isPaper ? "(paper)" : "(live)"}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

// ── Users Tab ─────────────────────────────────────────────────────────────────
function UsersTab() {
  const [users, setUsers]           = useState<UserRow[]>([]);
  const [total, setTotal]           = useState(0);
  const [page, setPage]             = useState(1);
  const [query, setQuery]           = useState("");
  const [planFilter, setPlanFilter] = useState("ALL");
  const [loading, setLoading]       = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ q: query, plan: planFilter, page: String(page) });
    const res = await fetch("/api/admin/users?" + params.toString(), { credentials: "same-origin" });
    const d = await res.json();
    setUsers(d.users ?? []); setTotal(d.total ?? 0);
    setLoading(false);
  }, [query, planFilter, page]);

  useEffect(() => { const id = setTimeout(load, 300); return () => clearTimeout(id); }, [load]);

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
          <Search size={13} style={{ position: "absolute", left: 12, top: "50%",
            transform: "translateY(-50%)", color: "rgba(255,255,255,0.3)", pointerEvents: "none" }} />
          <input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }}
            placeholder="Search email, name, or Clerk ID…"
            style={{ width: "100%", paddingLeft: 34, paddingRight: 12, paddingTop: 9, paddingBottom: 9,
              borderRadius: 10, background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.1)", color: "#fff", fontSize: 13,
              outline: "none", boxSizing: "border-box" as const }} />
        </div>
        {["ALL","FREE","STARTER","PRO","ENTERPRISE"].map(p => (
          <button key={p} onClick={() => { setPlanFilter(p); setPage(1); }}
            style={{ padding: "7px 12px", borderRadius: 8, fontSize: 11, cursor: "pointer",
              fontWeight: planFilter === p ? 700 : 400,
              background: planFilter === p ? (PLAN_COLOR[p] ?? "rgba(255,255,255,0.1)") + "20" : "rgba(255,255,255,0.04)",
              border: "1px solid " + (planFilter === p ? (PLAN_COLOR[p] ?? "rgba(255,255,255,0.3)") : "rgba(255,255,255,0.1)"),
              color: planFilter === p ? (PLAN_COLOR[p] ?? "#fff") : "rgba(255,255,255,0.5)" }}>
            {p}
          </button>
        ))}
      </div>

      <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginBottom: 10 }}>
        {loading ? "Loading…" : fmt(total) + " users"}
      </p>

      <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
        borderRadius: 14, overflow: "hidden" }}>
        {/* Header row */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 70px 70px 18px",
          padding: "10px 16px", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          {["User", "Plan", "MRR", ""].map(h => (
            <span key={h} style={{ fontSize: 10, color: "rgba(255,255,255,0.25)",
              textTransform: "uppercase" as const, letterSpacing: "0.07em", fontWeight: 600 }}>{h}</span>
          ))}
        </div>

        {users.map((u, i) => (
          <div key={u.id} onClick={() => setSelectedId(u.id)}
            style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 70px 70px 18px",
              alignItems: "center", padding: "12px 16px", cursor: "pointer",
              borderBottom: i < users.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              transition: "background 0.1s" }}>
            <div>
              <p style={{ fontSize: 13, color: "#fff", fontWeight: 500 }}>{u.name ?? u.email}</p>
              {u.name && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>{u.email}</p>}
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginTop: 1 }}>
                {"Joined " + fmtDate(u.createdAt) + " · " + u._count.tradeLogs + " trades"}
              </p>
            </div>
            <PlanBadge plan={u.plan} />
            <span style={{ fontSize: 12, color: PLAN_PRICE[u.plan] > 0 ? "#4ade80" : "rgba(255,255,255,0.25)",
              fontWeight: 600 }}>
              {PLAN_PRICE[u.plan] > 0 ? "$" + PLAN_PRICE[u.plan] + "/mo" : "—"}
            </span>
            <ChevronRight size={13} style={{ color: "rgba(255,255,255,0.2)" }} />
          </div>
        ))}

        {!loading && users.length === 0 && (
          <p style={{ padding: "20px 16px", fontSize: 13, color: "rgba(255,255,255,0.25)" }}>
            No users found
          </p>
        )}
      </div>

      {total > 25 && (
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14 }}>
          <button onClick={() => setPage(p => Math.max(p - 1, 1))} disabled={page === 1}
            style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, cursor: "pointer",
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
              color: "rgba(255,255,255,0.5)", opacity: page === 1 ? 0.4 : 1 }}>← Prev</button>
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", lineHeight: "32px" }}>Page {page}</span>
          <button onClick={() => setPage(p => p + 1)} disabled={users.length < 25}
            style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, cursor: "pointer",
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
              color: "rgba(255,255,255,0.5)", opacity: users.length < 25 ? 0.4 : 1 }}>Next →</button>
        </div>
      )}

      <AnimatePresence>
        {selectedId && <UserDetailPanel userId={selectedId} onClose={() => setSelectedId(null)} />}
      </AnimatePresence>
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────
function OverviewTab() {
  const [stats, setStats]     = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/stats", { credentials: "same-origin" });
      if (res.status === 403) { setError("Admin access denied"); setLoading(false); return; }
      setStats(await res.json());
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 13 }}>Loading…</p>;
  if (error)   return <p style={{ color: "#ef4444" }}>{error}</p>;

  const s = stats!;
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 20 }}>
        <Stat icon={DollarSign} label="MRR"         value={fmtUsd(s.revenue.mrr_usd)} sub="Monthly recurring" color="#4ade80" />
        <Stat icon={TrendingUp} label="ARR"          value={fmtUsd(s.revenue.arr_usd)} sub="Annualised"        color="#4ade80" />
        <Stat icon={Users}      label="Paying"       value={fmt(s.users.paying)}        sub={"of " + fmt(s.users.total) + " total"} color="#818cf8" />
        <Stat icon={Activity}   label="Live agents"  value={String(s.activity.active_agents_live)} sub={s.activity.ws_clients + " WS clients"} color="#fbbf24" />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 20 }}>
        <Stat icon={Users}      label="New today"  value={fmt(s.users.new_24h)} color="#fff" />
        <Stat icon={Users}      label="New 7d"     value={fmt(s.users.new_7d)}  color="#fff" />
        <Stat icon={BarChart2}  label="Trades 24h" value={fmt(s.activity.trades_24h)} color="#fff" />
        <Stat icon={Server}     label="Uptime"     value={fmtUptime(s.activity.server_uptime_s)} color="#4ade80" />
      </div>
      <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
        borderRadius: 14, padding: "18px 20px", marginBottom: 20 }}>
        <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 14 }}>Users by plan</p>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {Object.entries(s.users.by_plan).map(([plan, count]) => (
            <div key={plan}>
              <span style={{ fontSize: 9, fontWeight: 700, color: PLAN_COLOR[plan] ?? "#888",
                textTransform: "uppercase" as const, letterSpacing: "0.08em" }}>{plan}</span>
              <p style={{ fontSize: 28, fontWeight: 800, color: "#fff", fontVariantNumeric: "tabular-nums" }}>{fmt(count)}</p>
              <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                {(PLAN_PRICE[plan] ?? 0) > 0 ? fmtUsd((PLAN_PRICE[plan] ?? 0) * count) + "/mo" : "free"}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 14, padding: "16px 18px" }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
            textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 12 }}>Recent signups</p>
          {s.recent_signups.slice(0, 8).map((u, i) => (
            <div key={u.clerkId} style={{ display: "flex", justifyContent: "space-between",
              alignItems: "center", padding: "6px 0",
              borderBottom: i < 7 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
              <div>
                <p style={{ fontSize: 12, color: "#fff" }}>{u.email}</p>
                <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>{fmtDate(u.createdAt)}</p>
              </div>
              <PlanBadge plan={u.plan} />
            </div>
          ))}
        </div>
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 14, padding: "16px 18px" }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.3)",
            textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 12 }}>
            {"Live agents (" + s.active_agents.length + ")"}
          </p>
          {s.active_agents.length === 0
            ? <p style={{ fontSize: 12, color: "rgba(255,255,255,0.25)" }}>None running</p>
            : s.active_agents.slice(0, 6).map((a, i) => (
              <div key={i} style={{ padding: "6px 0",
                borderBottom: i < Math.min(s.active_agents.length, 6) - 1 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <p style={{ fontSize: 11, color: "#fff" }}>{(a.symbols ?? []).join(", ")} · {a.venue}</p>
                  <span style={{ fontSize: 9, color: a.isPaper ? "#818cf8" : "#ef4444", fontWeight: 700 }}>
                    {a.isPaper ? "PAPER" : "LIVE"}
                  </span>
                </div>
                <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>Since {fmtDate(a.startedAt)}</p>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const [tab, setTab] = useState<"overview" | "users">("overview");

  return (
    <div className="dvh-min" style={{ background: "#080808", padding: "16px 12px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <Link href="/dashboard" style={{ color: "rgba(255,255,255,0.3)", display: "flex" }}>
            <ArrowLeft size={16} />
          </Link>
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 800, color: "#fff" }}>Admin Dashboard</h1>
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
              Platform overview · Users · Revenue · Customer support
            </p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
            <Shield size={13} style={{ color: "#4ade80" }} />
            <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>Admin only</span>
          </div>
        </div>

        <div style={{ display: "flex", gap: 4, marginBottom: 20,
          background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 12, padding: 4, width: "fit-content" }}>
          {[
            { id: "overview" as const, label: "Overview",         icon: BarChart2 },
            { id: "users"    as const, label: "Users & Payments", icon: Users     },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              style={{ display: "flex", alignItems: "center", gap: 7,
                padding: "7px 16px", borderRadius: 9, fontSize: 12, fontWeight: 600,
                cursor: "pointer", border: "none", transition: "all 0.15s",
                background: tab === t.id ? "rgba(255,255,255,0.1)" : "transparent",
                color: tab === t.id ? "#fff" : "rgba(255,255,255,0.4)" }}>
              <t.icon size={12} />
              {t.label}
            </button>
          ))}
        </div>

        {tab === "overview" && <OverviewTab />}
        {tab === "users"    && <UsersTab />}

        <p style={{ textAlign: "center", fontSize: 10, color: "rgba(255,255,255,0.12)", marginTop: 28 }}>
          Admin only · All overrides are audit-logged · All times local
        </p>
      </div>
    </div>
  );
}
