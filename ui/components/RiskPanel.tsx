"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RiskConfig {
  max_position_pct?: string;
  max_leverage?: string;
  mandatory_sl_pct?: string;
  max_loss_per_position_pct?: string;
  daily_loss_circuit_breaker_pct?: string;
  max_total_exposure_pct?: string;
  max_concurrent_positions?: string;
}

interface VaRData {
  monte_carlo?: {
    current_equity?: number;
    var_95?: { usd: number; pct: number };
    var_99?: { usd: number; pct: number };
  };
  parametric?: {
    var_95?: { usd: number; pct: number };
    var_99?: { usd: number; pct: number };
  };
}

function RiskRow({ label, value, unit = "%", cap = 50, delay = 0, color }:
  { label: string; value?: string; unit?: string; cap?: number; delay?: number; color?: string }) {
  const num = parseFloat(value ?? "0");
  const pct = Math.min((num / cap) * 100, 100);
  const barColor = color ?? "linear-gradient(90deg,rgba(255,255,255,0.7),rgba(255,255,255,0.35))";

  return (
    <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.4 }} style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 7 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)", fontFamily: "monospace" }}>
          {value ?? "—"}{unit}
        </span>
      </div>
      <div style={{ height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut", delay: delay + 0.1 }}
          style={{ height: "100%", background: barColor, borderRadius: 2 }}
        />
      </div>
    </motion.div>
  );
}

function VarSection({ var_data }: { var_data: VaRData | null }) {
  if (!var_data?.monte_carlo) return null;
  const mc   = var_data.monte_carlo;
  const v95  = mc.var_95;
  const v99  = mc.var_99;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.5 }}
      style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.06)" }}
    >
      <p style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase",
        letterSpacing: "0.1em", color: "rgba(255,255,255,0.3)", marginBottom: 12 }}>
        Value at Risk · Monte Carlo 10k
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {[
          { label: "VaR 95%", data: v95 },
          { label: "VaR 99%", data: v99 },
        ].map(({ label, data }) => (
          <div key={label} style={{
            background: "rgba(239,68,68,0.05)",
            border: "1px solid rgba(239,68,68,0.15)",
            borderRadius: 10, padding: "10px 12px",
          }}>
            <p style={{ fontSize: 9, fontWeight: 600, color: "var(--red)", textTransform: "uppercase",
              letterSpacing: "0.08em", marginBottom: 6 }}>{label}</p>
            {data ? (
              <>
                <p style={{ fontSize: 16, fontWeight: 600, color: "#fff",
                  fontVariantNumeric: "tabular-nums", marginBottom: 2 }}>
                  ${data.usd.toFixed(2)}
                </p>
                <p style={{ fontSize: 10, color: "rgba(239,68,68,0.8)" }}>
                  {data.pct.toFixed(2)}% of equity
                </p>
              </>
            ) : (
              <p style={{ fontSize: 12, color: "var(--muted)" }}>—</p>
            )}
          </div>
        ))}
      </div>
      {mc.current_equity && (
        <p style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", marginTop: 8, textAlign: "right" }}>
          Portfolio: ${mc.current_equity.toLocaleString("en-US", { maximumFractionDigits: 2 })}
        </p>
      )}
    </motion.div>
  );
}

export function RiskPanel({ risk }: { risk: RiskConfig | null }) {
  const [varData, setVarData] = useState<VaRData | null>(null);

  useEffect(() => {
    const load = () =>
      fetch(`${API}/api/var`)
        .then(r => r.json())
        .then((d: VaRData) => setVarData(d))
        .catch(() => {});
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <RiskRow label="Max position size"     value={risk?.max_position_pct}               cap={20}  delay={0}    />
      <RiskRow label="Max leverage"          value={risk?.max_leverage}  unit="×"          cap={20}  delay={0.05} />
      <RiskRow label="Stop-loss distance"    value={risk?.mandatory_sl_pct}               cap={20}  delay={0.1}  />
      <RiskRow label="Force-close loss"      value={risk?.max_loss_per_position_pct}      cap={30}  delay={0.15} />
      <RiskRow label="Daily circuit breaker" value={risk?.daily_loss_circuit_breaker_pct} cap={20}  delay={0.2}  />
      <RiskRow label="Max total exposure"    value={risk?.max_total_exposure_pct}         cap={100} delay={0.25} />
      <RiskRow label="Max positions"         value={risk?.max_concurrent_positions} unit="" cap={20} delay={0.3}  />
      <VarSection var_data={varData} />
    </div>
  );
}
