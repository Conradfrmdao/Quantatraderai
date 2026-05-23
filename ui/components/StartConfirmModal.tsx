"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, AlertTriangle, TrendingUp, Target, Brain,
  ChevronRight, X, Check, Play, Zap, RefreshCw,
} from "lucide-react";
import { getStartConfirmActionState } from "@/lib/start-confirm";

export interface StartConfig {
  strategyType:     string;
  strategyName:     string;
  strategyTagline:  string;
  isPaper:          boolean;
  venueName:        string;
  market:           string;
  paperCapital:     number;
  minConfidencePct: number;
  maxDailyLossPct:  number;
  maxTradesPerDay:  number;
  lossCooldownCount: number;
  symbols:          string[];
}

export interface StartReadinessCheck {
  key: string;
  label: string;
  status: string;
  required: boolean;
  summary: string;
  detail?: string;
}

export interface StartReadiness {
  state: string;
  can_start: boolean;
  summary: string;
  warnings?: string[];
  market?: {
    sections?: {
      asset?: string;
      session?: string;
      candle_source?: string;
      data_state?: string;
      warnings?: string[];
    }[];
  };
  checks?: StartReadinessCheck[];
  warm_snapshot?: {
    used?: boolean;
    age_s?: number | null;
  } | null;
}

interface Props {
  config:    StartConfig;
  onConfirm: () => void;
  onCancel:  () => void;
  readiness?: StartReadiness | null;
  readinessLoading?: boolean;
}

const PERSONA_COLOR: Record<string, string> = {
  MOMENTUM_HUNTER: "#4ade80",
  SCALPER_AI:      "#fbbf24",
  SWING_MASTER:    "#818cf8",
  NEWS_REACTOR:    "#f472b6",
};

function Row({ icon: Icon, label, value, color = "#fff", sub }:
  { icon: React.ElementType; label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10,
      padding: "9px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
      <div style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: "rgba(255,255,255,0.04)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Icon size={12} style={{ color: "rgba(255,255,255,0.4)" }} />
      </div>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>{label}</p>
        {sub && <p style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", marginTop: 1 }}>{sub}</p>}
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color }}>{value}</span>
    </div>
  );
}

function readinessTone(state: string | undefined) {
  if (state === "ready") return { bg: "rgba(74,222,128,0.08)", border: "rgba(74,222,128,0.24)", text: "#86efac" };
  if (state === "degraded") return { bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.24)", text: "#fcd34d" };
  if (state === "blocked") return { bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.24)", text: "#fca5a5" };
  return { bg: "rgba(255,255,255,0.04)", border: "rgba(255,255,255,0.1)", text: "rgba(255,255,255,0.7)" };
}

export function StartConfirmModal({ config, onConfirm, onCancel, readiness, readinessLoading = false }: Props) {
  const [acked, setAcked] = useState(false);
  const [pulse, setPulse] = useState(false);

  const personaColor = PERSONA_COLOR[config.strategyType] ?? "#4ade80";
  const isLive = !config.isPaper;
  const readinessBlocked = readinessLoading || !readiness || readiness.can_start === false;
  const actionState = getStartConfirmActionState(isLive, acked && !readinessBlocked);
  const ActionIcon = isLive ? Zap : Play;
  const ReadinessIcon = readinessLoading ? RefreshCw : readiness?.can_start === false ? AlertTriangle : ActionIcon;
  const readinessStyle = readinessTone(readiness?.state);

  function tryConfirm() {
    if (readinessLoading || !readiness || readiness.can_start === false) {
      return;
    }
    if (!acked) {
      // Shake the checkbox to draw attention
      setPulse(true);
      setTimeout(() => setPulse(false), 600);
      return;
    }
    onConfirm();
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: "fixed", inset: 0, zIndex: 9000,
          background: "rgba(0,0,0,0.85)", backdropFilter: "blur(10px)",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: 20,
        }}
        onClick={onCancel}
      >
        <motion.div
          initial={{ scale: 0.93, y: 18, opacity: 0 }}
          animate={{ scale: 1,    y: 0,  opacity: 1 }}
          exit={{   scale: 0.93, opacity: 0 }}
          transition={{ duration: 0.22 }}
          onClick={e => e.stopPropagation()}
          style={{
            background:   "#0c0c0c",
            border:       `1px solid ${isLive ? "rgba(239,68,68,0.3)" : "rgba(255,255,255,0.1)"}`,
            borderRadius: 20,
            padding:      "24px 24px 20px",
            width:        "100%",
            maxWidth:     440,
            maxHeight:    "calc(100dvh - 32px)",
            overflowY:    "auto",
            boxShadow:    "0 24px 60px rgba(0,0,0,0.7)",
          }}
        >
          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%", flexShrink: 0,
                background: isLive ? "rgba(239,68,68,0.1)" : "rgba(74,222,128,0.08)",
                border: `1px solid ${isLive ? "rgba(239,68,68,0.3)" : "rgba(74,222,128,0.2)"}`,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {isLive
                  ? <AlertTriangle size={18} style={{ color: "#ef4444" }} />
                  : <Shield       size={18} style={{ color: "#4ade80" }} />}
              </div>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>
                  {isLive ? "Start Live Trading" : "Start Paper Trading"}
                </h2>
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", marginTop: 2 }}>
                  {isLive
                    ? "Real money will be used — review your settings below"
                    : "Simulated trades only — no real money at risk"}
                </p>
              </div>
            </div>
            <button onClick={onCancel}
              style={{ background: "none", border: "none", cursor: "pointer",
                color: "rgba(255,255,255,0.25)", padding: 4, flexShrink: 0 }}>
              <X size={14} />
            </button>
          </div>

          {/* ── Live trading banner ─────────────────────────────────────── */}
          {isLive && (
            <motion.div
              animate={{ opacity: [1, 0.6, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              style={{ marginBottom: 16, padding: "10px 14px",
                background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: 10, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%",
                background: "#ef4444", flexShrink: 0, display: "inline-block" }} />
              <p style={{ fontSize: 12, color: "#fca5a5", fontWeight: 600 }}>
                LIVE TRADING — Real money at risk. Cannot be undone once a trade executes.
              </p>
            </motion.div>
          )}

          {/* ── Config summary ──────────────────────────────────────────── */}
          <div style={{ marginBottom: 18 }}>
            {/* Persona */}
            <div style={{ padding: "10px 12px", marginBottom: 10,
              background: `${personaColor}0a`, border: `1px solid ${personaColor}20`,
              borderRadius: 10, display: "flex", alignItems: "center", gap: 10 }}>
              <Brain size={14} style={{ color: personaColor, flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 13, fontWeight: 700, color: personaColor }}>
                  {config.strategyName}
                </p>
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 1 }}>
                  {config.strategyTagline}
                </p>
              </div>
            </div>

            {/* Settings rows */}
            <Row icon={Shield}
              label="Mode"
              value={config.isPaper
                ? `Paper — $${config.paperCapital.toLocaleString()} simulated`
                : "Live trading — real money"}
              color={config.isPaper ? "#4ade80" : "#ef4444"}
              sub={config.isPaper ? "No real money at risk" : undefined} />

            <Row icon={TrendingUp}
              label="Venue"
              value={config.venueName}
              sub={`${config.market.toUpperCase()} · ${config.symbols.join(", ")}`} />

            <Row icon={Target}
              label="Confidence gate"
              value={config.minConfidencePct > 0 ? `≥ ${config.minConfidencePct}%` : "Off — all trades"}
              color={config.minConfidencePct > 0 ? "#818cf8" : "rgba(255,255,255,0.35)"}
              sub={config.minConfidencePct > 0 ? "Skips low-confidence signals" : "Consider enabling for better results"} />

            <Row icon={AlertTriangle}
              label="Max daily loss"
              value={config.maxDailyLossPct > 0 ? `${config.maxDailyLossPct}% of account` : "Off — no limit"}
              color={config.maxDailyLossPct > 0 ? "#fbbf24" : "rgba(255,255,255,0.35)"}
              sub={config.maxDailyLossPct > 0 ? "Agent auto-stops at this loss" : undefined} />

            {config.maxTradesPerDay > 0 && (
              <Row icon={ChevronRight}
                label="Max trades / day"
                value={`${config.maxTradesPerDay} trades`}
                color="#fbbf24" />
            )}

            {config.lossCooldownCount > 0 && (
              <Row icon={ChevronRight}
                label="Loss cooldown"
                value={`After ${config.lossCooldownCount} consecutive losses`}
              color="#fbbf24" />
            )}
          </div>

          {/* ── Startup readiness ───────────────────────────────────────── */}
          <div style={{
            marginBottom: 18,
            padding: "12px 12px 10px",
            borderRadius: 12,
            background: readinessStyle.bg,
            border: `1px solid ${readinessStyle.border}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
              <div>
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.38)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>
                  Startup Readiness
                </p>
                <p style={{ fontSize: 13, fontWeight: 700, color: readinessStyle.text, marginTop: 3 }}>
                  {readinessLoading ? "Checking live venue, market data, and AI health…" : readiness?.summary ?? "Readiness unavailable"}
                </p>
              </div>
              <span style={{
                padding: "5px 8px",
                borderRadius: 999,
                fontSize: 10,
                fontWeight: 800,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: readinessStyle.text,
                border: `1px solid ${readinessStyle.border}`,
                background: "rgba(0,0,0,0.12)",
                flexShrink: 0,
              }}>
                {readinessLoading ? "Checking" : readiness?.state ?? "Unknown"}
              </span>
            </div>

            {!readinessLoading && readiness?.warm_snapshot?.used && (
              <p style={{ fontSize: 11, color: "rgba(255,255,255,0.48)", marginBottom: 8 }}>
                Warm market snapshot restored{typeof readiness.warm_snapshot.age_s === "number" ? ` (${readiness.warm_snapshot.age_s}s old)` : ""}.
              </p>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(readiness?.checks ?? []).map((check) => {
                const tone = readinessTone(check.status);
                return (
                  <div key={check.key} style={{
                    padding: "8px 9px",
                    borderRadius: 10,
                    border: `1px solid ${tone.border}`,
                    background: "rgba(0,0,0,0.12)",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#fff" }}>{check.label}</span>
                      <span style={{
                        fontSize: 9,
                        fontWeight: 800,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        color: tone.text,
                      }}>
                        {check.required ? "Required" : "Optional"} · {check.status}
                      </span>
                    </div>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.62)", marginTop: 4 }}>{check.summary}</p>
                    {check.detail && (
                      <p style={{ fontSize: 10, color: "rgba(255,255,255,0.36)", marginTop: 4 }}>{check.detail}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Acknowledgment checkbox ─────────────────────────────────── */}
          <motion.label
            animate={pulse ? { x: [-4, 4, -4, 4, 0] } : {}}
            transition={{ duration: 0.3 }}
            style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer",
              marginBottom: 18 }}
            onClick={() => setAcked(a => !a)}
          >
            <div style={{
              width: 20, height: 20, borderRadius: 6, flexShrink: 0, marginTop: 1,
              background: acked ? "#4ade80" : "rgba(255,255,255,0.06)",
              border: `1.5px solid ${acked ? "#4ade80" : pulse ? "#fbbf24" : "rgba(255,255,255,0.2)"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all 0.15s",
            }}>
              {acked && <Check size={11} style={{ color: "#000" }} />}
            </div>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", lineHeight: 1.6 }}>
              {isLive
                ? "I understand that automated trading involves risk, that I may lose money, and that I am solely responsible for all trading decisions made by QuantatraderAI on my behalf."
                : "I understand this agent will place simulated trades and I am reviewing the settings above."}
            </p>
          </motion.label>

          {/* Checkbox nudge if not checked */}
          <AnimatePresence>
            {pulse && !acked && (
              <motion.p
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                style={{ fontSize: 11, color: "#fbbf24", marginBottom: 10, marginTop: -10 }}>
                ↑ Please check the box above to continue
              </motion.p>
            )}
          </AnimatePresence>

          {/* ── Action buttons ──────────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button onClick={onCancel}
              style={{ flex: "1 1 104px", minWidth: 96, padding: "11px 12px", borderRadius: 10, cursor: "pointer",
                background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                color: "rgba(255,255,255,0.5)", fontSize: 13, fontWeight: 500 }}>
              Cancel
            </button>
            <button onClick={tryConfirm}
              style={{
                flex: "2 1 210px",
                minWidth: 0,
                padding: "10px 12px",
                borderRadius: 14,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                background: actionState.background,
                border: actionState.border,
                boxShadow: actionState.boxShadow,
                color: actionState.textColor,
                fontSize: 13,
                fontWeight: 800,
                transition: "all 0.2s",
                opacity: readinessBlocked && !acked ? 0.9 : readinessBlocked ? 0.7 : 1,
              }}>
              <span style={{
                width: 30,
                height: 30,
                borderRadius: 10,
                background: acked ? "rgba(0,0,0,0.12)" : "rgba(255,255,255,0.04)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}>
                <ReadinessIcon size={15} fill={acked && !isLive && !readinessBlocked ? "#050505" : "none"} style={{ color: actionState.iconColor }} />
              </span>
              <span style={{ minWidth: 0, textAlign: "left", lineHeight: 1.15 }}>
                <span style={{ display: "block", whiteSpace: "normal" }}>
                  {readinessLoading ? "Checking Readiness" : readiness?.can_start === false ? "Resolve Blocked Checks" : actionState.label}
                </span>
                <span style={{
                  display: "block",
                  fontSize: 10,
                  fontWeight: 700,
                  marginTop: 2,
                  opacity: acked ? 0.65 : 0.75,
                  whiteSpace: "normal",
                }}>
                  {readinessLoading
                    ? "Fetching fresh venue, data, and AI health before enabling start"
                    : readiness?.can_start === false
                      ? readiness.summary
                      : actionState.subcopy}
                </span>
              </span>
            </button>
          </div>

          <p style={{ textAlign: "center", fontSize: 10, color: "rgba(255,255,255,0.18)",
            marginTop: 12 }}>
            You can stop the agent at any time from the dashboard
          </p>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
