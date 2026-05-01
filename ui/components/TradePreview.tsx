"use client";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown, Target, Shield, AlertTriangle, ChevronRight } from "lucide-react";

export interface TradePreviewData {
  symbol:         string;
  action:         "buy" | "sell";
  size_usd:       number;
  current_price:  number;
  tp_price:       number | null;
  sl_price:       number | null;
  confidence:     number;       // 0-1
  confidence_label: "LOW" | "MEDIUM" | "HIGH";
  rationale:      string;
  estimated_qty:  number;
  estimated_fee:  number;
  venue:          string;
  is_paper:       boolean;
}

interface Props {
  preview:    TradePreviewData | null;
  onConfirm:  () => void;
  onCancel:   () => void;
}

const CONF_COLOR: Record<string, string> = {
  HIGH:   "#4ade80",
  MEDIUM: "#fbbf24",
  LOW:    "#f87171",
};

function Row({ label, value, color = "rgba(255,255,255,0.6)" }:
  { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between",
      padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 }}>
      <span style={{ color: "rgba(255,255,255,0.35)" }}>{label}</span>
      <span style={{ fontWeight: 600, color, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}

export function TradePreview({ preview, onConfirm, onCancel }: Props) {
  if (!preview) return null;

  const confColor = CONF_COLOR[preview.confidence_label] ?? "#888";
  const isBuy     = preview.action === "buy";

  const tpPct = preview.tp_price
    ? Math.abs((preview.tp_price - preview.current_price) / preview.current_price * 100)
    : null;
  const slPct = preview.sl_price
    ? Math.abs((preview.sl_price - preview.current_price) / preview.current_price * 100)
    : null;
  const rr = (tpPct && slPct && slPct > 0) ? (tpPct / slPct).toFixed(2) : null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: "fixed", inset: 0, zIndex: 8000,
          background: "rgba(0,0,0,0.75)", backdropFilter: "blur(6px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }}
      >
        <motion.div
          initial={{ scale: 0.94, y: 16 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.94 }}
          transition={{ duration: 0.2 }}
          style={{
            background: "#0e0e0e", border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 18, padding: "22px 22px 18px", maxWidth: 400, width: "100%",
            boxShadow: "0 20px 50px rgba(0,0,0,0.6)",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <div style={{
              width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
              background: isBuy ? "rgba(74,222,128,0.12)" : "rgba(239,68,68,0.12)",
              border: `1px solid ${isBuy ? "rgba(74,222,128,0.3)" : "rgba(239,68,68,0.3)"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {isBuy
                ? <TrendingUp size={14} color="#4ade80" />
                : <TrendingDown size={14} color="#ef4444" />}
            </div>
            <div>
              <p style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>
                Simulate: {preview.action.toUpperCase()} {preview.symbol}
              </p>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginTop: 1 }}>
                {preview.venue} · {preview.is_paper ? "PAPER" : "LIVE"}
              </p>
            </div>
            {preview.is_paper && (
              <div style={{ marginLeft: "auto", background: "rgba(74,222,128,0.1)",
                border: "1px solid rgba(74,222,128,0.2)", borderRadius: 6,
                padding: "2px 8px", fontSize: 9, fontWeight: 700, color: "#4ade80",
                letterSpacing: "0.07em" }}>
                PAPER
              </div>
            )}
          </div>

          {/* Rationale */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 8, padding: "10px 12px", marginBottom: 14 }}>
            <p style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)",
              textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
              AI Rationale
            </p>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.55 }}>
              {preview.rationale.slice(0, 200)}{preview.rationale.length > 200 ? "…" : ""}
            </p>
          </div>

          {/* Confidence bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <div style={{ flex: 1, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)" }}>
              <div style={{ width: `${preview.confidence * 100}%`, height: "100%",
                background: confColor, borderRadius: 2, transition: "width 0.5s ease" }} />
            </div>
            <span style={{ fontSize: 11, fontWeight: 700, color: confColor,
              background: `${confColor}18`, border: `1px solid ${confColor}30`,
              padding: "2px 8px", borderRadius: 6, whiteSpace: "nowrap" }}>
              {preview.confidence_label}
            </span>
          </div>

          {/* Trade details */}
          <div style={{ marginBottom: 14 }}>
            <Row label="Size" value={`$${preview.size_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
            <Row label="Est. Quantity" value={`${preview.estimated_qty.toFixed(6)} units`} />
            <Row label="Entry Price" value={`$${preview.current_price.toLocaleString()}`} />
            {preview.tp_price && (
              <Row label={`Take Profit (+${tpPct?.toFixed(2)}%)`}
                value={`$${preview.tp_price.toLocaleString()}`} color="#4ade80" />
            )}
            {preview.sl_price && (
              <Row label={`Stop Loss (−${slPct?.toFixed(2)}%)`}
                value={`$${preview.sl_price.toLocaleString()}`} color="#ef4444" />
            )}
            {rr && <Row label="Risk / Reward" value={`1 : ${rr}`} color="#818cf8" />}
            <Row label="Est. Fee" value={`~$${preview.estimated_fee.toFixed(3)}`} />
          </div>

          {/* Risk warning if low confidence */}
          {preview.confidence_label === "LOW" && (
            <div style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.18)",
              borderRadius: 8, padding: "8px 10px", marginBottom: 12,
              display: "flex", alignItems: "flex-start", gap: 6 }}>
              <AlertTriangle size={11} style={{ color: "#ef4444", flexShrink: 0, marginTop: 1 }} />
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", lineHeight: 1.5 }}>
                Low confidence signal. Consider skipping or reducing position size.
              </p>
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={onCancel}
              style={{ flex: 1, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 10, padding: "10px 0", color: "rgba(255,255,255,0.5)",
                fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              Cancel
            </button>
            <button onClick={onConfirm}
              style={{ flex: 2, background: isBuy ? "rgba(74,222,128,0.15)" : "rgba(239,68,68,0.15)",
                border: `1px solid ${isBuy ? "rgba(74,222,128,0.3)" : "rgba(239,68,68,0.3)"}`,
                borderRadius: 10, padding: "10px 0",
                color: isBuy ? "#4ade80" : "#ef4444",
                fontSize: 13, fontWeight: 700, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              {preview.action.toUpperCase()} {preview.symbol}
              <ChevronRight size={14} />
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
