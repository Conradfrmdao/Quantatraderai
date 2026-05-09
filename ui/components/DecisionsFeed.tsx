"use client";
import { motion, AnimatePresence } from "framer-motion";

/* ── Types ─────────────────────────────────────────────────────────── */
interface CouncilOpinion {
  provider:   string;
  action:     string;
  confidence: number;  // 0–1
  rationale:  string;
}

interface TradeDecision {
  asset:         string;
  action:        string;
  rationale?:    string;
  allocation_usd?: number;
  tp_price?:     number;
  sl_price?:     number;
  confidence?:   number;
  deadlock?:     boolean;
  correlation_warning?: string;
  council?:      CouncilOpinion[];
}

interface Decision {
  ts?:             string;
  trade_decisions?: TradeDecision[];
  council?:        { asset: string; opinions: CouncilOpinion[]; vote: string; confidence: number; deadlock: boolean }[];
}

/* ── Colour maps ───────────────────────────────────────────────────── */
const ACTION_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  buy:  { bg: "rgba(34,197,94,0.08)",   color: "var(--green)", border: "rgba(34,197,94,0.2)"   },
  sell: { bg: "rgba(239,68,68,0.08)",   color: "var(--red)",   border: "rgba(239,68,68,0.2)"   },
  hold: { bg: "rgba(134,143,151,0.08)", color: "var(--muted)", border: "rgba(134,143,151,0.2)" },
};

const PROVIDER_COLOR: Record<string, string> = {
  groq:      "#F55036",
  anthropic: "#D97706",
  gemini:    "#4F8EF7",
  openrouter:"#9B6BF5",
  ollama:    "#22C55E",
};

/* ── Sub-components ────────────────────────────────────────────────── */
function Tag({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span style={{ fontSize: 11, color, display: "flex", gap: 4 }}>
      <span style={{ opacity: 0.5 }}>{label}</span>{value}
    </span>
  );
}

function ConfidenceBar({ value, color = "var(--green)" }: { value: number; color?: string }) {
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          style={{ height: "100%", background: color, borderRadius: 2 }}
        />
      </div>
      <span style={{ fontSize: 10, color: "var(--muted)", minWidth: 26, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {pct}%
      </span>
    </div>
  );
}

function CouncilRow({ opinion }: { opinion: CouncilOpinion }) {
  const style  = ACTION_STYLE[opinion.action?.toLowerCase()] ?? ACTION_STYLE.hold;
  const pColor = PROVIDER_COLOR[opinion.provider?.toLowerCase()] ?? "rgba(255,255,255,0.5)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: pColor, flexShrink: 0, display: "inline-block" }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: pColor, textTransform: "capitalize", minWidth: 64 }}>
          {opinion.provider}
        </span>
        <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 6, background: style.bg, color: style.color, border: `1px solid ${style.border}`, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {opinion.action}
        </span>
      </div>
      <ConfidenceBar value={opinion.confidence ?? 0.5} color={pColor} />
      {opinion.rationale && (
        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", lineHeight: 1.4, marginTop: 2,
          overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical" }}>
          {opinion.rationale}
        </p>
      )}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────────────── */
export function DecisionsFeed({ decisions }: { decisions: Decision[] }) {
  const flat = decisions
    .flatMap((d) =>
      (d.trade_decisions ?? []).map((td) => {
        // Merge council opinions from the parent entry if not on the trade decision itself
        const councilEntry = d.council?.find(c => c.asset?.toUpperCase() === td.asset?.toUpperCase());
        return {
          ts:      d.ts,
          ...td,
          council: td.council ?? councilEntry?.opinions,
          deadlock: td.deadlock ?? councilEntry?.deadlock,
          confidence: td.confidence ?? councilEntry?.confidence,
        };
      })
    )
    .reverse()
    .slice(0, 12);

  if (!flat.length) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        style={{ textAlign: "center", padding: "48px 20px", color: "var(--muted)", fontSize: 13 }}>
        <p>No decisions yet</p>
        <p style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>The AI decision log will populate after the first tick</p>
      </motion.div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <AnimatePresence>
        {flat.map((d, i) => {
          const action      = (d.action ?? "hold").toLowerCase();
          const style       = ACTION_STYLE[action] ?? ACTION_STYLE.hold;
          const hasCouncil  = d.council && d.council.length > 0;
          const isDeadlock  = d.deadlock === true;
          const confidence  = d.confidence ?? null;

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
                background: isDeadlock
                  ? "rgba(251,191,36,0.04)"
                  : "rgba(255,255,255,0.025)",
                border: `1px solid ${isDeadlock ? "rgba(251,191,36,0.2)" : "var(--border)"}`,
              }}
            >
              {/* Header row */}
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                {/* Action badge */}
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "3px 9px", borderRadius: 8,
                  background: style.bg, color: style.color, border: `1px solid ${style.border}`,
                  textTransform: "uppercase", letterSpacing: "0.1em", flexShrink: 0, marginTop: 2,
                }}>
                  {action}
                </span>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong style={{ fontSize: 13, color: "var(--text)" }}>{d.asset}</strong>

                      {/* Deadlock badge */}
                      {isDeadlock && (
                        <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                          background: "rgba(251,191,36,0.12)", color: "#FBBF24",
                          border: "1px solid rgba(251,191,36,0.25)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                          deadlock
                        </span>
                      )}

                      {/* Correlation warning */}
                      {d.correlation_warning && (
                        <span title={d.correlation_warning} style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                          background: "rgba(239,68,68,0.1)", color: "var(--red)",
                          border: "1px solid rgba(239,68,68,0.2)", textTransform: "uppercase", letterSpacing: "0.08em", cursor: "help" }}>
                          corr ⚠
                        </span>
                      )}
                    </div>

                    <span style={{ fontSize: 10, color: "var(--muted)" }}>
                      {d.ts ? new Date(d.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                  </div>

                  {/* Overall confidence bar (shown when council ran) */}
                  {confidence !== null && hasCouncil && (
                    <div style={{ marginBottom: 6 }}>
                      <ConfidenceBar
                        value={confidence}
                        color={action === "buy" ? "var(--green)" : action === "sell" ? "var(--red)" : "rgba(255,255,255,0.3)"}
                      />
                    </div>
                  )}

                  {/* Rationale */}
                  {d.rationale && (
                    <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55,
                      overflow: "hidden", display: "-webkit-box",
                      WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                      {d.rationale}
                    </p>
                  )}

                  {/* TP / SL / Size tags */}
                  {(d.tp_price || d.sl_price || d.allocation_usd) && (
                    <div style={{ display: "flex", gap: 10, marginTop: 7, flexWrap: "wrap" }}>
                      {d.tp_price     && <Tag label="TP"   value={`$${d.tp_price.toLocaleString()}`}    color="var(--green)" />}
                      {d.sl_price     && <Tag label="SL"   value={`$${d.sl_price.toLocaleString()}`}    color="var(--red)"   />}
                      {d.allocation_usd != null && d.allocation_usd > 0 &&
                        <Tag label="Size" value={`$${d.allocation_usd.toLocaleString()}`} color="var(--muted)" />}
                    </div>
                  )}
                </div>
              </div>

              {/* Council votes section */}
              {hasCouncil && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  transition={{ duration: 0.3, delay: 0.1 }}
                  style={{ marginTop: 12, paddingTop: 10,
                    borderTop: "1px solid rgba(255,255,255,0.05)" }}
                >
                  <p style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase",
                    letterSpacing: "0.1em", color: "rgba(255,255,255,0.25)", marginBottom: 6 }}>
                    AI Council · {(d.council ?? []).length} votes
                  </p>
                  {(d.council ?? []).map((op) => (
                    <CouncilRow key={op.provider} opinion={op} />
                  ))}
                </motion.div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
