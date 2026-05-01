"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ChevronDown, ChevronUp, X, ExternalLink } from "lucide-react";
import Link from "next/link";

const STORAGE_KEY    = "qt:checklist_dismissed";
const ONBOARDING_KEY = "qt:onboarding";
const DAYS_TO_SHOW   = 14;

interface CheckItem {
  id:      string;
  label:   string;
  sub:     string;
  href:    string;
  linkLabel: string;
  doneKey: string;   // localStorage key that marks this done
}

const ITEMS: CheckItem[] = [
  {
    id: "venue",
    label: "Connect your first venue",
    sub: "Link an exchange API key so the AI can trade",
    href: "/settings?tab=venues",
    linkLabel: "Go to Settings →",
    doneKey: "qt:venue_connected",
  },
  {
    id: "paper",
    label: "Start the agent in paper mode",
    sub: "Watch the AI trade with fake money first — no risk",
    href: "/dashboard",
    linkLabel: "Go to Dashboard →",
    doneKey: "qt:agent_started_paper",
  },
  {
    id: "timeline",
    label: "Check the Decision Timeline",
    sub: "See exactly when and why every trade was made",
    href: "/dashboard",
    linkLabel: "View Timeline →",
    doneKey: "qt:timeline_viewed",
  },
  {
    id: "trust",
    label: "Review the Trust Dashboard",
    sub: "Win rate, drawdown, Sharpe — your AI's report card",
    href: "/trust",
    linkLabel: "Open Trust Dashboard →",
    doneKey: "qt:trust_viewed",
  },
  {
    id: "live",
    label: "Go live when you're ready",
    sub: "Toggle paper mode off in Settings → Venues",
    href: "/settings?tab=venues",
    linkLabel: "Settings →",
    doneKey: "qt:went_live",
  },
];

export function GettingStartedChecklist() {
  const [visible,   setVisible]   = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [done,      setDone]      = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Don't show if dismissed
    if (localStorage.getItem(STORAGE_KEY)) return;

    // Only show if onboarded within the last N days
    try {
      const ob = JSON.parse(localStorage.getItem(ONBOARDING_KEY) ?? "{}");
      const age = Date.now() - (ob.completedAt ?? 0);
      if (age > DAYS_TO_SHOW * 24 * 60 * 60 * 1000) return;
    } catch { return; }

    // Read done states
    const doneMap: Record<string, boolean> = {};
    for (const item of ITEMS) {
      doneMap[item.id] = !!localStorage.getItem(item.doneKey);
    }
    setDone(doneMap);
    setVisible(true);
  }, []);

  const completedCount = Object.values(done).filter(Boolean).length;
  const allDone = completedCount === ITEMS.length;

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
  }

  function markDone(id: string, doneKey: string) {
    localStorage.setItem(doneKey, "1");
    setDone(prev => ({ ...prev, [id]: true }));
  }

  if (!visible) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.3 }}
        style={{
          margin: "0 0 20px",
          background: "rgba(74,222,128,0.04)",
          border: "1px solid rgba(74,222,128,0.15)",
          borderRadius: 14, overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px", cursor: "pointer" }}
          onClick={() => setCollapsed(c => !c)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: "50%",
              background: allDone ? "rgba(74,222,128,0.2)" : "rgba(74,222,128,0.1)",
              border: "1px solid rgba(74,222,128,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Check size={12} style={{ color: "#4ade80" }} />
            </div>
            <div>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                Getting started — {completedCount}/{ITEMS.length} steps done
              </p>
              {!collapsed && (
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
                  {allDone ? "You've completed all steps 🎉" : "Complete these to get the most out of QuntaTradeAI"}
                </p>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {/* Progress bar */}
            <div style={{ width: 80, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.08)" }}>
              <div style={{ height: "100%", borderRadius: 2, background: "#4ade80",
                width: `${(completedCount / ITEMS.length) * 100}%`, transition: "width 0.4s" }} />
            </div>
            {collapsed ? <ChevronDown size={14} style={{ color: "rgba(255,255,255,0.3)" }} />
                       : <ChevronUp   size={14} style={{ color: "rgba(255,255,255,0.3)" }} />}
            <button onClick={e => { e.stopPropagation(); dismiss(); }}
              style={{ background: "none", border: "none", cursor: "pointer",
                color: "rgba(255,255,255,0.2)", padding: 2, display: "flex" }}>
              <X size={12} />
            </button>
          </div>
        </div>

        {/* Steps */}
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
              style={{ overflow: "hidden" }}
            >
              <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                {ITEMS.map((item, i) => {
                  const isDone = done[item.id];
                  return (
                    <div key={item.id} style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "10px 16px",
                      borderBottom: i < ITEMS.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                      opacity: isDone ? 0.6 : 1,
                    }}>
                      {/* Check circle */}
                      <button
                        onClick={() => markDone(item.id, item.doneKey)}
                        style={{
                          width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                          background: isDone ? "rgba(74,222,128,0.2)" : "transparent",
                          border: `1.5px solid ${isDone ? "#4ade80" : "rgba(255,255,255,0.2)"}`,
                          cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                          transition: "all 0.2s",
                        }}
                      >
                        {isDone && <Check size={10} style={{ color: "#4ade80" }} />}
                      </button>

                      {/* Text */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 12, fontWeight: isDone ? 400 : 600,
                          color: isDone ? "rgba(255,255,255,0.4)" : "#fff",
                          textDecoration: isDone ? "line-through" : "none" }}>
                          {item.label}
                        </p>
                        <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>{item.sub}</p>
                      </div>

                      {/* Link */}
                      {!isDone && (
                        <Link href={item.href}
                          onClick={() => markDone(item.id, item.doneKey)}
                          style={{ fontSize: 11, color: "#4ade80", textDecoration: "none",
                            display: "flex", alignItems: "center", gap: 3, flexShrink: 0,
                            fontWeight: 600 }}>
                          {item.linkLabel} <ExternalLink size={9} />
                        </Link>
                      )}
                    </div>
                  );
                })}
              </div>

              {allDone && (
                <div style={{ padding: "12px 16px", textAlign: "center",
                  borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                  <p style={{ fontSize: 12, color: "rgba(255,255,255,0.45)" }}>
                    🎉 All done! You&apos;re a QuntaTradeAI pro now.{" "}
                    <button onClick={dismiss}
                      style={{ color: "#4ade80", background: "none", border: "none",
                        cursor: "pointer", fontSize: 12, textDecoration: "underline" }}>
                      Dismiss this checklist
                    </button>
                  </p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </AnimatePresence>
  );
}
