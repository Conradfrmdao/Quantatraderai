"use client";
/**
 * ExecutionConfidence — shows before a trade is placed.
 * Risk level (LOW/MEDIUM/HIGH), confidence bar, expected outcome range.
 * Reduces user fear by explaining what the AI is about to do.
 */
import { motion } from "framer-motion";
import { Shield, TrendingUp, AlertTriangle } from "lucide-react";

export interface ConfidenceProps {
  symbol:     string;
  action:     string;
  confidence: number;     // 0-1
  label:      "LOW" | "MEDIUM" | "HIGH";
  riskLevel:  "LOW" | "MEDIUM" | "HIGH";
  allocationUsd: number;
  explanation:   string;
}

const COLORS = { HIGH: "#4ade80", MEDIUM: "#fbbf24", LOW: "#f87171" };
const ICONS  = {
  HIGH:   Shield,
  MEDIUM: AlertTriangle,
  LOW:    AlertTriangle,
};

export function ExecutionConfidence({
  symbol, action, confidence, label, riskLevel, allocationUsd, explanation,
}: ConfidenceProps) {
  const confColor = COLORS[label];
  const riskColor = COLORS[riskLevel];
  const RiskIcon  = ICONS[riskLevel];
  const isBuy = action === "buy";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        background:   "rgba(255,255,255,0.03)",
        border:       "1px solid rgba(255,255,255,0.07)",
        borderRadius: 14,
        padding:      "16px 18px",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <TrendingUp size={14} color={isBuy ? "#4ade80" : "#f87171"} />
          <span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
            {action.toUpperCase()} {symbol}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5,
          padding: "3px 9px", borderRadius: 6,
          background: `${riskColor}18`, border: `1px solid ${riskColor}30` }}>
          <RiskIcon size={10} color={riskColor} />
          <span style={{ fontSize: 10, fontWeight: 700, color: riskColor }}>
            {riskLevel} RISK
          </span>
        </div>
      </div>

      {/* Confidence bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between",
          fontSize: 10, color: "rgba(255,255,255,0.4)", marginBottom: 5 }}>
          <span>AI Confidence</span>
          <span style={{ color: confColor, fontWeight: 600 }}>
            {(confidence * 100).toFixed(0)}% — {label}
          </span>
        </div>
        <div style={{ height: 5, borderRadius: 3, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${confidence * 100}%` }}
            transition={{ duration: 0.5 }}
            style={{ height: "100%", background: confColor, borderRadius: 3 }}
          />
        </div>
      </div>

      {/* AI explanation */}
      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginBottom: 12 }}>
        {explanation}
      </p>

      {/* Allocation */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
        <span style={{ color: "rgba(255,255,255,0.3)" }}>Allocation</span>
        <span style={{ color: "#fff", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
          ${allocationUsd.toFixed(2)}
        </span>
      </div>
    </motion.div>
  );
}
