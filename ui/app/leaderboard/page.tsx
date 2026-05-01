"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Trophy, TrendingUp, ArrowLeft, Brain, Zap } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useToast } from "@/components/Toast";

interface PersonaRow {
  id: string;
  name: string;
  tagline: string;
  style: string;
  riskProfile: string;
  winRateRange: string;
  sessions: number;
  total_trades: number;
  win_rate_pct: number | null;
  gross_pnl: number;
  active: boolean;
}

function PersonaLeaderboard() {
  const [rows, setRows]   = useState<PersonaRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/agent/personas/leaderboard", { credentials: "same-origin" })
      .then(r => r.json())
      .then(d => { setRows(d.leaderboard ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const STYLE_COLOR: Record<string, string> = {
    momentum: "#4ade80", scalping: "#fbbf24", swing: "#818cf8", news: "#f472b6",
  };
  const RANK_ICONS = ["🥇", "🥈", "🥉", "4️⃣"];

  return (
    <div style={{ marginBottom: 36 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <Brain size={18} style={{ color: "#818cf8" }} />
        <h2 style={{ fontSize: 18, fontWeight: 600, color: "#fff" }}>AI Persona Performance</h2>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>live session data</span>
      </div>
      {loading ? (
        <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {rows.map((row, i) => {
            const styleColor = STYLE_COLOR[row.style] ?? "#888";
            return (
              <motion.div key={row.id}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: i * 0.05 }}
                style={{
                  background: "rgba(255,255,255,0.03)", border: `1px solid ${row.active ? "rgba(74,222,128,0.25)" : "rgba(255,255,255,0.07)"}`,
                  borderRadius: 14, padding: "16px 20px",
                  display: "grid", gridTemplateColumns: "36px 1fr repeat(3,90px) 80px", gap: 14, alignItems: "center",
                }}
              >
                <span style={{ fontSize: i < 3 ? 18 : 13, textAlign: "center" }}>{RANK_ICONS[i] ?? `#${i+1}`}</span>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <p style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>{row.name}</p>
                    {row.active && (
                      <span style={{ fontSize: 9, fontWeight: 700, color: "#4ade80",
                        background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.2)",
                        padding: "1px 6px", borderRadius: 4, letterSpacing: "0.07em" }}>LIVE</span>
                    )}
                  </div>
                  <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{row.tagline}</p>
                  <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    <span style={{ fontSize: 9, color: styleColor, background: `${styleColor}18`,
                      border: `1px solid ${styleColor}30`, padding: "1px 6px", borderRadius: 4,
                      textTransform: "uppercase", letterSpacing: "0.06em" }}>{row.style}</span>
                    <span style={{ fontSize: 9, color: "rgba(255,255,255,0.3)" }}>{row.riskProfile} risk</span>
                  </div>
                </div>
                {[
                  { label: "Win Rate", value: row.win_rate_pct !== null ? `${row.win_rate_pct}%` : row.winRateRange, positive: (row.win_rate_pct ?? 50) >= 50 },
                  { label: "P&L", value: row.gross_pnl !== 0 ? `${row.gross_pnl >= 0 ? "+" : ""}$${row.gross_pnl.toFixed(2)}` : "—", positive: row.gross_pnl >= 0 },
                  { label: "Trades", value: row.total_trades > 0 ? row.total_trades.toString() : "—", positive: true },
                ].map(m => (
                  <div key={m.label} style={{ textAlign: "right" }}>
                    <p style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{m.label}</p>
                    <p style={{ fontSize: 14, fontWeight: 600, fontVariantNumeric: "tabular-nums",
                      color: m.positive ? "var(--green)" : "var(--red)" }}>{m.value}</p>
                  </div>
                ))}
                <Link href="/dashboard"
                  style={{ padding: "6px 10px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                    background: `${styleColor}15`, border: `1px solid ${styleColor}30`,
                    color: styleColor, textDecoration: "none", textAlign: "center" }}>
                  Use →
                </Link>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface Listing {
  id: string;
  name: string;
  description: string | null;
  sharpe: number;
  totalReturn: number;
  maxDrawdown: number;
  price: number;
  createdAt: string;
  user: { id: string; name: string | null };
}

const MEDAL = ["🥇", "🥈", "🥉"];

export default function LeaderboardPage() {
  const toast = useToast();
  const [listings, setListings] = useState<Listing[]>([]);
  const [sort, setSort]         = useState<"sharpe" | "return">("sharpe");
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/marketplace?sort=${sort}&limit=100`)
      .then(r => r.json())
      .then((d: { listings: Listing[] }) => { setListings(d.listings ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [sort]);

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <header style={{
        padding: "0 28px", height: 56, borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Leaderboard</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {(["sharpe", "return"] as const).map(s => (
            <button key={s} onClick={() => setSort(s)} style={{
              padding: "5px 12px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
              background: sort === s ? "rgba(255,255,255,0.1)" : "transparent",
              border: sort === s ? "1px solid rgba(255,255,255,0.2)" : "1px solid transparent",
              color: sort === s ? "#fff" : "var(--muted)",
            }}>
              {s === "sharpe" ? "Sharpe" : "Return"}
            </button>
          ))}
        </div>
      </header>

      <main style={{ padding: "32px 40px 60px", maxWidth: 900, margin: "0 auto" }}>
        <PersonaLeaderboard />

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Trophy size={20} style={{ color: "#fbbf24" }} />
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "#fff" }}>Top Strategies</h1>
          <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>platform leaderboard · anonymous</span>
        </div>

        {loading ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</p>
        ) : listings.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>No public strategies yet. Be the first to publish!</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {listings.map((l, i) => (
              <motion.div
                key={l.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: i * 0.03 }}
                style={{
                  display: "grid", gridTemplateColumns: "36px 1fr repeat(4, 80px) 80px",
                  alignItems: "center", gap: 14,
                  background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: 12, padding: "16px 20px",
                }}
              >
                <span style={{ fontSize: i < 3 ? 18 : 12, color: "var(--muted)", textAlign: "center" }}>
                  {i < 3 ? MEDAL[i] : `#${i + 1}`}
                </span>
                <div>
                  <Link href={`/marketplace/${l.id}`} style={{ textDecoration: "none" }}>
                    <p style={{ fontSize: 14, fontWeight: 600, color: "#fff", cursor: "pointer" }}>{l.name}</p>
                  </Link>
                  {l.description && <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{l.description}</p>}
                </div>
                {[
                  { label: "Sharpe", value: l.sharpe.toFixed(2), positive: l.sharpe > 0 },
                  { label: "Return", value: `${l.totalReturn >= 0 ? "+" : ""}${l.totalReturn.toFixed(1)}%`, positive: l.totalReturn >= 0 },
                  { label: "Max DD", value: `-${l.maxDrawdown.toFixed(1)}%`, positive: l.maxDrawdown < 15 },
                  { label: "Price",  value: l.price === 0 ? "Free" : `$${l.price}/mo`, positive: true },
                ].map(m => (
                  <div key={m.label} style={{ textAlign: "right" }}>
                    <p style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{m.label}</p>
                    <p style={{ fontSize: 14, fontWeight: 500, color: m.positive ? "var(--green)" : "var(--red)", fontVariantNumeric: "tabular-nums" }}>{m.value}</p>
                  </div>
                ))}
                <button
                  onClick={async () => {
                    const r = await fetch("/api/copy", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ leaderId: l.user.id, maxAllocPct: 3 }),
                    }).catch(() => null);
                    if (r?.ok) toast('Now following this trader', 'success'); else toast('Failed to start copy trading — upgrade to PRO', 'error');
                  }}
                  style={{ padding: "6px 10px", borderRadius: 8, fontSize: 11, cursor: "pointer",
                    background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.2)",
                    color: "#4ade80", fontWeight: 600 }}>
                  Copy
                </button>
              </motion.div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 32, padding: "20px 24px", background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 14 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "#fff", marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
            <TrendingUp size={14} /> Publish your strategy
          </p>
          <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
            Run a backtest, then publish your agent config to the marketplace. Subscribers pay a monthly fee — you receive 70%.
          </p>
          <Link href="/backtest" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 12, background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, padding: "7px 14px", color: "#fff", fontSize: 12, textDecoration: "none", fontWeight: 500 }}>
            Run a backtest →
          </Link>
        </div>
      </main>
    </div>
  );
}
