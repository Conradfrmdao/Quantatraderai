"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, AlertTriangle, X } from "lucide-react";

const STORAGE_KEY = "qunta_risk_ack_v1";

interface Props {
  onAccept?: () => void;
}

export function DisclaimerModal({ onAccept }: Props) {
  const [open, setOpen]     = useState(false);
  const [checks, setChecks] = useState({ c1: false, c2: false, c3: false });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const acked = localStorage.getItem(STORAGE_KEY);
    if (!acked) setOpen(true);
  }, []);

  const allChecked = checks.c1 && checks.c2 && checks.c3;

  function accept() {
    localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    setOpen(false);
    onAccept?.();
  }

  const toggle = (key: keyof typeof checks) =>
    setChecks(prev => ({ ...prev, [key]: !prev[key] }));

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{
            position: "fixed", inset: 0, zIndex: 9999,
            background: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "20px",
          }}
        >
          <motion.div
            initial={{ scale: 0.92, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{
              background: "#0e0e0e", border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 20, padding: "28px 28px 24px",
              maxWidth: 460, width: "100%",
              boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 20 }}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%", flexShrink: 0,
                background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.25)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <AlertTriangle size={18} style={{ color: "#fbbf24" }} />
              </div>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
                  Important Risk Disclosure
                </h2>
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", lineHeight: 1.5 }}>
                  Please read carefully before using QuntaTradeAI
                </p>
              </div>
            </div>

            {/* Body */}
            <div style={{
              background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 12, padding: "14px 16px", marginBottom: 20,
              fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.7,
            }}>
              <p style={{ marginBottom: 10 }}>
                QuntaTradeAI is an <strong style={{ color: "rgba(255,255,255,0.7)" }}>automated AI trading tool</strong>,
                not a financial advisor. Trading involves substantial risk of loss.
              </p>
              <p>
                Past performance of any strategy, including AI-generated ones, does not
                guarantee future results. You can lose all of your invested capital.
              </p>
            </div>

            {/* Checkboxes */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 22 }}>
              {[
                { key: "c1" as const, text: "I understand this is NOT financial advice and I trade at my own risk." },
                { key: "c2" as const, text: "I acknowledge that automated trading can result in significant financial losses." },
                { key: "c3" as const, text: "I am solely responsible for my trading decisions and any outcomes." },
              ].map(({ key, text }) => (
                <label key={key}
                  style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer" }}
                  onClick={() => toggle(key)}
                >
                  <div style={{
                    width: 18, height: 18, borderRadius: 5, flexShrink: 0, marginTop: 1,
                    background: checks[key] ? "#4ade80" : "rgba(255,255,255,0.08)",
                    border: `1px solid ${checks[key] ? "#4ade80" : "rgba(255,255,255,0.15)"}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    transition: "all 0.15s",
                  }}>
                    {checks[key] && (
                      <svg width={10} height={8} viewBox="0 0 10 8" fill="none">
                        <path d="M1 4l3 3 5-6" stroke="#000" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                  <span style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.5 }}>
                    {text}
                  </span>
                </label>
              ))}
            </div>

            {/* Footer */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Shield size={11} style={{ color: "rgba(255,255,255,0.2)", flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 10, color: "rgba(255,255,255,0.2)" }}>
                This acknowledgment is stored locally and will not be shown again.
              </span>
              <button
                onClick={accept}
                disabled={!allChecked}
                style={{
                  background: allChecked ? "#4ade80" : "rgba(255,255,255,0.06)",
                  color:      allChecked ? "#000" : "rgba(255,255,255,0.25)",
                  border: "none", borderRadius: 10, padding: "9px 20px",
                  fontSize: 13, fontWeight: 700, cursor: allChecked ? "pointer" : "not-allowed",
                  transition: "all 0.15s", flexShrink: 0,
                }}
              >
                I Understand — Continue
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Hook to reset the disclaimer (for testing / sign-out). */
export function clearDisclaimerAck() {
  if (typeof window !== "undefined") localStorage.removeItem(STORAGE_KEY);
}
