"use client";
import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown, Zap, Shield, AlertTriangle, Info, ChevronDown, ChevronUp } from "lucide-react";

interface TimelineEvent {
  ts:         string;
  kind:       "signal" | "decision" | "executed" | "blocked" | "info";
  symbol:     string;
  detail:     string;
  confidence: number | null;
  action:     string | null;
}

const KIND_STYLE: Record<string, { color: string; bg: string; Icon: React.ElementType }> = {
  signal:   { color: "#818cf8", bg: "rgba(129,140,248,0.1)", Icon: Zap },
  decision: { color: "#fbbf24", bg: "rgba(251,191,36,0.1)",  Icon: TrendingUp },
  executed: { color: "#4ade80", bg: "rgba(74,222,128,0.1)",  Icon: TrendingUp },
  blocked:  { color: "#f87171", bg: "rgba(248,113,113,0.1)", Icon: Shield },
  info:     { color: "rgba(255,255,255,0.35)", bg: "rgba(255,255,255,0.04)", Icon: Info },
};

function fmt(ts: string) {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return ts; }
}

export function DecisionTimeline({
  userId,
  maxVisible = 8,
}: {
  userId?: string | null;
  maxVisible?: number;
}) {
  const [events, setEvents]     = useState<TimelineEvent[]>([]);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    try {
      const res  = await fetch(`/api/agent/timeline?limit=50`, { credentials: "same-origin" });
      const data = await res.json().catch(() => ({}));
      setEvents((data.timeline ?? []).reverse());
    } catch { /* backend offline */ }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 4_000);
    return () => clearInterval(id);
  }, [load]);

  const visible = expanded ? events : events.slice(0, maxVisible);

  return (
    <div style={{
      background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 14, padding: "14px 16px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)",
          textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Decision Timeline
        </span>
        {events.length > maxVisible && (
          <button onClick={() => setExpanded(e => !e)}
            style={{ background: "none", border: "none", cursor: "pointer",
              color: "rgba(255,255,255,0.3)", display: "flex", alignItems: "center", gap: 4, fontSize: 10 }}>
            {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            {expanded ? "Less" : `+${events.length - maxVisible} more`}
          </button>
        )}
      </div>

      {events.length === 0 && (
        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", textAlign: "center", padding: "12px 0" }}>
          No events yet — start the agent to see the decision timeline
        </p>
      )}

      <AnimatePresence initial={false}>
        {visible.map((evt, i) => {
          const style = KIND_STYLE[evt.kind] ?? KIND_STYLE.info;
          const Icon  = style.Icon;
          return (
            <motion.div
              key={`${evt.ts}-${i}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18, delay: i * 0.02 }}
              style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "7px 0",
                borderBottom: i < visible.length - 1
                  ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}
            >
              {/* Icon */}
              <div style={{
                width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                background: style.bg, display: "flex", alignItems: "center", justifyContent: "center",
                marginTop: 1,
              }}>
                <Icon size={10} style={{ color: style.color }} />
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  {evt.symbol && (
                    <span style={{ fontSize: 10, fontWeight: 700, color: style.color,
                      background: `${style.bg}`, border: `1px solid ${style.color}25`,
                      padding: "1px 5px", borderRadius: 4 }}>
                      {evt.symbol}
                    </span>
                  )}
                  {evt.confidence !== null && evt.confidence !== undefined && (
                    <span style={{ fontSize: 9, color: "rgba(255,255,255,0.3)" }}>
                      {Math.round(evt.confidence * 100)}% conf
                    </span>
                  )}
                </div>
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", lineHeight: 1.4,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {evt.detail}
                </p>
              </div>

              {/* Time */}
              <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)",
                flexShrink: 0, fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
                {fmt(evt.ts)}
              </span>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
