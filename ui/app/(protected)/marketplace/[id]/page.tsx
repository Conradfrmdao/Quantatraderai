"use client";
import { use, useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, TrendingUp, UserPlus, BarChart2, Star } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useToast } from "@/components/Toast";
import { useIsMobile } from "@/hooks/useIsMobile";

interface Listing {
  id: string;
  name: string;
  description: string | null;
  config: string;
  sharpe: number;
  totalReturn: number;
  maxDrawdown: number;
  price: number;
  createdAt: string;
  user: { id: string; name: string | null };
}

export default function StrategyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isMobile = useIsMobile();
  const toast = useToast();
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [following, setFollowing] = useState(false);

  useEffect(() => {
    fetch(`/api/marketplace/${id}`)
      .then(r => r.json())
      .then((d: Listing | { error: string }) => {
        if ("error" in d) { toast(d.error, "error"); return; }
        setListing(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id, toast]);

  const follow = async () => {
    if (!listing) return;
    setFollowing(true);
    const res = await fetch("/api/copy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ leaderId: listing.user.id, maxAllocPct: 3 }),
    }).catch(() => null);
    setFollowing(false);
    if (res?.ok) toast(`Now copying ${listing.user.name ?? "trader"}`, "success");
    else         toast("Failed to start copy trading", "error");
  };

  let cfg: Record<string, unknown> = {};
  try { if (listing?.config) cfg = JSON.parse(listing.config); } catch {}

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/marketplace" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Marketplace / Strategy</span>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "40px 40px 60px", maxWidth: 900, margin: "0 auto" }}>
        {loading ? (
          <p style={{ color: "var(--muted)" }}>Loading…</p>
        ) : !listing ? (
          <p style={{ color: "var(--muted)" }}>Strategy not found.</p>
        ) : (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
              <div>
                <h1 style={{ fontSize: 28, fontWeight: 600, color: "#fff", marginBottom: 6 }}>{listing.name}</h1>
                {listing.user.name && <p style={{ fontSize: 13, color: "var(--muted)" }}>
                  by <Link href={`/leaderboard`} style={{ color: "#a78bfa" }}>{listing.user.name}</Link>
                </p>}
              </div>
              <div style={{ textAlign: "right" }}>
                <p style={{ fontSize: 30, fontWeight: 700, color: listing.price === 0 ? "#4ade80" : "#a78bfa", fontVariantNumeric: "tabular-nums" }}>
                  {listing.price === 0 ? "Free" : `$${listing.price}`}
                </p>
                {listing.price > 0 && <p style={{ fontSize: 12, color: "var(--muted)" }}>per month</p>}
              </div>
            </div>

            {listing.description && (
              <p style={{ fontSize: 14, color: "rgba(255,255,255,0.7)", lineHeight: 1.7, marginBottom: 32 }}>
                {listing.description}
              </p>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 32 }}>
              {[
                { label: "Sharpe Ratio",  value: listing.sharpe.toFixed(3), positive: listing.sharpe > 0 },
                { label: "Total Return",  value: `${listing.totalReturn >= 0 ? "+" : ""}${listing.totalReturn.toFixed(2)}%`, positive: listing.totalReturn >= 0 },
                { label: "Max Drawdown",  value: `-${listing.maxDrawdown.toFixed(2)}%`, positive: listing.maxDrawdown < 15 },
                { label: "Published",     value: new Date(listing.createdAt).toLocaleDateString() },
              ].map(m => (
                <div key={m.label} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: 12, padding: "16px 18px" }}>
                  <p style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{m.label}</p>
                  <p style={{ fontSize: 20, fontWeight: 500,
                    color: m.positive === true ? "var(--green)" : m.positive === false ? "var(--red)" : "#fff",
                    fontVariantNumeric: "tabular-nums" }}>{m.value}</p>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 12, marginBottom: 32, flexWrap: "wrap" }}>
              <button onClick={follow} disabled={following} style={{ display: "flex", alignItems: "center", gap: 8,
                padding: "11px 22px", borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: "pointer",
                background: "rgba(74,222,128,0.12)", border: "1px solid rgba(74,222,128,0.3)", color: "#4ade80",
                opacity: following ? 0.6 : 1 }}>
                <UserPlus size={13} /> {following ? "Following…" : "Copy this strategy"}
              </button>
              <Link href={`/backtest?strategy=${listing.id}`} style={{ display: "flex", alignItems: "center", gap: 8,
                padding: "11px 22px", borderRadius: 10, fontSize: 14, fontWeight: 500, textDecoration: "none",
                background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.7)" }}>
                <BarChart2 size={13} /> Backtest on my data
              </Link>
            </div>

            {/* Config preview */}
            {Object.keys(cfg).length > 0 && (
              <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 12, padding: "18px 22px" }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)", marginBottom: 12,
                  textTransform: "uppercase", letterSpacing: "0.1em" }}>Strategy config</p>
                <pre style={{ fontSize: 11, color: "rgba(255,255,255,0.6)", whiteSpace: "pre-wrap",
                  fontFamily: "var(--font-mono, monospace)", lineHeight: 1.6 }}>
                  {JSON.stringify(cfg, null, 2)}
                </pre>
              </div>
            )}
          </motion.div>
        )}
      </main>
    </div>
  );
}
