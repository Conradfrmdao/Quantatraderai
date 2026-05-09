"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Plus, BarChart2, TrendingUp, Star, ShoppingBag } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useToast } from "@/components/Toast";

interface Listing {
  id:          string;
  name:        string;
  description: string | null;
  sharpe:      number;
  totalReturn: number;
  maxDrawdown: number;
  price:       number;
  createdAt:   string;
  user:        { id: string; name: string | null };
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 14px", borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(255,255,255,0.04)", color: "#fff",
  fontSize: 13, outline: "none",
};
const labelStyle: React.CSSProperties = {
  display: "block", fontSize: 11, color: "rgba(255,255,255,0.4)",
  marginBottom: 5, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.07em",
};

function PublishModal({ onClose, onPublished }: { onClose: () => void; onPublished: () => void }) {
  const [form, setForm] = useState({ name: "", description: "", price: "0", isPublic: true });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { setError("Name required"); return; }
    setLoading(true);
    const res = await fetch("/api/marketplace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, price: parseFloat(form.price) || 0 }),
    }).catch(() => null);
    setLoading(false);
    if (res?.ok) { onPublished(); onClose(); }
    else setError("Publish failed");
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 200,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        style={{ background: "#111", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 18,
          padding: 28, width: "100%", maxWidth: 480 }}>
        <p style={{ fontSize: 16, fontWeight: 600, color: "#fff", marginBottom: 20 }}>Publish Strategy</p>
        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Strategy Name</label>
          <input style={inputStyle} value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. RSI Mean-Reversion BTC" />
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Description</label>
          <textarea style={{ ...inputStyle, height: 80, resize: "none" }} value={form.description}
            onChange={e => set("description", e.target.value)} placeholder="What does this strategy do?" />
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Monthly price (USD · 0 = free)</label>
          <input style={inputStyle} type="number" min="0" value={form.price} onChange={e => set("price", e.target.value)} />
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: 20 }}>
          <input type="checkbox" checked={form.isPublic} onChange={e => set("isPublic", e.target.checked)} />
          <span style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>List publicly on marketplace</span>
        </label>
        {error && <p style={{ color: "var(--red)", fontSize: 12, marginBottom: 12 }}>{error}</p>}
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={submit} disabled={loading} style={{ flex: 1, padding: "11px 0", borderRadius: 10,
            background: "#fff", color: "#000", border: "none", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
            {loading ? "Publishing…" : "Publish"}
          </button>
          <button onClick={onClose} style={{ padding: "11px 18px", borderRadius: 10, background: "transparent",
            border: "1px solid rgba(255,255,255,0.12)", color: "rgba(255,255,255,0.5)", cursor: "pointer", fontSize: 13 }}>
            Cancel
          </button>
        </div>
      </motion.div>
    </div>
  );
}

export default function MarketplacePage() {
  const isMobile = useIsMobile();
  const toast = useToast();
  const [listings, setListings]   = useState<Listing[]>([]);
  const [loading, setLoading]     = useState(true);
  const [sort, setSort]           = useState<"sharpe" | "return">("sharpe");
  const [showPublish, setPublish] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`/api/marketplace?sort=${sort}`)
      .then(r => r.json())
      .then((d: { listings: Listing[] }) => { setListings(d.listings ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="dvh-min" style={{ background: "var(--bg)" }}>
      {showPublish && <PublishModal onClose={() => setPublish(false)} onPublished={load} />}

      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56, borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Marketplace</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {(["sharpe", "return"] as const).map(s => (
            <button key={s} onClick={() => setSort(s)} style={{ padding: "5px 12px", borderRadius: 8,
              fontSize: 12, fontWeight: 500, cursor: "pointer",
              background: sort === s ? "rgba(255,255,255,0.1)" : "transparent",
              border: sort === s ? "1px solid rgba(255,255,255,0.2)" : "1px solid transparent",
              color: sort === s ? "#fff" : "var(--muted)" }}>
              {s === "sharpe" ? "Sharpe" : "Return"}
            </button>
          ))}
          <button onClick={() => setPublish(true)} style={{ display: "flex", alignItems: "center", gap: 6,
            padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
            background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", color: "#fff" }}>
            <Plus size={12} /> Publish
          </button>
        </div>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 80px" : "32px 40px 60px", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <ShoppingBag size={20} style={{ color: "#a78bfa" }} />
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "#fff" }}>Strategy Marketplace</h1>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            {listings.length} {listings.length === 1 ? "strategy" : "strategies"} published
          </span>
        </div>

        {loading ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</p>
        ) : listings.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 20px" }}>
            <p style={{ fontSize: 15, color: "rgba(255,255,255,0.4)", marginBottom: 16 }}>
              No strategies published yet.
            </p>
            <button onClick={() => setPublish(true)} style={{ display: "inline-flex", alignItems: "center", gap: 8,
              padding: "11px 24px", borderRadius: 10, background: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(255,255,255,0.15)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              <Plus size={13} /> Be the first to publish
            </button>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fill,minmax(320px,1fr))", gap: 16 }}>
            {listings.map((l, i) => (
              <motion.div key={l.id}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
                  borderRadius: 16, padding: "20px 22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                  <div>
                    <p style={{ fontSize: 15, fontWeight: 600, color: "#fff", marginBottom: 3 }}>{l.name}</p>
                    {l.user.name && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>by {l.user.name}</p>}
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 700, color: l.price === 0 ? "var(--green)" : "#a78bfa",
                    padding: "3px 10px", borderRadius: 20,
                    background: l.price === 0 ? "rgba(74,222,128,0.08)" : "rgba(167,139,250,0.08)",
                    border: `1px solid ${l.price === 0 ? "rgba(74,222,128,0.2)" : "rgba(167,139,250,0.2)"}` }}>
                    {l.price === 0 ? "Free" : `$${l.price}/mo`}
                  </span>
                </div>
                {l.description && (
                  <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", lineHeight: 1.5, marginBottom: 14 }}>
                    {l.description}
                  </p>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, marginBottom: 16 }}>
                  {[
                    { label: "Sharpe",  value: l.sharpe.toFixed(2),             color: l.sharpe > 0 ? "var(--green)" : "var(--red)" },
                    { label: "Return",  value: `${l.totalReturn >= 0 ? "+" : ""}${l.totalReturn.toFixed(1)}%`, color: l.totalReturn >= 0 ? "var(--green)" : "var(--red)" },
                    { label: "Max DD",  value: `-${l.maxDrawdown.toFixed(1)}%`,  color: "rgba(255,255,255,0.6)" },
                  ].map(m => (
                    <div key={m.label} style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "8px 10px" }}>
                      <p style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", textTransform: "uppercase",
                        letterSpacing: "0.07em", marginBottom: 4 }}>{m.label}</p>
                      <p style={{ fontSize: 14, fontWeight: 600, color: m.color, fontVariantNumeric: "tabular-nums" }}>{m.value}</p>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <Link href={`/marketplace/${l.id}`} style={{ flex: 1, padding: "9px 0", borderRadius: 9,
                    fontSize: 12, fontWeight: 600, textAlign: "center", textDecoration: "none",
                    background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)",
                    color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                    <TrendingUp size={11} /> View strategy
                  </Link>
                  <button
                    onClick={async () => {
                      const r = await fetch("/api/copy", { method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ leaderId: l.user.id, maxAllocPct: 3 }) }).catch(() => null);
                      if (r?.ok) alert(`Now copying ${l.user.name ?? "trader"}`);
                    }}
                    style={{ padding: "9px 14px", borderRadius: 9, fontSize: 12, cursor: "pointer",
                      background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.2)",
                      color: "var(--green)", display: "flex", alignItems: "center", gap: 5 }}>
                    <Star size={10} /> Copy
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 32, padding: "20px 24px", background: "rgba(167,139,250,0.04)",
          border: "1px solid rgba(167,139,250,0.15)", borderRadius: 14 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "#fff", marginBottom: 6, display: "flex", gap: 8 }}>
            <BarChart2 size={14} style={{ color: "#a78bfa" }} /> Revenue split
          </p>
          <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
            You keep 70% of every subscription. Set your monthly price and we handle billing,
            churn management, and payouts via Stripe Connect.
            Run a backtest first to generate verified performance metrics.
          </p>
          <Link href="/backtest" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 12,
            background: "rgba(167,139,250,0.1)", border: "1px solid rgba(167,139,250,0.25)",
            borderRadius: 8, padding: "7px 14px", color: "#a78bfa", fontSize: 12, textDecoration: "none", fontWeight: 500 }}>
            Run a backtest →
          </Link>
        </div>
      </main>
    </div>
  );
}
