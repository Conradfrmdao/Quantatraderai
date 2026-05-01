"use client";
import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Trash2, Zap } from "lucide-react";

interface StrategyRule {
  id:        string;
  condition: string;
  action:    string;
  symbol:    string | null;
  active:    boolean;
}

const EXAMPLES = [
  "buy BTC when RSI drops below 30",
  "sell ETH if MACD crosses below signal",
  "close SOL when price drops 5% from entry",
];

export function NLCommandBar() {
  const [text,    setText]    = useState("");
  const [rules,   setRules]   = useState<StrategyRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");
  const [open,    setOpen]    = useState(false);

  const loadRules = useCallback(() => {
    fetch("/api/strategies")
      .then(r => r.json())
      .then((d: { rules: StrategyRule[] }) => setRules(d.rules ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => { loadRules(); }, [loadRules]);

  const submit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res  = await fetch("/api/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json() as { error?: string };
      if (data.error) { setError(data.error); }
      else            { setText(""); loadRules(); }
    } catch { setError("Failed to parse rule"); }
    setLoading(false);
  };

  const deleteRule = async (id: string) => {
    await fetch(`/api/strategies?id=${id}`, { method: "DELETE" });
    setRules(r => r.filter(x => x.id !== id));
  };

  const ACTION_COLOR: Record<string, string> = {
    buy: "#4ade80", sell: "#ef4444", close: "#fbbf24",
  };

  return (
    <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 14 }}>
      {/* Header */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
      >
        <Zap size={13} style={{ color: "#fbbf24" }} />
        <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>Strategy Commands</span>
        {rules.length > 0 && (
          <span style={{ fontSize: 10, padding: "1px 8px", borderRadius: 20,
            background: "rgba(255,255,255,0.06)", color: "var(--muted)" }}>
            {rules.length} active
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 10, color: "rgba(255,255,255,0.25)" }}>
          {open ? "▲" : "▼"}
        </span>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{ padding: "0 16px 16px" }}>
              {/* Input row */}
              <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                <input
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && submit()}
                  placeholder='e.g. "buy BTC when RSI < 30"'
                  style={{
                    flex: 1, padding: "10px 14px", borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.1)",
                    background: "rgba(255,255,255,0.04)", color: "#fff",
                    fontSize: 13, outline: "none",
                  }}
                />
                <button
                  onClick={submit}
                  disabled={loading || !text.trim()}
                  style={{
                    padding: "10px 14px", borderRadius: 10,
                    background: loading ? "rgba(255,255,255,0.04)" : "rgba(255,255,255,0.1)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    color: "#fff", cursor: "pointer", display: "flex", alignItems: "center",
                    opacity: loading || !text.trim() ? 0.5 : 1,
                  }}
                >
                  <Send size={13} />
                </button>
              </div>

              {/* Error */}
              {error && <p style={{ fontSize: 11, color: "var(--red)", marginBottom: 8 }}>{error}</p>}

              {/* Examples */}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {EXAMPLES.map(ex => (
                  <button key={ex} onClick={() => setText(ex)} style={{
                    fontSize: 10, color: "rgba(255,255,255,0.35)",
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    borderRadius: 6, padding: "3px 8px", cursor: "pointer",
                  }}>
                    {ex}
                  </button>
                ))}
              </div>

              {/* Active rules */}
              {rules.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <p style={{ fontSize: 9, fontWeight: 600, textTransform: "uppercase",
                    letterSpacing: "0.1em", color: "rgba(255,255,255,0.25)", marginBottom: 4 }}>
                    Active rules
                  </p>
                  {rules.map(r => (
                    <div key={r.id} style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "8px 10px", borderRadius: 8,
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.06)",
                    }}>
                      <span style={{
                        fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                        background: `${ACTION_COLOR[r.action] ?? "#888"}18`,
                        color: ACTION_COLOR[r.action] ?? "#888",
                        border: `1px solid ${ACTION_COLOR[r.action] ?? "#888"}33`,
                        textTransform: "uppercase", flexShrink: 0,
                      }}>
                        {r.action}
                      </span>
                      <span style={{ flex: 1, fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
                        {r.condition}
                      </span>
                      {r.symbol && (
                        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", flexShrink: 0 }}>
                          {r.symbol}
                        </span>
                      )}
                      <button onClick={() => deleteRule(r.id)} style={{
                        background: "none", border: "none", color: "rgba(255,255,255,0.2)",
                        cursor: "pointer", padding: 4, display: "flex",
                      }}>
                        <Trash2 size={11} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {rules.length === 0 && (
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", textAlign: "center", padding: "8px 0" }}>
                  No active rules — type a command above
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
