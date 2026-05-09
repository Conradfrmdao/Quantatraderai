"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Users, UserPlus, UserMinus, Copy } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

interface Relationship {
  id: string;
  isActive: boolean;
  maxAllocPct: number;
  createdAt: string;
  leader?:   { id: string; name: string | null; email: string };
  follower?: { id: string; name: string | null; email: string };
}

interface CopyData {
  following: Relationship[];
  followers: Relationship[];
}

const inputStyle: React.CSSProperties = {
  padding: "9px 14px", borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(255,255,255,0.04)", color: "#fff",
  fontSize: 13, outline: "none",
};

export default function CopyTradingPage() {
  const isMobile                = useIsMobile();
  const [data, setData]         = useState<CopyData | null>(null);
  const [leaderId, setLeaderId] = useState("");
  const [allocPct, setAllocPct] = useState("3");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const [planGated, setPlanGated] = useState(false);

  const load = useCallback(() => {
    fetch("/api/copy").then(r => {
      if (r.status === 402) { setPlanGated(true); return null; }
      return r.json();
    }).then((d: CopyData | null) => { if (d) setData(d); }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const follow = async () => {
    if (!leaderId.trim()) { setError("Enter a leader User ID"); return; }
    setLoading(true); setError("");
    const res = await fetch("/api/copy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ leaderId: leaderId.trim(), maxAllocPct: parseFloat(allocPct) || 3 }),
    }).catch(() => null);
    setLoading(false);
    if (res?.ok) { setLeaderId(""); load(); }
    else setError("Could not follow — check the User ID");
  };

  const unfollow = async (lid: string) => {
    await fetch(`/api/copy?leaderId=${lid}`, { method: "DELETE" });
    load();
  };

  const active     = data?.following.filter(r => r.isActive) ?? [];
  const followers  = data?.followers ?? [];

  if (planGated) {
    return (
      <div style={{ background: "var(--bg)", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{ textAlign: "center", maxWidth: 400 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
          <p style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 8 }}>PRO Feature</p>
          <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 24, lineHeight: 1.6 }}>
            Copy trading is available on the PRO plan ($99/mo). Mirror top traders automatically, scaled to your risk settings.
          </p>
          <a href="/billing" style={{ display: "inline-flex", alignItems: "center", gap: 8,
            padding: "12px 28px", borderRadius: 12, background: "rgba(74,222,128,0.12)",
            border: "1px solid rgba(74,222,128,0.3)", color: "#4ade80",
            fontWeight: 700, fontSize: 14, textDecoration: "none" }}>
            Upgrade to PRO →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="dvh-min" style={{ background: "var(--bg)" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Copy Trading</span>
        {followers.length > 0 && (
          <span style={{ marginLeft: "auto", padding: "3px 10px", borderRadius: 20, fontSize: 11,
            background: "rgba(74,222,128,0.1)", color: "var(--green)" }}>
            {followers.length} {followers.length === 1 ? "follower" : "followers"}
          </span>
        )}
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 900, margin: "0 auto" }}>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Copy size={20} style={{ color: "#4ade80" }} />
          <h1 style={{ fontSize: 22, fontWeight: 600, color: "#fff" }}>Copy Trading</h1>
          <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 9px", borderRadius: 20, background: "rgba(167,139,250,0.12)", color: "#a78bfa", border: "1px solid rgba(167,139,250,0.25)", marginLeft: 4 }}>PRO</span>
        </div>

        {/* Follow form */}
        <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 16, padding: "22px 24px", marginBottom: 28 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "#fff", marginBottom: 16,
            display: "flex", alignItems: "center", gap: 8 }}>
            <UserPlus size={14} /> Follow a trader
          </p>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 140px auto", gap: 10 }}>
            <input style={{ ...inputStyle, width: "100%" }} placeholder="Paste a User ID from the leaderboard"
              value={leaderId} onChange={e => setLeaderId(e.target.value)} />
            <div style={{ position: "relative" }}>
              <input style={{ ...inputStyle, width: "100%", paddingRight: 30 }}
                type="number" min="0.1" max="100" step="0.5"
                value={allocPct} onChange={e => setAllocPct(e.target.value)} />
              <span style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                fontSize: 11, color: "var(--muted)" }}>% max</span>
            </div>
            <button onClick={follow} disabled={loading}
              style={{ padding: "9px 20px", borderRadius: 10, background: "rgba(74,222,128,0.12)",
                border: "1px solid rgba(74,222,128,0.25)", color: "var(--green)",
                fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap",
                opacity: loading ? 0.6 : 1 }}>
              {loading ? "…" : "Follow"}
            </button>
          </div>
          {error && <p style={{ color: "var(--red)", fontSize: 12, marginTop: 8 }}>{error}</p>}
          <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 10, lineHeight: 1.5 }}>
            When the leader places a trade your account automatically mirrors it, scaled to your max allocation %.
            All signals pass through your personal RiskManager first.
          </p>
        </div>

        {/* Currently following */}
        <div style={{ marginBottom: 28 }}>
          <p style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.1em", color: "rgba(255,255,255,0.3)", marginBottom: 12 }}>
            You are following ({active.length})
          </p>
          {active.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--muted)" }}>Not following anyone yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <AnimatePresence>
                {active.map(r => (
                  <motion.div key={r.id}
                    initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                    style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px",
                      background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
                      borderRadius: 12 }}>
                    <div style={{ width: 34, height: 34, borderRadius: "50%", background: "rgba(74,222,128,0.1)",
                      border: "1px solid rgba(74,222,128,0.2)", display: "flex", alignItems: "center",
                      justifyContent: "center", flexShrink: 0 }}>
                      <Users size={14} style={{ color: "var(--green)" }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                        {r.leader?.name ?? r.leader?.email ?? r.leader?.id}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                        Max {r.maxAllocPct}% per trade · Since {new Date(r.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                    <button onClick={() => r.leader?.id && unfollow(r.leader.id)}
                      style={{ padding: "6px 12px", borderRadius: 8, fontSize: 11, cursor: "pointer",
                        background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)",
                        color: "var(--red)", display: "flex", alignItems: "center", gap: 5 }}>
                      <UserMinus size={11} /> Unfollow
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Your followers */}
        {followers.length > 0 && (
          <div>
            <p style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase",
              letterSpacing: "0.1em", color: "rgba(255,255,255,0.3)", marginBottom: 12 }}>
              Your followers ({followers.length})
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {followers.map(r => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px",
                  background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)",
                  borderRadius: 10 }}>
                  <Users size={13} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} />
                  <p style={{ fontSize: 13, color: "rgba(255,255,255,0.6)", flex: 1 }}>
                    {r.follower?.name ?? r.follower?.email ?? r.follower?.id}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--muted)" }}>
                    max {r.maxAllocPct}%
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginTop: 36, padding: "18px 22px", background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.05)", borderRadius: 14 }}>
          <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
            Find top traders on the <Link href="/leaderboard" style={{ color: "#4ade80" }}>leaderboard</Link> and
            copy their User ID to start mirroring their trades. Your risk manager always applies first —
            if a mirrored trade would breach your limits it is silently skipped.
          </p>
        </div>
      </main>
    </div>
  );
}
