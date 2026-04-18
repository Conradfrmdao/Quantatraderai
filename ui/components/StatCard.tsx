"use client";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  glow?: boolean;
}

export function StatCard({ label, value, sub, icon: Icon, trend = "neutral", glow }: StatCardProps) {
  const trendColor =
    trend === "up" ? "var(--green)" : trend === "down" ? "var(--red)" : "var(--muted)";

  return (
    <div className="card p-5 fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
            {label}
          </p>
          <p
            style={{
              fontSize: 26,
              fontWeight: 700,
              color: glow ? "var(--accent)" : "var(--text)",
              textShadow: glow ? "0 0 20px var(--accent-glow)" : undefined,
              letterSpacing: "-0.02em",
            }}
          >
            {value}
          </p>
          {sub && (
            <p style={{ fontSize: 12, color: trendColor, marginTop: 4, fontWeight: 500 }}>{sub}</p>
          )}
        </div>
        <div
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon size={18} style={{ color: "var(--accent)" }} />
        </div>
      </div>
    </div>
  );
}
