"use client";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { motion } from "framer-motion";

interface Point { t: string; equity: number }

const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: "rgba(10,10,10,0.95)",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: 12,
        padding: "10px 14px",
        fontSize: 12,
        backdropFilter: "blur(12px)",
      }}
    >
      <p style={{ color: "var(--muted)", marginBottom: 4 }}>{label}</p>
      <p style={{ color: "#fff", fontWeight: 700, fontFamily: "monospace", fontSize: 14 }}>
        ${payload[0].value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </p>
    </div>
  );
};

export function EquityChart({ data }: { data: Point[] }) {
  if (!data.length) {
    return (
      <div
        style={{
          height: 160,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--muted)",
          fontSize: 13,
          flexDirection: "column",
          gap: 6,
        }}
      >
        <p>Waiting for tick data…</p>
        <p style={{ fontSize: 11, opacity: 0.5 }}>Chart populates after the first agent cycle</p>
      </div>
    );
  }

  const values = data.map((d) => d.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.15 || 200;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.8 }}
    >
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="rgba(255,255,255,0.7)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="rgba(255,255,255,0.7)" stopOpacity={0}    />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" hide />
          <YAxis domain={[min - pad, max + pad]} hide />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="rgba(255,255,255,0.7)"
            strokeWidth={1.5}
            fill="url(#eqGrad)"
            dot={false}
            activeDot={{ r: 4, fill: "rgba(255,255,255,0.7)", stroke: "#000", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
