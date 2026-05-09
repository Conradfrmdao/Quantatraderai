"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, BarChart2, BookOpen, Settings, ChevronUp,
  Play, Square, Zap,
} from "lucide-react";
import { useState } from "react";

interface MobileBottomNavProps {
  // Agent controls
  running:       boolean;
  agentLoading:  boolean;
  onStart:       () => void;
  onStop:        () => void;
  onKillswitch?: () => void;
  // Settings
  strategyType:  string;
  timeframe:     string;
  market:        string;
  onStrategy:    (v: string) => void;
  onTimeframe:   (v: string) => void;
  onMarket:      (v: string) => void;
}

const NAV = [
  { href: "/dashboard",  icon: LayoutDashboard, label: "Home"     },
  { href: "/backtest",   icon: BarChart2,        label: "Backtest" },
  { href: "/journal",    icon: BookOpen,         label: "Journal"  },
  { href: "/settings",   icon: Settings,         label: "Settings" },
];

const sel = (active: boolean): React.CSSProperties => ({
  flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
  justifyContent: "center", gap: 3, paddingTop: 8, paddingBottom: 8,
  color: active ? "#4ade80" : "rgba(255,255,255,0.35)",
  background: "none", border: "none", cursor: "pointer",
  textDecoration: "none",
});

export function MobileBottomNav({
  running, agentLoading, onStart, onStop, onKillswitch,
  strategyType, timeframe, market,
  onStrategy, onTimeframe, onMarket,
}: MobileBottomNavProps) {
  const pathname     = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Controls drawer — slides up when tapped */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 89,
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
          }}
        />
      )}

      <div style={{
        position: "fixed", bottom: open ? 0 : 56, left: 0, right: 0, zIndex: 90,
        background: "#0a0a0a", borderTop: "1px solid rgba(255,255,255,0.08)",
        borderRadius: open ? "16px 16px 0 0" : 0,
        padding: "16px 16px 8px",
        transform: open ? "translateY(0)" : "translateY(-100%)",
        transition: "all 0.3s cubic-bezier(0.32, 0.72, 0, 1)",
        display: open ? "block" : "none",
      }}>
        {/* Drag handle */}
        <div style={{ width: 36, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.15)", margin: "0 auto 16px" }} />

        <p style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.3)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>Agent Settings</p>

        {/* Strategy */}
        <div style={{ marginBottom: 12 }}>
          <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Strategy</p>
          <div style={{ display: "flex", gap: 6 }}>
            {[["MOMENTUM_HUNTER","Momentum"],["SCALPER_AI","Scalper"],["SWING_MASTER","Swing"],["NEWS_REACTOR","News"]].map(([val, label]) => (
              <button key={val} onClick={() => onStrategy(val)} style={{
                flex: 1, padding: "8px 4px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                cursor: "pointer", border: "1px solid",
                background: strategyType === val ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                borderColor: strategyType === val ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                color: strategyType === val ? "#4ade80" : "rgba(255,255,255,0.5)",
              }}>{label}</button>
            ))}
          </div>
        </div>

        {/* Timeframe + Market */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
          <div>
            <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Timeframe</p>
            <div style={{ display: "flex", gap: 4 }}>
              {["1m","5m","15m","1h","4h"].map(tf => (
                <button key={tf} onClick={() => onTimeframe(tf)} style={{
                  flex: 1, padding: "7px 2px", borderRadius: 7, fontSize: 10, fontWeight: 600,
                  cursor: "pointer", border: "1px solid",
                  background: timeframe === tf ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                  borderColor: timeframe === tf ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                  color: timeframe === tf ? "#4ade80" : "rgba(255,255,255,0.5)",
                }}>{tf}</button>
              ))}
            </div>
          </div>
          <div>
            <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Market</p>
            <div style={{ display: "flex", gap: 4 }}>
              {["spot","futures","forex"].map(m => (
                <button key={m} onClick={() => onMarket(m)} style={{
                  flex: 1, padding: "7px 2px", borderRadius: 7, fontSize: 10, fontWeight: 600,
                  cursor: "pointer", border: "1px solid", textTransform: "capitalize",
                  background: market === m ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                  borderColor: market === m ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                  color: market === m ? "#4ade80" : "rgba(255,255,255,0.5)",
                }}>{m}</button>
              ))}
            </div>
          </div>
        </div>

        {/* Start / Stop */}
        <button
          onClick={() => { setOpen(false); running ? onStop() : onStart(); }}
          disabled={agentLoading}
          style={{
            width: "100%", padding: "14px 0", borderRadius: 12, fontSize: 14, fontWeight: 700,
            cursor: agentLoading ? "default" : "pointer", border: "1px solid",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            background: running ? "rgba(239,68,68,0.12)" : "rgba(74,222,128,0.12)",
            borderColor: running ? "rgba(239,68,68,0.35)" : "rgba(74,222,128,0.35)",
            color: running ? "#ef4444" : "#4ade80",
            marginBottom: onKillswitch && running ? 8 : 0,
          }}
        >
          {agentLoading ? "…" : running ? <><Square size={14} /> Stop Agent</> : <><Play size={14} /> Start Agent</>}
        </button>

        {onKillswitch && running && (
          <button onClick={() => { setOpen(false); onKillswitch(); }} style={{
            width: "100%", padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 600,
            cursor: "pointer", border: "1px solid rgba(239,68,68,0.25)",
            background: "rgba(239,68,68,0.06)", color: "#ef4444",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          }}>
            <Zap size={12} /> Emergency — Close All Positions
          </button>
        )}
      </div>

      {/* ── Sticky Bottom Bar ─────────────────────────────────────────── */}
      <nav style={{
        position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 100,
        background: "rgba(8,8,8,0.96)", backdropFilter: "blur(20px)",
        borderTop: "1px solid rgba(255,255,255,0.08)",
        display: "flex", alignItems: "stretch", height: 56,
        paddingBottom: "env(safe-area-inset-bottom)",
      }}>
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || (href === "/dashboard" && pathname.startsWith("/dashboard"));
          return (
            <Link key={href} href={href} style={sel(active)}>
              <Icon size={18} />
              <span style={{ fontSize: 9, fontWeight: active ? 700 : 500, letterSpacing: "0.03em" }}>{label}</span>
            </Link>
          );
        })}

        {/* Controls toggle button — centre */}
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", gap: 3, paddingTop: 8, paddingBottom: 8,
            background: "none", border: "none", cursor: "pointer",
            color: running ? "#4ade80" : "rgba(255,255,255,0.35)",
          }}
        >
          {running
            ? <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#4ade80",
                boxShadow: "0 0 6px rgba(74,222,128,0.6)", animation: "pulse-ring 1.4s ease-out infinite" }} />
            : <ChevronUp size={18} style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform 0.2s" }} />
          }
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.03em" }}>
            {running ? "Live" : "Controls"}
          </span>
        </button>
      </nav>
    </>
  );
}
