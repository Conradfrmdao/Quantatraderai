"use client";
import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface StatusData {
  status?:            string;
  provider?:          string;
  model?:             string;
  venue?:             string;
  tick_count?:        number;
  uptime_seconds?:    number;
  assets?:            string[];
  timeframe?:         string;
  is_paper?:          boolean;
  last_tick_ago_s?:   number | null;
  next_tick_in_s?:    number | null;
  tick_interval_s?:   number;
  strategy_type?:     string | null;
  latest_log?:        { ts: string; msg: string } | null;
  daily_trade_count?: number;
}

function fmtUptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function fmtSecs(s: number): string {
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  if (s >= 60)   return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${s}s`;
}

function Chip({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ fontSize: 9, color: "var(--muted)", fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
      <span style={{ fontSize: 12, color: color ?? "rgba(255,255,255,0.8)", fontWeight: 600 }}>
        {value}
      </span>
    </div>
  );
}

// ── Countdown that ticks live ─────────────────────────────────────────────────
function NextTickCountdown({ nextTickInS, intervalS }: { nextTickInS: number; intervalS: number }) {
  const [remaining, setRemaining] = useState(nextTickInS);

  useEffect(() => {
    setRemaining(nextTickInS);
    const id = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, [nextTickInS]);

  const pct = intervalS > 0 ? ((intervalS - remaining) / intervalS) * 100 : 0;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 140 }}>
      <div style={{ flex: 1, height: 3, borderRadius: 2, background: "rgba(255,255,255,0.08)" }}>
        <motion.div
          animate={{ width: `${pct}%` }}
          transition={{ duration: 1, ease: "linear" }}
          style={{ height: "100%", background: remaining < 30 ? "#4ade80" : "rgba(255,255,255,0.3)", borderRadius: 2 }}
        />
      </div>
      <span style={{ fontSize: 11, fontVariantNumeric: "tabular-nums",
        color: remaining < 30 ? "#4ade80" : "rgba(255,255,255,0.5)", fontWeight: 600,
        minWidth: 42, textAlign: "right" }}>
        {remaining === 0 ? "now" : fmtSecs(remaining)}
      </span>
    </div>
  );
}

// ── Latest log strip ─────────────────────────────────────────────────────────
function LatestLogStrip({ msg }: { msg: string }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={msg}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
        style={{ fontSize: 11, color: "rgba(255,255,255,0.45)",
          maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {msg}
      </motion.div>
    </AnimatePresence>
  );
}

// ── FOREX session indicator ───────────────────────────────────────────────────
// Shows which trading sessions are currently open based on UTC time.
// Sessions: Sydney 22-07, Tokyo 00-09, London 07-16, New York 12-21 (all UTC)
const FX_SESSIONS = [
  { name: "Tokyo",  open: 0,  close: 9,  color: "#f59e0b" },
  { name: "London", open: 7,  close: 16, color: "#818cf8" },
  { name: "NY",     open: 12, close: 21, color: "#4ade80" },
  { name: "Sydney", open: 22, close: 31, color: "#38bdf8" }, // 22-07 UTC (31 = 07 next day)
] as const;

function isSessionOpen(openH: number, closeH: number, utcH: number): boolean {
  // Handle overnight sessions (closeH > 24 means it wraps to next day)
  if (closeH > 24) return utcH >= openH || utcH < (closeH - 24);
  return utcH >= openH && utcH < closeH;
}

function ForexSessionChip() {
  const [utcHour, setUtcHour] = useState(() => new Date().getUTCHours());
  useEffect(() => {
    const id = setInterval(() => setUtcHour(new Date().getUTCHours()), 60_000);
    return () => clearInterval(id);
  }, []);

  const open = FX_SESSIONS.filter(s => isSessionOpen(s.open, s.close, utcHour));
  const isOverlap = open.some(s => s.name === "London") && open.some(s => s.name === "NY");

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 9, color: "var(--muted)", fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "0.08em" }}>Sessions</span>
      {FX_SESSIONS.map(s => {
        const active = isSessionOpen(s.open, s.close, utcHour);
        return (
          <span key={s.name} style={{
            fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
            letterSpacing: "0.05em",
            background: active ? `${s.color}18` : "rgba(255,255,255,0.03)",
            border:     `1px solid ${active ? `${s.color}40` : "rgba(255,255,255,0.07)"}`,
            color:      active ? s.color : "rgba(255,255,255,0.2)",
            transition: "all 0.3s",
          }}>
            {s.name}
          </span>
        );
      })}
      {isOverlap && (
        <span style={{ fontSize: 9, color: "#4ade80", fontWeight: 700,
          background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.25)",
          borderRadius: 4, padding: "2px 6px", letterSpacing: "0.05em" }}>
          ⚡ Peak
        </span>
      )}
    </div>
  );
}

// ── Calendar chip ─────────────────────────────────────────────────────────────
function CalendarChip() {
  const [label, setLabel] = useState("");
  useEffect(() => {
    const load = () => fetch("/api/agent/calendar/next", { credentials: "same-origin" })
      .then(r => r.json())
      .then((d: { next_event?: string }) => setLabel(d.next_event ?? ""))
      .catch(() => {});
    load();
    const id = setInterval(load, 300_000);
    return () => clearInterval(id);
  }, []);
  if (!label) return null;
  return (
    <>
      <div style={{ width: 1, height: 16, background: "var(--border)" }} />
      <span style={{ fontSize: 11, color: "#FBBF24" }}>📅 {label}</span>
    </>
  );
}

// ── Main StatusBar ────────────────────────────────────────────────────────────
export function StatusBar({ data, loading = false }: { data: StatusData | null; loading?: boolean }) {
  const status    = loading ? "syncing" : data?.status ?? "idle";
  const running   = status === "running";
  const active    = status === "running" || status === "paused" || status === "stopping";
  const isForex   = data?.venue === "oanda" || data?.venue === "metatrader";

  const PERSONA_LABELS: Record<string, string> = {
    MOMENTUM_HUNTER: "Momentum", SCALPER_AI: "Scalper",
    SWING_MASTER: "Swing",      NEWS_REACTOR: "News",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* ── Top row: live indicator + key stats ────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        style={{ display: "flex", alignItems: "center", gap: 20, padding: "12px 18px",
          background: "rgba(255,255,255,0.03)", border: `1px solid ${running ? "rgba(74,222,128,0.2)" : "var(--border)"}`,
          borderRadius: 14, flexWrap: "wrap", backdropFilter: "blur(12px)" }}>

        {/* Pulsing live dot */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", display: "inline-block",
            background: running ? "#4ade80" : "var(--muted)",
            boxShadow: running ? "0 0 0 0 rgba(74,222,128,0.6)" : undefined,
            animation: running ? "pulse-ring 1.4s ease-out infinite" : undefined }} />
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em",
            textTransform: "uppercase", color: running ? "#4ade80" : "var(--muted)" }}>
            {loading ? "Syncing…" : running ? "Agent Active" : status === "paused" ? "Paused" : status === "stopping" ? "Stopping…" : "Offline"}
          </span>
          {data?.is_paper !== undefined && active && (
            <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
              background: data.is_paper ? "rgba(129,140,248,0.1)" : "rgba(239,68,68,0.12)",
              border: `1px solid ${data.is_paper ? "rgba(129,140,248,0.25)" : "rgba(239,68,68,0.3)"}`,
              color: data.is_paper ? "#818cf8" : "#ef4444",
              letterSpacing: "0.07em", textTransform: "uppercase" }}>
              {data.is_paper ? "PAPER" : "LIVE"}
            </span>
          )}
        </div>

        <div style={{ width: 1, height: 16, background: "var(--border)" }} />

        {active && <Chip label="Venue"    value={data?.venue ?? "—"} />}
        {active && <Chip label="Watching" value={data?.assets?.join(", ") ?? "—"} />}
        {active && data?.strategy_type && (
          <Chip label="Persona" value={PERSONA_LABELS[data.strategy_type] ?? data.strategy_type} color="#fbbf24" />
        )}
        {active && <Chip label="Ticks" value={data?.tick_count?.toString() ?? "0"} />}
        {!active && !loading && (
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.25)" }}>
            Start the agent to begin trading
          </span>
        )}
        {loading && (
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>
            Confirming your live agent state…
          </span>
        )}
        {data?.uptime_seconds != null && active && (
          <Chip label="Uptime" value={fmtUptime(data.uptime_seconds)} />
        )}
        {data?.daily_trade_count != null && active && (
          <Chip label="Trades today" value={String(data.daily_trade_count)} color="#4ade80" />
        )}

        <CalendarChip />

        {/* FOREX session indicator — only shown for OANDA/MetaTrader venues */}
        {isForex && (
          <>
            <div style={{ width: 1, height: 16, background: "var(--border)" }} />
            <ForexSessionChip />
          </>
        )}
      </motion.div>

      {/* ── Bottom row: next tick countdown + latest log (only when running) */}
      <AnimatePresence>
        {active && data && (
          <motion.div
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25 }}
            style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 18px",
              background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 12, flexWrap: "wrap" }}>

            {/* Next tick countdown */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 200 }}>
              <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", fontWeight: 600,
                textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0 }}>
                Next tick
              </span>
              {data.next_tick_in_s != null && data.tick_interval_s ? (
                <NextTickCountdown
                  nextTickInS={data.next_tick_in_s}
                  intervalS={data.tick_interval_s}
                />
              ) : (
                <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>calculating…</span>
              )}
            </div>

            {/* Last tick info */}
            {data.last_tick_ago_s != null && (
              <>
                <div style={{ width: 1, height: 14, background: "rgba(255,255,255,0.08)" }} />
                <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                  Last tick <strong style={{ color: "rgba(255,255,255,0.6)" }}>
                    {fmtSecs(data.last_tick_ago_s)} ago
                  </strong>
                </span>
              </>
            )}

            {/* Timeframe indicator */}
            {data.timeframe && (
              <>
                <div style={{ width: 1, height: 14, background: "rgba(255,255,255,0.08)" }} />
                <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>
                  Interval <strong style={{ color: "rgba(255,255,255,0.6)" }}>{data.timeframe}</strong>
                </span>
              </>
            )}

            {/* Latest log message */}
            {data.latest_log?.msg && (
              <>
                <div style={{ width: 1, height: 14, background: "rgba(255,255,255,0.08)", marginLeft: "auto" }} />
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <motion.span
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.8, repeat: Infinity }}
                    style={{ fontSize: 7, color: "#4ade80" }}>●</motion.span>
                  <LatestLogStrip msg={data.latest_log.msg} />
                </div>
              </>
            )}

            {/* If no ticks yet — explain what's happening */}
            {(data.tick_count ?? 0) === 0 && (
              <span style={{ fontSize: 11, color: "#fbbf24", marginLeft: "auto" }}>
                ⏳ Warming up — first tick incoming{data.timeframe ? ` in ~${data.timeframe}` : ""}
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
