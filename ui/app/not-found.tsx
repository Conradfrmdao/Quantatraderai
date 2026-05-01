"use client";
import Link from "next/link";
import { motion } from "framer-motion";
import { LogoWordmark } from "@/components/Logo";

export default function NotFound() {
  return (
    <div style={{
      background: "var(--bg)", minHeight: "100vh",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      padding: 24, textAlign: "center",
    }}>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{ maxWidth: 440 }}
      >
        <LogoWordmark size={32} />

        <p style={{
          fontSize: 72, fontWeight: 700, color: "rgba(255,255,255,0.06)",
          lineHeight: 1, margin: "32px 0 0", letterSpacing: "-4px",
          fontVariantNumeric: "tabular-nums",
        }}>
          404
        </p>

        <p style={{ fontSize: 20, fontWeight: 600, color: "#fff", margin: "16px 0 8px" }}>
          Page not found
        </p>
        <p style={{ fontSize: 14, color: "var(--muted)", lineHeight: 1.6, marginBottom: 32 }}>
          The page you are looking for doesn&apos;t exist or has been moved.
        </p>

        <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/dashboard" style={{
            padding: "10px 22px", borderRadius: 10,
            background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)",
            color: "#fff", fontWeight: 600, fontSize: 13, textDecoration: "none",
          }}>
            Go to Dashboard
          </Link>
          <Link href="/" style={{
            padding: "10px 22px", borderRadius: 10,
            background: "transparent", border: "1px solid rgba(255,255,255,0.08)",
            color: "var(--muted)", fontSize: 13, textDecoration: "none",
          }}>
            Home
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
