"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface StatusData {
  status?: string;
  provider?: string;
  model?: string;
  venue?: string;
  tick_count?: number;
  uptime_seconds?: number;
  assets?: string[];
}

function fmtUptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function Chip({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 500,
        textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
      <span style={{ fontSize: 12, color: valueColor ?? "rgba(255,255,255,0.8)", fontWeight: 500 }}>
        {value}
      </span>
    </div>
  );
}

function CalendarChip() {
  const [label, setLabel] = useState<string>("");

  useEffect(() => {
    const load = () =>
      fetch(`${API}/api/calendar/next`)
        .then(r => r.json())
        .then((d: { next_event?: string }) => setLabel(d.next_event ?? ""))
        .catch(() => {});
    load();
    const id = setInterval(load, 300_000); // refresh every 5 min
    return () => clearInterval(id);
  }, []);

  if (!label) return null;

  return (
    <>
      <div style={{ width: 1, height: 16, background: "var(--border)" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 10, color: "#FBBF24" }}>📅</span>
        <span style={{ fontSize: 11, color: "#FBBF24", fontWeight: 500 }}>{label}</span>
      </div>
    </>
  );
}

export function StatusBar({ data }: { data: StatusData | null }) {
  const running = data?.status === "running";

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      style={{
        display: "flex", alignItems: "center", gap: 24,
        padding: "12px 20px",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--border)",
        borderRadius: 16, flexWrap: "wrap",
        backdropFilter: "blur(12px)",
      }}
    >
      {/* Live dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className={running ? "pulse" : ""} style={{
          width: 7, height: 7, borderRadius: "50%", display: "inline-block",
          background: running ? "var(--green)" : "var(--muted)",
          boxShadow: running ? "0 0 10px var(--green-glow),0 0 20px var(--green-glow)" : undefined,
        }} />
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.12em",
          textTransform: "uppercase", color: running ? "var(--green)" : "var(--muted)" }}>
          {running ? "Live" : "Offline"}
        </span>
      </div>

      <div style={{ width: 1, height: 16, background: "var(--border)" }} />

      <Chip label="Venue"    value={data?.venue ?? "—"} />
      <Chip label="AI"       value={data?.provider ?? "—"} />
      <Chip label="Model"    value={data?.model?.replace("llama-","").replace("-versatile","").replace("-instruct","") ?? "—"} />
      <Chip label="Watching" value={data?.assets?.join(", ") ?? "—"} />
      <Chip label="Ticks"    value={data?.tick_count?.toString() ?? "0"} />
      {data?.uptime_seconds != null && (
        <Chip label="Uptime" value={fmtUptime(data.uptime_seconds)} />
      )}

      {/* Economic calendar countdown — fetches from Python /api/calendar/next */}
      <CalendarChip />
    </motion.div>
  );
}
