"use client";
import { motion } from "framer-motion";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  glow?: boolean;
  delay?: number;
  compact?: boolean;
}

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  trend = "neutral",
  glow,
  delay = 0,
  compact = false,
}: StatCardProps) {
  const trendColor =
    trend === "up"
      ? "var(--green)"
      : trend === "down"
      ? "var(--red)"
      : "var(--muted)";

  return (
    <motion.div
      className="card"
      style={{ padding: compact ? "18px 18px" : "24px 26px" }}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut", delay }}
      whileHover={{ scale: 1.01, transition: { duration: 0.2 } }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p
            style={{
              color: "var(--muted)",
              fontSize: compact ? 10 : 11,
              fontWeight: 500,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginBottom: compact ? 8 : 10,
            }}
          >
            {label}
          </p>
          <p
            style={{
              fontSize: compact ? 22 : 28,
              fontWeight: 700,
              color: "var(--text)",
              textShadow: glow ? "0 0 24px rgba(255,255,255,0.15)" : undefined,
              letterSpacing: "-0.03em",
              lineHeight: 1,
            }}
          >
            {value}
          </p>
          {sub && (
            <p style={{ fontSize: compact ? 11 : 12, color: trendColor, marginTop: compact ? 6 : 8, fontWeight: 500 }}>
              {sub}
            </p>
          )}
        </div>

        {/* Icon badge */}
        <div
          style={{
            width: compact ? 34 : 40,
            height: compact ? 34 : 40,
            borderRadius: 12,
            background: "rgba(255,255,255,0.05)",
            border: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon size={compact ? 15 : 18} style={{ color: "rgba(255,255,255,0.45)" }} />
        </div>
      </div>
    </motion.div>
  );
}
