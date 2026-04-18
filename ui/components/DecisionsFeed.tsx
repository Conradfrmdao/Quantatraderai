"use client";
import { motion, AnimatePresence } from "framer-motion";

interface Decision {
  ts?: string;
  trade_decisions?: Array<{
    asset: string;
    action: string;
    rationale?: string;
    allocation_usd?: number;
    tp_price?: number;
    sl_price?: number;
  }>;
}

const ACTION_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  buy:  { bg: "rgba(34,197,94,0.08)",  color: "var(--green)", border: "rgba(34,197,94,0.2)"  },
  sell: { bg: "rgba(239,68,68,0.08)",  color: "var(--red)",   border: "rgba(239,68,68,0.2)"  },
  hold: { bg: "rgba(134,143,151,0.08)", color: "var(--muted)", border: "rgba(134,143,151,0.2)" },
};

export function DecisionsFeed({ decisions }: { decisions: Decision[] }) {
  const flat = decisions
    .flatMap((d) =>
      (d.trade_decisions ?? []).map((td) => ({ ts: d.ts, ...td }))
    )
    .reverse()
    .slice(0, 12);

  if (!flat.length) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          textAlign: "center",
          padding: "48px 20px",
          color: "var(--muted)",
          fontSize: 13,
        }}
      >
        <p>No decisions yet</p>
        <p style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>
          The AI decision log will populate after the first tick
        </p>
      </motion.div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <AnimatePresence>
        {flat.map((d, i) => {
          const action = (d.action ?? "hold").toLowerCase();
          const style = ACTION_STYLE[action] ?? ACTION_STYLE.hold;
          return (
            <motion.div
              key={`${d.asset}-${d.ts}-${i}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ delay: i * 0.04, duration: 0.35 }}
              style={{
                padding: "12px 14px",
                borderRadius: 16,
                background: "rgba(255,255,255,0.025)",
                border: "1px solid var(--border)",
                display: "flex",
                gap: 12,
                alignItems: "flex-start",
              }}
            >
              {/* Action badge */}
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  padding: "3px 9px",
                  borderRadius: 8,
                  background: style.bg,
                  color: style.color,
                  border: `1px solid ${style.border}`,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  flexShrink: 0,
                  marginTop: 2,
                }}
              >
                {action}
              </span>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <strong style={{ fontSize: 13, color: "var(--text)" }}>{d.asset}</strong>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>
                    {d.ts ? new Date(d.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                  </span>
                </div>
                {d.rationale && (
                  <p
                    style={{
                      fontSize: 12,
                      color: "var(--muted)",
                      lineHeight: 1.55,
                      overflow: "hidden",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                    }}
                  >
                    {d.rationale}
                  </p>
                )}
                {(d.tp_price || d.sl_price || d.allocation_usd) && (
                  <div style={{ display: "flex", gap: 10, marginTop: 7, flexWrap: "wrap" }}>
                    {d.tp_price && (
                      <Tag label="TP" value={`$${d.tp_price.toLocaleString()}`} color="var(--green)" />
                    )}
                    {d.sl_price && (
                      <Tag label="SL" value={`$${d.sl_price.toLocaleString()}`} color="var(--red)" />
                    )}
                    {d.allocation_usd != null && d.allocation_usd > 0 && (
                      <Tag label="Size" value={`$${d.allocation_usd.toLocaleString()}`} color="var(--muted)" />
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

function Tag({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span style={{ fontSize: 11, color, display: "flex", gap: 4 }}>
      <span style={{ opacity: 0.5 }}>{label}</span>
      {value}
    </span>
  );
}
