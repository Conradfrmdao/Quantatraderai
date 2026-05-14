"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, BarChart2, BookOpen, ShieldCheck,
  Play, Square, Zap, X, MoreHorizontal, Shield,
  ShoppingBag, Copy, FileText, Settings, Book,
} from "lucide-react";
import { useState } from "react";

interface MobileBottomNavProps {
  running:       boolean;
  agentLoading:  boolean;
  onStart:       () => void;
  onStop:        () => void;
  onKillswitch?: () => void;
  killConfirm?:  boolean;
  isPaperMode?:  boolean;
  strategyType:  string;
  timeframe:     string;
  market:        string;
  marketOptions: { value: string; label: string }[];
  onStrategy:    (v: string) => void;
  onTimeframe:   (v: string) => void;
  onMarket:      (v: string) => void;
  showGuards?:    boolean;
  onToggleGuards?: () => void;
}

const NAV = [
  { href: "/dashboard",  icon: LayoutDashboard, label: "Home"     },
  { href: "/backtest",   icon: BarChart2,        label: "Backtest" },
  { href: "/journal",    icon: BookOpen,         label: "Journal"  },
  { href: "/trust",      icon: ShieldCheck,      label: "Trust"    },
];

const MORE_LINKS = [
  { href: "/marketplace",  icon: ShoppingBag, label: "Marketplace"   },
  { href: "/copy-trading", icon: Copy,        label: "Copy Trading"  },
  { href: "/audit",        icon: FileText,    label: "Audit Log"     },
  { href: "/docs",         icon: Book,        label: "Docs"          },
  { href: "/settings",     icon: Settings,    label: "Settings"      },
];

export function MobileBottomNav({
  running, agentLoading, onStart, onStop, onKillswitch,
  killConfirm = false, isPaperMode = true,
  strategyType, timeframe, market, marketOptions,
  onStrategy, onTimeframe, onMarket,
  showGuards, onToggleGuards,
}: MobileBottomNavProps) {
  const pathname  = usePathname();
  const [open, setOpen] = useState(false);

  const NAV_HEIGHT = 56; // px — must match the nav bar height below

  return (
    <>
      {/* ── Backdrop ─────────────────────────────────────────────────── */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 89,
            background: "rgba(0,0,0,0.65)", backdropFilter: "blur(4px)",
          }}
        />
      )}

      {/* ── Controls Drawer — sits just above the nav bar ────────────── */}
      <div style={{
        position: "fixed",
        bottom: NAV_HEIGHT,          // always anchored above the nav bar
        left: 0, right: 0,
        zIndex: 90,
        background: "#0d0d0d",
        borderTop: "1px solid rgba(255,255,255,0.1)",
        borderRadius: "18px 18px 0 0",
        // max-height keeps it on screen; overflow lets it scroll if phone is tiny
        maxHeight: "75vh",
        overflowY: "auto",
        padding: "0 16px 16px",
        // Slide in/out
        transform: open ? "translateY(0)" : "translateY(105%)",
        transition: "transform 0.3s cubic-bezier(0.32,0.72,0,1)",
        pointerEvents: open ? "auto" : "none",
      }}>
        {/* Drag handle + close */}
        <div style={{ position: "sticky", top: 0, background: "#0d0d0d", padding: "12px 0 10px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.15)", margin: "0 auto" }} />
          <button onClick={() => setOpen(false)} style={{ position: "absolute", right: 0, top: 10, background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.35)", padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <p style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.3)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>
          Agent Controls
        </p>

        {/* ── Strategy ── */}
        <div style={{ marginBottom: 14 }}>
          <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Strategy</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {[["MOMENTUM_HUNTER","Momentum"],["SCALPER_AI","Scalper"],["SWING_MASTER","Swing"],["NEWS_REACTOR","News"]].map(([val, label]) => (
              <button key={val} onClick={() => onStrategy(val)} style={{
                padding: "10px 8px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                cursor: "pointer", border: "1px solid", textAlign: "center",
                background: strategyType === val ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                borderColor: strategyType === val ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                color: strategyType === val ? "#4ade80" : "rgba(255,255,255,0.5)",
              }}>{label}</button>
            ))}
          </div>
        </div>

        {/* ── Timeframe ── */}
        <div style={{ marginBottom: 14 }}>
          <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Timeframe</p>
          <div style={{ display: "flex", gap: 6 }}>
            {["1m","5m","15m","1h","4h"].map(tf => (
              <button key={tf} onClick={() => onTimeframe(tf)} style={{
                flex: 1, padding: "10px 0", borderRadius: 9, fontSize: 11, fontWeight: 600,
                cursor: "pointer", border: "1px solid", textAlign: "center",
                background: timeframe === tf ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                borderColor: timeframe === tf ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                color: timeframe === tf ? "#4ade80" : "rgba(255,255,255,0.5)",
              }}>{tf}</button>
            ))}
          </div>
        </div>

        {/* ── Market ── */}
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Market</p>
          {marketOptions.length > 1 ? (
            <div style={{ display: "flex", gap: 6 }}>
              {marketOptions.map(option => (
                <button key={option.value} onClick={() => onMarket(option.value)} style={{
                  flex: 1, padding: "10px 0", borderRadius: 9, fontSize: 11, fontWeight: 600,
                  cursor: "pointer", border: "1px solid", textTransform: "capitalize", textAlign: "center",
                  background: market === option.value ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.04)",
                  borderColor: market === option.value ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.1)",
                  color: market === option.value ? "#4ade80" : "rgba(255,255,255,0.5)",
                }}>{option.label}</button>
              ))}
            </div>
          ) : (
            <div style={{
              padding: "10px 12px",
              borderRadius: 9,
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.04)",
              fontSize: 11,
              fontWeight: 600,
              color: "rgba(255,255,255,0.5)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              textAlign: "center",
            }}>
              {marketOptions[0]?.label ?? market}
            </div>
          )}
        </div>

        {/* ── Guards toggle ── */}
        {onToggleGuards && (
          <button
            onClick={() => { setOpen(false); onToggleGuards(); }}
            style={{
              width: "100%", padding: "11px 0", borderRadius: 11, fontSize: 12, fontWeight: 600,
              cursor: "pointer", border: "1px solid",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              background: showGuards ? "rgba(251,191,36,0.12)" : "rgba(255,255,255,0.04)",
              borderColor: showGuards ? "rgba(251,191,36,0.35)" : "rgba(255,255,255,0.1)",
              color: showGuards ? "#fbbf24" : "rgba(255,255,255,0.5)",
              marginBottom: 10,
            }}
          >
            <Shield size={13} />
            {showGuards ? "Hide Guard Settings" : "Open Guard Settings"}
          </button>
        )}

        {/* ── Start / Stop ── */}
        <button
          onClick={() => { setOpen(false); running ? onStop() : onStart(); }}
          disabled={agentLoading}
          style={{
            width: "100%", padding: "14px 14px", borderRadius: 16, fontSize: 15, fontWeight: 700,
            cursor: agentLoading ? "default" : "pointer", border: "1px solid",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
            background: running
              ? "linear-gradient(135deg, rgba(127,29,29,0.92), rgba(239,68,68,0.18))"
              : isPaperMode
                ? "linear-gradient(135deg, rgba(8,43,31,0.96), rgba(74,222,128,0.2))"
                : "linear-gradient(135deg, rgba(69,10,10,0.96), rgba(248,113,113,0.18))",
            borderColor: running ? "rgba(248,113,113,0.42)" : isPaperMode ? "rgba(74,222,128,0.4)" : "rgba(248,113,113,0.38)",
            color: running ? "#fecaca" : isPaperMode ? "#dcfce7" : "#fee2e2",
            marginBottom: onKillswitch && running ? 8 : 0,
            boxShadow: running
              ? "0 18px 36px rgba(127,29,29,0.22)"
              : isPaperMode
                ? "0 18px 36px rgba(21,128,61,0.16)"
                : "0 18px 36px rgba(153,27,27,0.18)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 3, textAlign: "left" }}>
            <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: running ? "rgba(254,202,202,0.72)" : isPaperMode ? "rgba(220,252,231,0.7)" : "rgba(254,226,226,0.72)" }}>
              {running ? "Agent Active" : isPaperMode ? "Paper Mode" : "Live Mode"}
            </span>
            <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.01em", color: running ? "#fff1f2" : "#ffffff" }}>
              {agentLoading ? "Working..." : running ? "Stop Agent" : isPaperMode ? "Launch Paper Agent" : "Launch Live Agent"}
            </span>
            <span style={{ fontSize: 11, color: running ? "rgba(254,226,226,0.6)" : "rgba(255,255,255,0.55)" }}>
              {running ? "Stop the current run safely" : isPaperMode ? "Risk-free simulated execution" : "Real orders on the connected venue"}
            </span>
          </div>
          <span style={{
            width: 42,
            height: 42,
            borderRadius: 14,
            border: "1px solid rgba(255,255,255,0.14)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: running ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.06)",
            flexShrink: 0,
          }}>
            {running ? <Square size={16} /> : <Play size={16} />}
          </span>
        </button>

        {onKillswitch && running && (
          <button onClick={() => {
            onKillswitch();
            if (killConfirm) setOpen(false);
          }} style={{
            width: "100%", padding: "12px 14px", borderRadius: 12, fontSize: 12, fontWeight: 700,
            cursor: "pointer", border: "1px solid rgba(239,68,68,0.25)",
            background: killConfirm ? "rgba(239,68,68,0.18)" : "rgba(239,68,68,0.06)",
            borderColor: killConfirm ? "rgba(248,113,113,0.55)" : "rgba(239,68,68,0.25)",
            color: killConfirm ? "#fecaca" : "#ef4444",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          }}>
            <Zap size={13} />
            {killConfirm ? "Tap again to close ALL positions" : "Emergency — Close All Positions"}
          </button>
        )}

        {/* ── More pages ── */}
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", marginTop: 16, paddingTop: 16 }}>
          <p style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.25)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>More</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {MORE_LINKS.map(({ href, icon: Icon, label }) => (
              <a key={href} href={href} onClick={() => setOpen(false)} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "10px 12px",
                borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)",
                background: "rgba(255,255,255,0.03)", color: "rgba(255,255,255,0.6)",
                fontSize: 12, fontWeight: 500, textDecoration: "none",
              }}>
                <Icon size={14} style={{ opacity: 0.7 }} /> {label}
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* ── Bottom Nav Bar ───────────────────────────────────────────── */}
      <nav style={{
        position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 100,
        background: "rgba(6,6,6,0.97)", backdropFilter: "blur(20px)",
        borderTop: "1px solid rgba(255,255,255,0.08)",
        display: "flex", alignItems: "stretch",
        height: NAV_HEIGHT,
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
      }}>
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || (href === "/dashboard" && pathname.startsWith("/dashboard"));
          return (
            <Link key={href} href={href} style={{
              flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
              justifyContent: "center", gap: 3, paddingTop: 8, paddingBottom: 8,
              color: active ? "#4ade80" : "rgba(255,255,255,0.35)",
              textDecoration: "none",
            }}>
              <Icon size={19} />
              <span style={{ fontSize: 9, fontWeight: active ? 700 : 500, letterSpacing: "0.03em" }}>{label}</span>
            </Link>
          );
        })}

        {/* Controls toggle */}
        <button
          onClick={() => setOpen(o => !o)}
          style={{
            flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", gap: 3, paddingTop: 8, paddingBottom: 8,
            background: "none", border: "none", cursor: "pointer",
            color: open ? "#4ade80" : running ? "#4ade80" : "rgba(255,255,255,0.35)",
          }}
        >
          {running && !open
            ? <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#4ade80",
                boxShadow: "0 0 8px rgba(74,222,128,0.7)", marginBottom: 2 }} />
            : <MoreHorizontal size={19} />
          }
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.03em" }}>
            {open ? "Close" : running ? "Live" : "Controls"}
          </span>
        </button>
      </nav>
    </>
  );
}
