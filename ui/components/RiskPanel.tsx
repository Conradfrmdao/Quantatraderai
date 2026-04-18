"use client";
import { motion } from "framer-motion";

interface RiskConfig {
  max_position_pct?: string;
  max_leverage?: string;
  mandatory_sl_pct?: string;
  max_loss_per_position_pct?: string;
  daily_loss_circuit_breaker_pct?: string;
  max_total_exposure_pct?: string;
  max_concurrent_positions?: string;
}

function RiskRow({
  label,
  value,
  unit = "%",
  cap = 50,
  delay = 0,
}: {
  label: string;
  value?: string;
  unit?: string;
  cap?: number;
  delay?: number;
}) {
  const num = parseFloat(value ?? "0");
  const pct = Math.min((num / cap) * 100, 100);

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.4 }}
      style={{ marginBottom: 16 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{label}</span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "rgba(255,255,255,0.8)",
            fontFamily: "monospace",
          }}
        >
          {value ?? "—"}{unit}
        </span>
      </div>
      <div
        style={{
          height: 3,
          background: "rgba(255,255,255,0.06)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut", delay: delay + 0.1 }}
          style={{
            height: "100%",
            background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
            borderRadius: 2,
          }}
        />
      </div>
    </motion.div>
  );
}

export function RiskPanel({ risk }: { risk: RiskConfig | null }) {
  return (
    <div>
      <RiskRow label="Max position size"     value={risk?.max_position_pct}            cap={20}  delay={0}    />
      <RiskRow label="Max leverage"          value={risk?.max_leverage}                unit="×" cap={20} delay={0.05} />
      <RiskRow label="Stop-loss distance"    value={risk?.mandatory_sl_pct}            cap={20}  delay={0.1}  />
      <RiskRow label="Force-close loss"      value={risk?.max_loss_per_position_pct}   cap={30}  delay={0.15} />
      <RiskRow label="Daily circuit breaker" value={risk?.daily_loss_circuit_breaker_pct} cap={20} delay={0.2} />
      <RiskRow label="Max total exposure"    value={risk?.max_total_exposure_pct}      cap={100} delay={0.25} />
      <RiskRow label="Max positions"        value={risk?.max_concurrent_positions}    unit=""  cap={20}  delay={0.3}  />
    </div>
  );
}
