'use client';

import React, { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, ArrowRight, KeyRound } from "lucide-react";
import dynamic from "next/dynamic";
import { Logo, LogoWordmark } from "@/components/Logo";
import { APP_NAME } from "@/lib/constants";

const CanvasRevealEffect = dynamic(
  () => import("@/components/ui/canvas-reveal-effect").then((m) => m.CanvasRevealEffect),
  { ssr: false }
);

/* ─── shared button styles ─────────────────────────────────── */
const btnPrimary: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
  width: "100%", padding: "14px 24px", borderRadius: 12,
  background: "#ffffff", color: "#000000",
  fontWeight: 600, fontSize: 15, cursor: "pointer",
  border: "none", transition: "opacity .15s", letterSpacing: "-0.01em",
};

const btnGhost: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "8px 14px", borderRadius: 10, border: "none",
  background: "transparent", color: "rgba(255,255,255,0.4)",
  fontWeight: 500, fontSize: 14, cursor: "pointer",
  textDecoration: "none", transition: "color .15s",
};

/* ─── OTP input ─────────────────────────────────────────────── */
function OtpInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const digits = 6;
  const chars  = value.split("").concat(Array(digits).fill("")).slice(0, digits);

  return (
    <div style={{ position: "relative", display: "flex", gap: 8, justifyContent: "center" }}>
      {chars.map((ch, i) => (
        <div
          key={i}
          style={{
            width: 44, height: 52, borderRadius: 12,
            border: `1px solid ${value.length === i ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.08)"}`,
            background: "rgba(255,255,255,0.03)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontFamily: "monospace", fontSize: 20, fontWeight: 600,
            position: "relative",
            boxShadow: value.length === i ? "0 0 0 1px rgba(255,255,255,0.12)" : undefined,
          }}
        >
          {ch}
          {value.length === i && (
            <span style={{ position: "absolute", bottom: 8, left: "50%", transform: "translateX(-50%)", width: 14, height: 1.5, background: "#fff", borderRadius: 1 }} className="pulse" />
          )}
        </div>
      ))}
      <input
        type="text" inputMode="numeric" pattern="[0-9]*"
        maxLength={digits} value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))}
        autoFocus
        style={{ position: "absolute", inset: 0, opacity: 0, cursor: "default", zIndex: 1 }}
      />
    </div>
  );
}

/* ─── Sign-in ───────────────────────────────────────────────── */
export function SignIn() {
  const [step,  setStep]  = useState<"email" | "otp" | "done">("email");
  const [email, setEmail] = useState("");
  const [otp,   setOtp]   = useState("");

  return (
    <div style={{ position: "relative", minHeight: "100vh", background: "#000", color: "#fff", display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* WebGL background */}
      <div style={{ position: "absolute", inset: 0, zIndex: 0 }}>
        <CanvasRevealEffect className="w-full h-full" revealDuration={3} />
      </div>

      {/* Vignette */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse 90% 90% at 50% 50%, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.72) 65%, rgba(0,0,0,0.95) 100%)",
      }} />

      {/* Navbar */}
      <motion.nav
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
          position: "relative", zIndex: 10,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 28px", height: 60,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <LogoWordmark size={28} />
        <Link href="/" style={btnGhost}>
          <ArrowLeft size={14} /> Back
        </Link>
      </motion.nav>

      {/* Centered card */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "32px 20px", position: "relative", zIndex: 10 }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          style={{ width: "100%", maxWidth: 420 }}
        >
          <div style={{
            borderRadius: 24,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.03)",
            backdropFilter: "blur(28px)",
            WebkitBackdropFilter: "blur(28px)",
            padding: "40px 36px",
          }}>
            <AnimatePresence mode="wait">

              {/* Email step */}
              {step === "email" && (
                <motion.div key="email" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.3 }}>
                  <div style={{ textAlign: "center", marginBottom: 32 }}>
                    <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
                      <Logo size={52} />
                    </div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8, letterSpacing: "-0.02em" }}>
                      Sign in to {APP_NAME}
                    </h1>
                    <p style={{ fontSize: 14, color: "rgba(255,255,255,0.38)", lineHeight: 1.5 }}>
                      Enter your email to receive a one-time code.
                    </p>
                    <p style={{ fontSize: 13, color: "rgba(255,255,255,0.28)", marginTop: 8 }}>
                      No account?{" "}
                      <Link href="/sign-up" style={{ color: "rgba(255,255,255,0.55)", textDecoration: "none" }}>
                        Create one
                      </Link>
                    </p>
                  </div>

                  <form onSubmit={(e) => { e.preventDefault(); if (email) setStep("otp"); }} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <input
                      type="email" placeholder="you@example.com"
                      value={email} onChange={(e) => setEmail(e.target.value)}
                      required autoFocus
                      style={{
                        width: "100%", padding: "14px 16px", borderRadius: 12,
                        border: "1px solid rgba(255,255,255,0.1)",
                        background: "rgba(255,255,255,0.04)",
                        color: "#fff", fontSize: 15, outline: "none",
                        transition: "border-color .15s",
                      }}
                    />
                    <button type="submit" style={btnPrimary}>
                      Continue <ArrowRight size={15} />
                    </button>
                  </form>
                </motion.div>
              )}

              {/* OTP step */}
              {step === "otp" && (
                <motion.div key="otp" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.3 }}>
                  <div style={{ textAlign: "center", marginBottom: 32 }}>
                    <div style={{
                      width: 48, height: 48, borderRadius: 14, margin: "0 auto 20px",
                      border: "1px solid rgba(255,255,255,0.1)",
                      background: "rgba(255,255,255,0.05)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      <KeyRound size={20} style={{ color: "rgba(255,255,255,0.55)" }} />
                    </div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8, letterSpacing: "-0.02em" }}>
                      Check your email
                    </h1>
                    <p style={{ fontSize: 14, color: "rgba(255,255,255,0.38)", lineHeight: 1.5 }}>
                      Code sent to <span style={{ color: "rgba(255,255,255,0.65)" }}>{email}</span>
                    </p>
                  </div>

                  <form onSubmit={(e) => { e.preventDefault(); if (otp.length >= 6) setStep("done"); }} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    <OtpInput value={otp} onChange={setOtp} />
                    <button type="submit" disabled={otp.length < 6} style={{ ...btnPrimary, opacity: otp.length < 6 ? 0.4 : 1 }}>
                      Verify <KeyRound size={15} />
                    </button>
                  </form>

                  <button onClick={() => { setStep("email"); setOtp(""); }}
                    style={{ marginTop: 18, width: "100%", textAlign: "center", fontSize: 13, color: "rgba(255,255,255,0.25)", background: "none", border: "none", cursor: "pointer", transition: "color .15s" }}>
                    ← Use a different email
                  </button>
                </motion.div>
              )}

              {/* Done step */}
              {step === "done" && (
                <motion.div key="done" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }} style={{ textAlign: "center", padding: "16px 0" }}>
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 16, delay: 0.1 }}
                    style={{
                      width: 56, height: 56, borderRadius: "50%", margin: "0 auto 24px",
                      border: "1px solid rgba(255,255,255,0.12)",
                      background: "rgba(255,255,255,0.06)",
                      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24,
                    }}
                  >✓</motion.div>
                  <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10, letterSpacing: "-0.02em" }}>You&apos;re in</h2>
                  <p style={{ fontSize: 14, color: "rgba(255,255,255,0.38)", marginBottom: 28 }}>Redirecting to your dashboard…</p>
                  <Link href="/dashboard" style={btnPrimary}>
                    Open Dashboard <ArrowRight size={15} />
                  </Link>
                </motion.div>
              )}

            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
