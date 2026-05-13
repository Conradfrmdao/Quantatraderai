"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";

interface MacroData {
  fear_greed?: { value: number; label: string; normalized: number; sentiment_bias: string };
  mtf?: Record<string, { overall_bias: string; alignment: number; strong_signal: boolean }>;
  news?: Record<string, { score: number; label: string; headlines: string[] }>;
  correlation?: string;
}

function FearGreedGauge({ value, label }: { value: number; label: string }) {
  const color = value <= 30 ? "#ef4444" : value >= 70 ? "#4ade80" : "#fbbf24";
  const pct   = value;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <p style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "rgba(255,255,255,0.3)" }}>
        Fear / Greed
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 80, height: 4, background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden", flexShrink: 0 }}>
          <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8 }}
            style={{ height: "100%", background: color, borderRadius: 2 }} />
        </div>
        <span style={{ fontSize: 12, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>{value}</span>
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>{label}</span>
      </div>
    </div>
  );
}

function MtfBias({ symbol, bias, alignment }: { symbol: string; bias: string; alignment: number }) {
  const color = bias === "bullish" ? "#4ade80" : bias === "bearish" ? "#ef4444" : "#fbbf24";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", fontWeight: 500 }}>{symbol}</span>
      <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 6,
        background: `${color}18`, color, border: `1px solid ${color}33`, textTransform: "capitalize" }}>
        {bias}
      </span>
      <span style={{ fontSize: 9, color: "rgba(255,255,255,0.25)" }}>{Math.round(alignment * 100)}%</span>
    </div>
  );
}

function NewsTag({ symbol, score, label }: { symbol: string; score: number; label: string }) {
  const color = score > 0.2 ? "#4ade80" : score < -0.2 ? "#ef4444" : "#fbbf24";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)" }}>{symbol}</span>
      <span style={{ fontSize: 10, fontWeight: 600, color }}>{label}</span>
    </div>
  );
}

export function MacroIntelStrip({ symbols }: { symbols?: string[] }) {
  const [data, setData]       = useState<MacroData | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const load = () =>
      fetch("/api/agent/intel/summary", { credentials: "same-origin" })
        .then(r => r.json())
        .then((d: MacroData) => setData(d))
        .catch(() => {});
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  if (!data || (!data.fear_greed && !data.mtf && !data.news)) {
    return (
      <div style={{ padding: "8px 16px", background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.05)", borderRadius: 12,
        fontSize: 11, color: "rgba(255,255,255,0.2)" }}>
        Market intelligence is warming up — data will appear shortly
      </div>
    );
  }

  const mtfEntries = Object.entries(data.mtf ?? {}).slice(0, 4);
  const newsEntries = Object.entries(data.news ?? {}).slice(0, 3);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 14, padding: "12px 16px",
      }}
    >
      {/* Collapsed: one-line summary */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ display: "flex", alignItems: "center", gap: 20, cursor: "pointer", flexWrap: "wrap" }}
      >
        <p style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
          letterSpacing: "0.1em", color: "rgba(255,255,255,0.3)", flexShrink: 0 }}>
          Macro Intel
        </p>

        {data.fear_greed && (
          <FearGreedGauge value={data.fear_greed.value} label={data.fear_greed.label} />
        )}

        {mtfEntries.length > 0 && (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {mtfEntries.map(([sym, mtf]) => (
              <MtfBias key={sym} symbol={sym} bias={mtf.overall_bias} alignment={mtf.alignment} />
            ))}
          </div>
        )}

        {newsEntries.length > 0 && (
          <div style={{ display: "flex", gap: 10 }}>
            {newsEntries.map(([sym, n]) => (
              <NewsTag key={sym} symbol={sym} score={n.score} label={n.label} />
            ))}
          </div>
        )}

        {data.correlation && (
          <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>{data.correlation}</span>
        )}

        <span style={{ marginLeft: "auto", fontSize: 10, color: "rgba(255,255,255,0.25)" }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded: headlines */}
      {expanded && newsEntries.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}
          style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <p style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.1em", color: "rgba(255,255,255,0.25)", marginBottom: 8 }}>Top headlines</p>
          {newsEntries.flatMap(([sym, n]) =>
            n.headlines.slice(0, 1).map((h, i) => (
              <p key={`${sym}-${i}`} style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", lineHeight: 1.5,
                marginBottom: 4, display: "flex", gap: 6 }}>
                <span style={{ color: "rgba(255,255,255,0.2)", flexShrink: 0 }}>{sym}</span>
                {h}
              </p>
            ))
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
