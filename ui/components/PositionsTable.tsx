"use client";
import { motion, AnimatePresence } from "framer-motion";

interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  leverage?: { type: string; value: number } | number;
  liquidation_price?: number;
}

function pnlColor(v: number) {
  return v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--muted)";
}

function fmt(v: number | null | undefined, dp = 2) {
  if (v == null) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function leverageStr(lev: Position["leverage"]) {
  if (!lev) return "—";
  if (typeof lev === "number") return `${lev}×`;
  return `${lev.value}×`;
}

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          textAlign: "center",
          padding: "48px 20px",
          color: "var(--muted)",
          fontSize: 13,
        }}
      >
        <p>No open positions</p>
        <p style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>
          Positions will appear here once the agent opens trades
        </p>
      </motion.div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Size</th>
            <th>Entry</th>
            <th>Mark</th>
            <th>Liq.</th>
            <th>Lev.</th>
            <th>uPnL</th>
          </tr>
        </thead>
        <tbody>
          <AnimatePresence>
            {positions.map((p, i) => {
              const long = (p.quantity ?? 0) > 0;
              const pnl = p.unrealized_pnl ?? 0;
              return (
                <motion.tr
                  key={p.symbol}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          padding: "2px 7px",
                          borderRadius: 6,
                          background: long
                            ? "rgba(34,197,94,0.1)"
                            : "rgba(239,68,68,0.1)",
                          color: long ? "var(--green)" : "var(--red)",
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                          border: `1px solid ${long ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
                        }}
                      >
                        {long ? "Long" : "Short"}
                      </span>
                      <strong style={{ fontSize: 13, color: "var(--text)" }}>{p.symbol}</strong>
                    </div>
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>{Math.abs(p.quantity)}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>${fmt(p.entry_price)}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>${fmt(p.current_price)}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 12, color: "var(--yellow)" }}>
                    {p.liquidation_price ? `$${fmt(p.liquidation_price)}` : "—"}
                  </td>
                  <td style={{ fontSize: 12 }}>{leverageStr(p.leverage)}</td>
                  <td
                    style={{
                      fontFamily: "monospace",
                      fontWeight: 600,
                      fontSize: 12,
                      color: pnlColor(pnl),
                    }}
                  >
                    {pnl >= 0 ? "+" : ""}${fmt(pnl, 4)}
                  </td>
                </motion.tr>
              );
            })}
          </AnimatePresence>
        </tbody>
      </table>
    </div>
  );
}
