"use client";

interface RiskConfig {
  max_position_pct?: string;
  max_leverage?: string;
  mandatory_sl_pct?: string;
  max_loss_per_position_pct?: string;
  daily_loss_circuit_breaker_pct?: string;
  max_total_exposure_pct?: string;
  max_concurrent_positions?: string;
}

function RiskRow({ label, value, unit = "%" }: { label: string; value?: string; unit?: string }) {
  const num = parseFloat(value ?? "0");
  // bar width as percentage of some max
  const maxes: Record<string, number> = { "%": 50, x: 20 };
  const cap = maxes[unit] ?? 50;
  const pct = Math.min((num / cap) * 100, 100);
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", fontFamily: "monospace" }}>
          {value ?? "—"}{unit}
        </span>
      </div>
      <div style={{ height: 4, background: "var(--surface-2)", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "linear-gradient(90deg, var(--accent), var(--green))",
            borderRadius: 2,
            transition: "width 0.5s ease",
          }}
        />
      </div>
    </div>
  );
}

export function RiskPanel({ risk }: { risk: RiskConfig | null }) {
  return (
    <div>
      <RiskRow label="Max position size" value={risk?.max_position_pct} />
      <RiskRow label="Max leverage" value={risk?.max_leverage} unit="x" />
      <RiskRow label="Stop-loss distance" value={risk?.mandatory_sl_pct} />
      <RiskRow label="Force-close loss" value={risk?.max_loss_per_position_pct} />
      <RiskRow label="Daily circuit breaker" value={risk?.daily_loss_circuit_breaker_pct} />
      <RiskRow label="Max total exposure" value={risk?.max_total_exposure_pct} />
      <RiskRow label="Max positions" value={risk?.max_concurrent_positions} unit="" />
    </div>
  );
}
