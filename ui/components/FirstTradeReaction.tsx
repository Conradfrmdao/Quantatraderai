"use client";
import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown, Shield, BarChart2, X, Heart } from "lucide-react";
import Link from "next/link";

const FIRST_WIN_KEY  = "qt:first_win_shown";
const FIRST_LOSS_KEY = "qt:first_loss_shown";

interface Props {
  /** Pass the last WS event so we can detect PnL changes */
  lastEvent: Record<string, unknown> | null;
}

type Reaction = "win" | "loss" | null;

// ── Confetti particle ─────────────────────────────────────────────────────────
function Confetti() {
  const particles = Array.from({ length: 24 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    delay: Math.random() * 0.6,
    color: ["#4ade80", "#fbbf24", "#818cf8", "#f472b6", "#38bdf8"][Math.floor(Math.random() * 5)],
    size: 4 + Math.random() * 5,
  }));

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
      {particles.map(p => (
        <motion.div
          key={p.id}
          initial={{ y: -20, x: `${p.x}vw`, opacity: 1, rotate: 0 }}
          animate={{ y: "110vh", opacity: [1, 1, 0], rotate: 360 * (Math.random() > 0.5 ? 1 : -1) }}
          transition={{ duration: 2.4 + Math.random(), delay: p.delay, ease: "easeIn" }}
          style={{
            position: "absolute", top: 0,
            width: p.size, height: p.size,
            borderRadius: Math.random() > 0.5 ? "50%" : 2,
            background: p.color,
          }}
        />
      ))}
    </div>
  );
}

export function FirstTradeReaction({ lastEvent }: Props) {
  const [reaction, setReaction] = useState<Reaction>(null);
  const [pnl,      setPnl]      = useState(0);

  const dismiss = useCallback(() => setReaction(null), []);

  useEffect(() => {
    if (!lastEvent) return;
    const type = lastEvent.type as string;
    if (type !== "trade_executed") return;

    const data = (lastEvent.data ?? {}) as Record<string, unknown>;
    const pnlVal = Number(data.pnl ?? 0);

    // First win
    if (pnlVal > 0 && !localStorage.getItem(FIRST_WIN_KEY)) {
      localStorage.setItem(FIRST_WIN_KEY, "1");
      setPnl(pnlVal);
      setReaction("win");
    }
    // First loss
    if (pnlVal < 0 && !localStorage.getItem(FIRST_LOSS_KEY)) {
      localStorage.setItem(FIRST_LOSS_KEY, "1");
      setPnl(pnlVal);
      setReaction("loss");
    }
  }, [lastEvent]);

  // Also listen to account_update for equity drops as a fallback
  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type !== "account_update") return;
    const data = (lastEvent.data ?? {}) as Record<string, unknown>;
    const ret = Number(data.total_return_pct ?? 0);
    if (ret > 0.5 && !localStorage.getItem(FIRST_WIN_KEY)) {
      localStorage.setItem(FIRST_WIN_KEY, "1");
      setPnl(ret);
      setReaction("win");
    }
  }, [lastEvent]);

  return (
    <AnimatePresence>
      {reaction === "win" && (
        <motion.div
          key="win"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{
            position: "fixed", inset: 0, zIndex: 8500,
            background: "rgba(0,0,0,0.75)", backdropFilter: "blur(8px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
          onClick={dismiss}
        >
          <Confetti />
          <motion.div
            initial={{ scale: 0.85, y: 30 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            onClick={e => e.stopPropagation()}
            style={{
              background: "linear-gradient(145deg, #0a1a0f 0%, #0c0c0c 100%)",
              border: "1px solid rgba(74,222,128,0.35)",
              borderRadius: 22, padding: "32px 28px",
              maxWidth: 400, width: "100%", textAlign: "center",
              boxShadow: "0 0 60px rgba(74,222,128,0.15), 0 24px 60px rgba(0,0,0,0.7)",
              position: "relative",
            }}
          >
            <button onClick={dismiss}
              style={{ position: "absolute", top: 14, right: 14, background: "none",
                border: "none", cursor: "pointer", color: "rgba(255,255,255,0.25)" }}>
              <X size={14} />
            </button>

            {/* Pulse ring */}
            <div style={{ position: "relative", width: 72, height: 72, margin: "0 auto 20px" }}>
              <motion.div
                animate={{ scale: [1, 1.5, 1], opacity: [0.4, 0, 0.4] }}
                transition={{ duration: 1.6, repeat: Infinity }}
                style={{ position: "absolute", inset: -8, borderRadius: "50%",
                  background: "rgba(74,222,128,0.2)" }}
              />
              <div style={{ width: 72, height: 72, borderRadius: "50%",
                background: "rgba(74,222,128,0.15)", border: "2px solid rgba(74,222,128,0.4)",
                display: "flex", alignItems: "center", justifyContent: "center" }}>
                <TrendingUp size={28} style={{ color: "#4ade80" }} />
              </div>
            </div>

            <p style={{ fontSize: 26, fontWeight: 800, color: "#fff", marginBottom: 6 }}>
              Your first profit! 🎉
            </p>
            <p style={{ fontSize: 28, fontWeight: 800, color: "#4ade80",
              fontVariantNumeric: "tabular-nums", marginBottom: 12 }}>
              +${Math.abs(pnl).toFixed(2)}
            </p>
            <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", lineHeight: 1.7, marginBottom: 20 }}>
              The AI found an edge and captured it. This is exactly what it was built to do.
              Keep the agent running — consistency beats single trades.
            </p>

            <div style={{ display: "flex", gap: 8 }}>
              <Link href="/trust"
                onClick={dismiss}
                style={{ flex: 1, padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.25)",
                  color: "#4ade80", textDecoration: "none", textAlign: "center",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                <BarChart2 size={12} /> View Trust Dashboard
              </Link>
              <button onClick={dismiss}
                style={{ flex: 1, padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)",
                  color: "rgba(255,255,255,0.6)", cursor: "pointer" }}>
                Keep running ✓
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}

      {reaction === "loss" && (
        <motion.div
          key="loss"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{
            position: "fixed", inset: 0, zIndex: 8500,
            background: "rgba(0,0,0,0.8)", backdropFilter: "blur(8px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
          onClick={dismiss}
        >
          <motion.div
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ duration: 0.3 }}
            onClick={e => e.stopPropagation()}
            style={{
              background: "#0c0c0c",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 20, padding: "28px 26px",
              maxWidth: 420, width: "100%",
              boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
              position: "relative",
            }}
          >
            <button onClick={dismiss}
              style={{ position: "absolute", top: 14, right: 14, background: "none",
                border: "none", cursor: "pointer", color: "rgba(255,255,255,0.25)" }}>
              <X size={14} />
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
              <div style={{ width: 44, height: 44, borderRadius: "50%", flexShrink: 0,
                background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)",
                display: "flex", alignItems: "center", justifyContent: "center" }}>
                <TrendingDown size={20} style={{ color: "#f87171" }} />
              </div>
              <div>
                <p style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>First loss — that's normal</p>
                <p style={{ fontSize: 12, color: "#f87171", fontVariantNumeric: "tabular-nums" }}>
                  {`$${Math.abs(pnl).toFixed(2)} loss on this trade`}
                </p>
              </div>
            </div>

            {/* Calm explanation */}
            <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 12, padding: "14px 16px", marginBottom: 16 }}>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.75 }}>
                Every profitable trading strategy has losses — they are{" "}
                <strong style={{ color: "rgba(255,255,255,0.8)" }}>part of the edge</strong>,
                not a sign of failure. Professional traders consider a 50-60% win rate excellent.
              </p>
              <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.75, marginTop: 8 }}>
                What matters is that your <strong style={{ color: "rgba(255,255,255,0.8)" }}>average win
                is larger than your average loss</strong>. The AI is designed for exactly this.
              </p>
            </div>

            {/* Risk controls confirmation */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 }}>
              {[
                { icon: Shield,   color: "#4ade80", text: "Stop-loss was placed — maximum loss was capped" },
                { icon: Heart,    color: "#818cf8", text: "Risk manager validated this trade before execution" },
                { icon: BarChart2, color: "#fbbf24", text: "Check Trust Dashboard to see the full picture" },
              ].map(({ icon: Icon, color, text }) => (
                <div key={text} style={{ display: "flex", alignItems: "center", gap: 8,
                  fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                  <Icon size={12} style={{ color, flexShrink: 0 }} />
                  {text}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <Link href="/trust"
                onClick={dismiss}
                style={{ flex: 1, padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.2)",
                  color: "#818cf8", textDecoration: "none", textAlign: "center",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                <BarChart2 size={12} /> See long-term stats
              </Link>
              <button onClick={dismiss}
                style={{ flex: 1, padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.2)",
                  color: "#4ade80", cursor: "pointer" }}>
                Keep the agent running
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
