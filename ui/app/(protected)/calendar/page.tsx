"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Calendar } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Event {
  name?: string;
  event?: string;
  date?: string;
  datetime?: string;
  time?: string;
  currency?: string;
  country?: string;
  importance?: string;
}

export default function CalendarPage() {
  const isMobile = useIsMobile();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/calendar/all`)
      .then(r => r.json())
      .then((d: { events?: Event[] }) => { setEvents(d.events ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const now = Date.now();
  const parseTs = (e: Event): number | null => {
    for (const k of ["date", "datetime", "time"] as const) {
      const v = e[k];
      if (v) { const t = new Date(v).getTime(); if (!isNaN(t)) return t; }
    }
    return null;
  };
  const sorted = events
    .map(e => ({ e, ts: parseTs(e) }))
    .filter(x => x.ts !== null)
    .sort((a, b) => (a.ts! - b.ts!));

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Economic Calendar</span>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 900, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <Calendar size={18} style={{ color: "#fbbf24" }} />
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "#fff" }}>High-Impact Events</h1>
        </div>
        <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 28, lineHeight: 1.6 }}>
          Your agent automatically pauses trading 5 minutes before any high-impact economic event
          and resumes once the volatility window closes — protecting your positions from news spikes.
        </p>

        {loading ? (
          <p style={{ color: "var(--muted)" }}>Loading…</p>
        ) : sorted.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>No upcoming high-impact events found. Calendar data refreshes every hour.</p>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sorted.map((x, i) => {
              const future = x.ts! > now;
              const diff   = Math.abs(x.ts! - now);
              const hrs    = Math.floor(diff / 3_600_000);
              const mins   = Math.floor((diff % 3_600_000) / 60_000);
              const label  = hrs >= 24 ? `${Math.floor(hrs/24)}d ${hrs%24}h` : hrs >= 1 ? `${hrs}h ${mins}m` : `${mins}m`;
              const e      = x.e;
              return (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
                  background: future ? "rgba(251,191,36,0.04)" : "rgba(255,255,255,0.02)",
                  border: `1px solid ${future ? "rgba(251,191,36,0.15)" : "rgba(255,255,255,0.05)"}`,
                  borderRadius: 10,
                }}>
                  <div style={{ width: 64, textAlign: "center", fontSize: 11, color: future ? "#fbbf24" : "var(--muted)",
                    fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                    {future ? `in ${label}` : `${label} ago`}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 13, fontWeight: 500, color: "#fff" }}>{e.name ?? e.event ?? "Event"}</p>
                    <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                      {new Date(x.ts!).toLocaleString()}
                      {e.currency && <> · {e.currency}</>}
                    </p>
                  </div>
                  {e.importance && (
                    <span style={{ padding: "2px 7px", borderRadius: 6, fontSize: 9, fontWeight: 700,
                      textTransform: "uppercase", letterSpacing: "0.08em",
                      background: "rgba(239,68,68,0.1)", color: "#ef4444",
                      border: "1px solid rgba(239,68,68,0.2)" }}>
                      {e.importance}
                    </span>
                  )}
                </div>
              );
            })}
          </motion.div>
        )}
      </main>
    </div>
  );
}
