"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Download, Filter } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

interface Trade {
  id: string;
  symbol: string;
  action: string;
  quantity: number;
  price: number;
  allocationUsd: number;
  pnl: number;
  source: string;
  rationale: string | null;
  tpPrice: number | null;
  slPrice: number | null;
  createdAt: string;
}

const inputStyle: React.CSSProperties = {
  padding: "8px 12px", borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)",
  color: "#fff", fontSize: 12, outline: "none",
};

function csvLine(t: Trade) {
  const fields = [
    new Date(t.createdAt).toISOString(),
    t.symbol, t.action.toUpperCase(),
    t.quantity.toFixed(8), t.price.toFixed(4),
    t.allocationUsd.toFixed(2), t.pnl.toFixed(2),
    t.source, t.slPrice ?? "", t.tpPrice ?? "",
    (t.rationale ?? "").replace(/,/g, ";"),
  ];
  return fields.join(",");
}

function exportCsv(trades: Trade[]) {
  const header = "Date,Symbol,Action,Quantity,Price,Allocation($),PnL($),Source,SL,TP,Rationale";
  const rows   = trades.map(csvLine);
  const blob   = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
  const url    = URL.createObjectURL(blob);
  const a      = document.createElement("a");
  a.href = url; a.download = `qunta_trades_${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(url);
}

export default function JournalPage() {
  const isMobile = useIsMobile();

  const [trades, setTrades]   = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol,  setSymbol]  = useState("");
  const [action,  setAction]  = useState("");
  const [from,    setFrom]    = useState("");
  const [to,      setTo]      = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ limit: "500" });
    if (symbol) params.set("symbol", symbol);
    if (action) params.set("action", action);
    if (from)   params.set("from", from);
    if (to)     params.set("to", to);
    const res = await fetch(`/api/trades?${params}`).catch(() => null);
    if (res?.ok) {
      const data = await res.json() as { trades: Trade[] };
      setTrades(data.trades ?? []);
    }
    setLoading(false);
  }, [symbol, action, from, to]);

  useEffect(() => { load(); }, [load]);

  const totalPnl   = trades.reduce((s, t) => s + t.pnl, 0);
  const winners    = trades.filter(t => t.pnl > 0).length;
  const winRate    = trades.length ? ((winners / trades.length) * 100).toFixed(1) : "—";

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <header style={{
        padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex",
        alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex", alignItems: "center" }}>
          <ArrowLeft size={16} />
        </Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Trade Journal</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            onClick={() => exportCsv(trades)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8, padding: "6px 12px", color: "rgba(255,255,255,0.6)",
              fontSize: 12, cursor: "pointer",
            }}
          >
            <Download size={12} /> Export CSV
          </button>
        </div>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 1300, margin: "0 auto" }}>

        {/* Summary */}
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          {[
            { label: "Total trades", value: trades.length.toString() },
            { label: "Realised PnL", value: `${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`, color: totalPnl >= 0 ? "var(--green)" : "var(--red)" },
            { label: "Win rate", value: `${winRate}%` },
            { label: "Winners", value: winners.toString() },
          ].map(m => (
            <div key={m.label} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 12, padding: "14px 18px", minWidth: 120 }}>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{m.label}</p>
              <p style={{ fontSize: 20, fontWeight: 500, color: m.color ?? "#fff", fontVariantNumeric: "tabular-nums" }}>{m.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20, alignItems: "center" }}>
          <Filter size={13} style={{ color: "var(--muted)" }} />
          <input style={inputStyle} placeholder="Symbol (e.g. BTC/USDT)" value={symbol} onChange={e => setSymbol(e.target.value)} />
          <select style={{ ...inputStyle, appearance: "none" }} value={action} onChange={e => setAction(e.target.value)}>
            <option value="">All actions</option>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
            <option value="close">Close</option>
          </select>
          <input style={inputStyle} type="date" value={from} onChange={e => setFrom(e.target.value)} />
          <input style={inputStyle} type="date" value={to}   onChange={e => setTo(e.target.value)}   />
          <button onClick={load} style={{ ...inputStyle, cursor: "pointer", background: "rgba(255,255,255,0.08)", whiteSpace: "nowrap" }}>Apply</button>
        </div>

        {/* Table */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Date","Symbol","Action","Qty","Price","Alloc ($)","PnL ($)","Source","SL / TP"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "10px 12px", fontSize: 10, color: "var(--muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>Loading…</td></tr>
              ) : trades.length === 0 ? (
                <tr><td colSpan={9} style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>No trades yet</td></tr>
              ) : trades.map(t => (
                <tr key={t.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.45)", whiteSpace: "nowrap" }}>
                    {new Date(t.createdAt).toLocaleDateString()} {new Date(t.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td style={{ padding: "10px 12px", color: "#fff", fontWeight: 500 }}>{t.symbol}</td>
                  <td style={{ padding: "10px 12px" }}>
                    <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 600, background: t.action === "buy" ? "var(--green-dim)" : "var(--red-dim)", color: t.action === "buy" ? "var(--green)" : "var(--red)" }}>
                      {t.action.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.7)", fontVariantNumeric: "tabular-nums" }}>{t.quantity.toFixed(6)}</td>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.7)", fontVariantNumeric: "tabular-nums" }}>${t.price.toFixed(4)}</td>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.7)", fontVariantNumeric: "tabular-nums" }}>${t.allocationUsd.toFixed(2)}</td>
                  <td style={{ padding: "10px 12px", fontWeight: 500, fontVariantNumeric: "tabular-nums", color: t.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                    {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                  </td>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.4)", fontSize: 10 }}>{t.source}</td>
                  <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.4)", fontSize: 11 }}>
                    {t.slPrice ? `SL ${t.slPrice}` : "—"} {t.tpPrice ? `/ TP ${t.tpPrice}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      </main>
    </div>
  );
}
