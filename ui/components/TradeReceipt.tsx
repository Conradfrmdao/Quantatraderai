"use client";
/**
 * TradeReceipt — Stripe-style receipt panel shown after every AI trade.
 *
 * Displays:
 *  - Trade ID + timestamp
 *  - Venue + symbol + action
 *  - Confidence score (LOW/MEDIUM/HIGH with colour)
 *  - Risk decision ("Why was this allowed?")
 *  - Before / after balance
 *  - AI explanation: "Why this trade?"
 *  - Receipt hash (tamper-evident)
 */
import { motion, AnimatePresence } from "framer-motion";
import { Check, Shield, TrendingUp, TrendingDown, X, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

export interface TradeReceiptData {
  trade_id:       string;
  trace_id:       string;
  timestamp:      string;
  venue:          string;
  symbol:         string;
  action:         string;
  quantity:       number;
  price:          number;
  allocation_usd: number;
  tp_price:       number | null;
  sl_price:       number | null;
  before_balance: number;
  after_balance:  number;
  mode:           string;
  receipt_hash:   string;
  ai_explanation: string;
  confidence: {
    overall: number;
    label:   "LOW" | "MEDIUM" | "HIGH";
    rsi:     number;
    macd:    number;
    ema:     number;
  };
  risk: {
    passed:         boolean;
    capped:         boolean;
    original_alloc: number;
    final_alloc:    number;
    human_summary:  string;
  };
}

const CONF_COLOR: Record<string, string> = {
  HIGH:   "#4ade80",
  MEDIUM: "#fbbf24",
  LOW:    "#f87171",
};

function BalanceRow({ label, value, delta }: { label: string; value: number; delta?: number }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12 }}>
      <span style={{ color: "rgba(255,255,255,0.4)" }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {delta !== undefined && (
          <span style={{ fontSize: 10, color: delta >= 0 ? "#4ade80" : "#ef4444" }}>
            {delta >= 0 ? "+" : ""}{delta.toFixed(2)}
          </span>
        )}
        <span style={{ fontWeight: 600, color: "#fff", fontVariantNumeric: "tabular-nums" }}>
          ${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>
    </div>
  );
}

function safeText(s: string, maxLen = 500): string {
  return String(s).slice(0, maxLen);
}

export function TradeReceipt({ receipt, onClose }: {
  receipt: TradeReceiptData;
  onClose: () => void;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const confColor   = CONF_COLOR[receipt.confidence.label] ?? "#888";
  const isBuy       = receipt.action === "buy";
  const balanceDiff = receipt.after_balance - receipt.before_balance;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 12 }}
      animate={{ opacity: 1, scale: 1,    y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.25 }}
      style={{
        background:    "#0e0e0e",
        border:        "1px solid rgba(255,255,255,0.1)",
        borderRadius:  18,
        padding:       "22px 22px",
        width:         "100%",
        maxWidth:      420,
        boxShadow:     "0 16px 40px rgba(0,0,0,0.5)",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: "50%",
              background: isBuy ? "rgba(74,222,128,0.12)" : "rgba(239,68,68,0.12)",
              border: `1px solid ${isBuy ? "rgba(74,222,128,0.3)" : "rgba(239,68,68,0.3)"}`,
              display: "flex", alignItems: "center", justifyContent: "center" }}>
              {isBuy ? <TrendingUp size={13} color="#4ade80" /> : <TrendingDown size={13} color="#ef4444" />}
            </div>
            <div>
              <p style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
                {receipt.action.toUpperCase()} {receipt.symbol}
              </p>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginTop: 1 }}>
                {receipt.venue} · {receipt.mode.toUpperCase()}
              </p>
            </div>
          </div>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none",
          color: "rgba(255,255,255,0.25)", cursor: "pointer", padding: 4 }}>
          <X size={14} />
        </button>
      </div>

      {/* AI Explanation */}
      <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 10, padding: "12px 14px", marginBottom: 16 }}>
        <p style={{ fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
          Why this trade?
        </p>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", lineHeight: 1.6 }}>
          {safeText(receipt.ai_explanation)}
        </p>
      </div>

      {/* Confidence */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${receipt.confidence.overall * 100}%` }}
            transition={{ duration: 0.6 }}
            style={{ height: "100%", background: confColor, borderRadius: 2 }}
          />
        </div>
        <span style={{ fontSize: 11, fontWeight: 700, color: confColor,
          background: `${confColor}18`, border: `1px solid ${confColor}30`,
          padding: "2px 8px", borderRadius: 6 }}>
          {receipt.confidence.label} confidence
        </span>
      </div>

      {/* Balance change */}
      <div style={{ marginBottom: 14 }}>
        <BalanceRow label="Before" value={receipt.before_balance} />
        <BalanceRow label="Trade cost"
          value={Math.abs(balanceDiff)}
          delta={balanceDiff} />
        <BalanceRow label="After"  value={receipt.after_balance} />
      </div>

      {/* TP / SL */}
      {(receipt.tp_price || receipt.sl_price) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          {receipt.tp_price && (
            <div style={{ background: "rgba(74,222,128,0.05)", border: "1px solid rgba(74,222,128,0.15)",
              borderRadius: 8, padding: "8px 10px" }}>
              <p style={{ fontSize: 9, color: "#4ade80", textTransform: "uppercase",
                letterSpacing: "0.07em", marginBottom: 2 }}>Take profit</p>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#fff",
                fontVariantNumeric: "tabular-nums" }}>
                ${receipt.tp_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>
          )}
          {receipt.sl_price && (
            <div style={{ background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)",
              borderRadius: 8, padding: "8px 10px" }}>
              <p style={{ fontSize: 9, color: "#ef4444", textTransform: "uppercase",
                letterSpacing: "0.07em", marginBottom: 2 }}>Stop loss</p>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#fff",
                fontVariantNumeric: "tabular-nums" }}>
                ${receipt.sl_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Risk decision */}
      <div style={{ background: receipt.risk.capped ? "rgba(251,191,36,0.05)" : "rgba(74,222,128,0.04)",
        border: `1px solid ${receipt.risk.capped ? "rgba(251,191,36,0.2)" : "rgba(74,222,128,0.15)"}`,
        borderRadius: 8, padding: "10px 12px", marginBottom: 14,
        display: "flex", alignItems: "flex-start", gap: 8 }}>
        <Shield size={12} style={{ color: receipt.risk.capped ? "#fbbf24" : "#4ade80", flexShrink: 0, marginTop: 1 }} />
        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", lineHeight: 1.55 }}>
          {safeText(receipt.risk.human_summary)}
        </p>
      </div>

      {/* Expandable details */}
      <button onClick={() => setShowDetails(d => !d)}
        style={{ width: "100%", background: "none", border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          color: "rgba(255,255,255,0.25)", fontSize: 11, padding: "4px 0" }}>
        {showDetails ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        {showDetails ? "Hide details" : "Show technical details"}
      </button>

      <AnimatePresence>
        {showDetails && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }} style={{ overflow: "hidden" }}>
            <div style={{ marginTop: 10, borderTop: "1px solid rgba(255,255,255,0.05)",
              paddingTop: 10 }}>
              {[
                { label: "Trade ID",     value: receipt.trade_id.slice(0, 18) + "…" },
                { label: "Trace ID",     value: receipt.trace_id.slice(0, 18) + "…" },
                { label: "Quantity",     value: `${receipt.quantity.toFixed(6)} units` },
                { label: "Fill price",   value: `$${receipt.price.toLocaleString()}` },
                { label: "Receipt hash", value: receipt.receipt_hash },
                { label: "Timestamp",    value: new Date(receipt.timestamp).toLocaleString() },
              ].map(r => (
                <div key={r.label} style={{ display: "flex", justifyContent: "space-between",
                  padding: "4px 0", fontSize: 10 }}>
                  <span style={{ color: "rgba(255,255,255,0.25)" }}>{r.label}</span>
                  <span style={{ color: "rgba(255,255,255,0.5)", fontFamily: "monospace" }}>{r.value}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tamper-evident footer */}
      <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 6,
        justifyContent: "center" }}>
        <Check size={10} style={{ color: "#4ade80" }} />
        <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", letterSpacing: "0.06em" }}>
          ENCRYPTED · TAMPER-EVIDENT · NEVER WITHDRAWAL ACCESS
        </span>
      </div>
    </motion.div>
  );
}
