"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Shield, Download } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";

interface AuditEntry {
  id: string; event: string; symbol: string | null;
  action: string | null; data: string; createdAt: string;
}

const EVENT_COLOR: Record<string, string> = {
  decision:        "rgba(255,255,255,0.5)",
  order:           "#4ade80",
  risk_block:      "#ef4444",
  agent_start:     "#4ade80",
  agent_stop:      "#f87171",
  kill_switch:     "#ef4444",
  circuit_breaker: "#fbbf24",
};

function escapeCsvField(value: string): string {
  if (value.includes('"') || value.includes(",") || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function exportCsv(logs: AuditEntry[]) {
  const header = "Date,Event,Symbol,Action,Data";
  const rows = logs.map(l => {
    let dataStr = "";
    try { dataStr = JSON.stringify(JSON.parse(l.data || "{}")); } catch { dataStr = l.data ?? ""; }
    return [
      new Date(l.createdAt).toISOString(),
      l.event,
      l.symbol ?? "",
      l.action ?? "",
      escapeCsvField(dataStr),
    ].join(",");
  });
  const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a"); a.href = url;
  a.download = `quantatrader_audit_${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(url);
}

const PAGE_SIZE = 50;

export default function AuditPage() {
  const isMobile                = useIsMobile();
  const [logs, setLogs]         = useState<AuditEntry[]>([]);
  const [loading, setLoading]   = useState(true);
  const [filter, setFilter]     = useState("");
  const [page, setPage]         = useState(0);
  const [hasMore, setHasMore]   = useState(true);
  const [eventFilter, setEventFilter] = useState("");

  const load = useCallback((p: number) => {
    setLoading(true);
    const skip = p * PAGE_SIZE;
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      skip:  String(skip),
      ...(eventFilter ? { event: eventFilter } : {}),
    });
    fetch(`/api/audit?${params}`)
      .then(r => r.json())
      .then((d: { logs: AuditEntry[] }) => {
        const newLogs = d.logs ?? [];
        setLogs(prev => p === 0 ? newLogs : [...prev, ...newLogs]);
        setHasMore(newLogs.length === PAGE_SIZE);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [eventFilter]);

  useEffect(() => { setPage(0); load(0); }, [load]);

  const filtered = filter
    ? logs.filter(l => l.event.includes(filter) || (l.symbol ?? "").includes(filter) || (l.action ?? "").includes(filter))
    : logs;

  return (
    <div className="dvh-min" style={{ background: "var(--bg)" }}>
      <header style={{ padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50 }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex" }}><ArrowLeft size={16} /></Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Audit Trail</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button onClick={() => exportCsv(filtered)} style={{ display: "flex", alignItems: "center", gap: 6,
            padding: "6px 12px", borderRadius: 8, fontSize: 12, cursor: "pointer",
            background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "var(--muted)" }}>
            <Download size={12} /> Export
          </button>
        </div>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 1000, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <Shield size={18} style={{ color: "#4ade80" }} />
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "#fff" }}>Audit Trail</h1>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>immutable · append-only</span>
        </div>

        <div style={{ marginBottom: 18, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {/* Event-type dropdown: server-side reload with pagination reset */}
          <select
            value={eventFilter}
            onChange={e => { setEventFilter(e.target.value); setPage(0); setLogs([]); }}
            style={{
              padding: "8px 12px", borderRadius: 8, fontSize: 12,
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
              color: "#fff", outline: "none", appearance: "none" }}>
            <option value="">All events</option>
            {["decision","order","risk_block","agent_start","agent_stop","kill_switch","force_close"].map(e => (
              <option key={e} value={e}>{e.replace(/_/g, " ")}</option>
            ))}
          </select>
          {/* Free-text search over loaded rows */}
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Search symbol / action…"
            style={{
              padding: "8px 12px", borderRadius: 8, fontSize: 12,
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
              color: "#fff", outline: "none", minWidth: 180 }} />
        </div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Date","Event","Symbol","Action","Data"].map(h => (
                  <th key={h} style={{ textAlign: "left", padding: "10px 12px", fontSize: 10,
                    color: "var(--muted)", fontWeight: 500, textTransform: "uppercase",
                    letterSpacing: "0.08em", borderBottom: "1px solid rgba(255,255,255,0.07)",
                    whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>Loading…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: 24, color: "var(--muted)", textAlign: "center" }}>No audit events yet</td></tr>
              ) : filtered.map(l => {
                let parsed: Record<string, unknown> = {};
                try { parsed = JSON.parse(l.data); } catch {}
                return (
                  <tr key={l.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.4)", whiteSpace: "nowrap" }}>
                      {new Date(l.createdAt).toLocaleString()}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 6, fontSize: 10, fontWeight: 600,
                        background: `${EVENT_COLOR[l.event] ?? "#888"}18`,
                        color: EVENT_COLOR[l.event] ?? "#888",
                        border: `1px solid ${EVENT_COLOR[l.event] ?? "#888"}33`,
                        textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        {l.event}
                      </span>
                    </td>
                    <td style={{ padding: "10px 12px", color: "#fff", fontWeight: 500 }}>{l.symbol ?? "—"}</td>
                    <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.6)" }}>{l.action ?? "—"}</td>
                    <td style={{ padding: "10px 12px", color: "rgba(255,255,255,0.3)", fontSize: 10,
                      maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {Object.keys(parsed).slice(0,3).map(k => `${k}:${String(parsed[k]).slice(0,20)}`).join(" · ")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Load More */}
          {hasMore && (
            <div style={{ textAlign: "center", marginTop: 20, paddingBottom: 8 }}>
              <button
                onClick={() => { const next = page + 1; setPage(next); load(next); }}
                disabled={loading}
                style={{
                  padding: "10px 28px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                  background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
                  color: "#fff", cursor: loading ? "default" : "pointer", opacity: loading ? 0.6 : 1,
                }}>
                {loading ? "Loading…" : "Load more events"}
              </button>
            </div>
          )}

          {!hasMore && filtered.length > 0 && (
            <p style={{ textAlign: "center", fontSize: 11, color: "rgba(255,255,255,0.2)", marginTop: 16 }}>
              All {filtered.length} events loaded
            </p>
          )}
        </motion.div>
      </main>
    </div>
  );
}
