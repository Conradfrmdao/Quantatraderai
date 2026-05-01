"use client";
import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, CheckCircle2, AlertTriangle, Info, AlertCircle } from "lucide-react";

type Kind = "info" | "success" | "warning" | "error";

interface Toast { id: string; kind: Kind; message: string; ttl: number }

interface Ctx {
  push: (message: string, kind?: Kind, ttl?: number) => void;
}

const ToastCtx = createContext<Ctx | null>(null);

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be inside <ToastProvider>");
  return ctx.push;
}

const STYLE: Record<Kind, { bg: string; color: string; border: string; Icon: React.ElementType }> = {
  info:    { bg: "rgba(59,130,246,0.08)",  color: "#60a5fa", border: "rgba(59,130,246,0.3)",  Icon: Info           },
  success: { bg: "rgba(74,222,128,0.08)",  color: "#4ade80", border: "rgba(74,222,128,0.3)",  Icon: CheckCircle2   },
  warning: { bg: "rgba(251,191,36,0.08)",  color: "#fbbf24", border: "rgba(251,191,36,0.3)",  Icon: AlertTriangle  },
  error:   { bg: "rgba(239,68,68,0.1)",    color: "#ef4444", border: "rgba(239,68,68,0.3)",   Icon: AlertCircle    },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, kind: Kind = "info", ttl = 4500) => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts(xs => [...xs, { id, kind, message, ttl }]);
  }, []);

  useEffect(() => {
    if (!toasts.length) return;
    const timers = toasts.map(t => setTimeout(
      () => setToasts(xs => xs.filter(x => x.id !== t.id)),
      t.ttl,
    ));
    return () => timers.forEach(clearTimeout);
  }, [toasts]);

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div style={{
        position: "fixed", bottom: 20, right: 20, zIndex: 1000,
        display: "flex", flexDirection: "column", gap: 8,
        maxWidth: 360, pointerEvents: "none",
      }}>
        <AnimatePresence>
          {toasts.map(t => {
            const s = STYLE[t.kind];
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, x: 16, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 16, scale: 0.95 }}
                style={{
                  background: s.bg, border: `1px solid ${s.border}`,
                  borderRadius: 12, padding: "12px 14px",
                  display: "flex", alignItems: "flex-start", gap: 10,
                  backdropFilter: "blur(12px)",
                  pointerEvents: "auto",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                }}
              >
                <s.Icon size={14} style={{ color: s.color, marginTop: 2, flexShrink: 0 }} />
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.85)", flex: 1, lineHeight: 1.5 }}>
                  {t.message}
                </p>
                <button onClick={() => setToasts(xs => xs.filter(x => x.id !== t.id))}
                  style={{ background: "none", border: "none", color: "rgba(255,255,255,0.3)",
                    cursor: "pointer", padding: 0, display: "flex", flexShrink: 0 }}>
                  <X size={13} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}
