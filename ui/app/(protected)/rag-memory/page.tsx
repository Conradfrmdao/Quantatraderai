"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Brain, Trash2 } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

interface Memory {
  id: string; asset: string; action: string;
  rationale: string; qualityScore: number;
  similarity?: number; createdAt: string;
}

export default function RagMemoryPage() {
  const isMobile              = useIsMobile();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetch("/api/rag-memory?limit=100")
      .then(r => r.json())
      .then((d: { memories: Memory[] }) => { setMemories(d.memories ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const del = async (id: string) => {
    await fetch(`/api/rag-memory?id=${id}`, { method: "DELETE" });
    setMemories(m => m.filter(x => x.id !== id));
  };

  const ACTION_COLOR: Record<string, string> = {
    buy: "#4ade80", sell: "#ef4444", hold: "#888",
  };

  return (
    <div className="dvh-min" style={{ background: "var(--bg)" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ RAG Memory</span>
        <span style={{ marginLeft: "auto", padding: "3px 10px", borderRadius: 20, fontSize: 11,
          background: "rgba(255,255,255,0.05)", color: "var(--muted)" }}>
          {memories.length} stored decisions
        </span>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <Brain size={18} style={{ color: "#a78bfa" }} />
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "#fff" }}>Trade Memory</h1>
          <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 9px", borderRadius: 20, background: "rgba(167,139,250,0.12)", color: "#a78bfa", border: "1px solid rgba(167,139,250,0.25)", marginLeft: 4 }}>PRO</span>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 28, lineHeight: 1.6 }}>
          Every decision the AI makes is stored here as a vector embedding. Before each tick the agent
          retrieves the 5 most similar past decisions and uses them to improve future choices.
          Quality score updates when a position closes — positive PnL reinforces, negative PnL reduces.
        </p>

        {loading ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</p>
        ) : memories.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            No trade memories yet. Start the agent and let it make a few decisions — it will learn from every trade automatically.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {memories.map((m, i) => (
              <motion.div key={m.id}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.02 }}
                style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: "14px 18px",
                  background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: 12 }}>
                {/* Action badge */}
                <span style={{ padding: "3px 9px", borderRadius: 7, fontSize: 9, fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.08em", flexShrink: 0, marginTop: 2,
                  background: `${ACTION_COLOR[m.action] ?? "#888"}15`,
                  color: ACTION_COLOR[m.action] ?? "#888",
                  border: `1px solid ${ACTION_COLOR[m.action] ?? "#888"}30` }}>
                  {m.action}
                </span>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 5 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>{m.asset}</span>
                    {/* Quality score bar */}
                    <div style={{ display: "flex", alignItems: "center", gap: 5, flex: 1 }}>
                      <div style={{ flex: 1, maxWidth: 80, height: 3,
                        background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${m.qualityScore * 100}%` }}
                          transition={{ duration: 0.6 }}
                          style={{ height: "100%", borderRadius: 2,
                            background: m.qualityScore > 0.5 ? "#4ade80" : "#ef4444" }}
                        />
                      </div>
                      <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)",
                        fontVariantNumeric: "tabular-nums" }}>
                        Q: {(m.qualityScore * 100).toFixed(0)}
                      </span>
                    </div>
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>
                      {new Date(m.createdAt).toLocaleDateString()}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", lineHeight: 1.5,
                    overflow: "hidden", display: "-webkit-box",
                    WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                    {m.rationale}
                  </p>
                </div>

                <button onClick={() => del(m.id)}
                  style={{ background: "none", border: "none", color: "rgba(255,255,255,0.15)",
                    cursor: "pointer", padding: 4, flexShrink: 0 }}>
                  <Trash2 size={12} />
                </button>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
