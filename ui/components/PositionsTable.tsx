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

/** Detect FOREX symbols: 6-letter pairs like EURUSD, EUR_USD, GBP/JPY, XAUUSD */
function isForexSymbol(symbol: string): boolean {
  const clean = symbol.replace(/[/_\-]/g, "").toUpperCase();
  // 6-char alphabetic (most FX pairs), excluding crypto pairs that end in USDT/BTC/ETH
  if (!/^[A-Z]{6}$/.test(clean)) return false;
  if (clean.endsWith("USDT") || clean.endsWith("BUSD")) return false;
  return true;
}

/**
 * Format a price value appropriately for the instrument:
 * - FOREX: 5 decimal places, no $ prefix (prices are in rate terms, not USD)
 * - Crypto/stocks: 2 decimal places, $ prefix
 */
function fmtPrice(v: number | null | undefined, symbol: string): string {
  if (v == null || v === 0) return "—";
  if (isForexSymbol(symbol)) {
    // JPY pairs only need 3 decimal places; everything else 5
    const clean = symbol.replace(/[/_\-]/g, "").toUpperCase();
    const dp = clean.endsWith("JPY") ? 3 : 5;
    return v.toFixed(dp);
  }
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format position size:
 * - OANDA: quantity is in base-currency units (e.g. 463 units of EUR)
 * - MetaTrader: quantity is already in lots (e.g. 0.01)
 * - Crypto: raw amount
 * We detect by whether it's a FOREX symbol plus size magnitude.
 */
function fmtSize(quantity: number, symbol: string, venueType?: string): string {
  const abs = Math.abs(quantity);
  if (!isForexSymbol(symbol)) {
    return abs.toLocaleString("en-US", { maximumFractionDigits: 6 });
  }
  if (venueType === "METATRADER") {
    return `${abs.toFixed(2)} lots`;
  }
  // OANDA: quantity is in units; display both units and approximate lots
  if (abs >= 1000) {
    const lots = abs / 100_000;
    return `${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })} units${lots >= 0.01 ? ` (${lots.toFixed(2)}L)` : ""}`;
  }
  return `${abs} units`;
}

function leverageStr(lev: Position["leverage"]) {
  if (!lev) return "—";
  if (typeof lev === "number") {
    return isFinite(lev) && lev > 0 ? `${lev}×` : "—";
  }
  // Object form: { type: "ISOLATED" | "CROSS", value?: number }
  const val = (lev as { type: string; value?: number }).value;
  if (val == null || !isFinite(val)) {
    // CROSS margin has no fixed leverage scalar — show type label instead
    const t = (lev as { type: string }).type;
    return t ? t.charAt(0).toUpperCase() + t.slice(1).toLowerCase() : "—";
  }
  return `${val}×`;
}

export function PositionsTable({
  positions,
  isPaper,
  venueType,
}: {
  positions: Position[];
  isPaper?: boolean;
  venueType?: string;
}) {
  if (!positions.length) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          textAlign: "center",
          padding: "40px 20px",
          color: "var(--muted)",
          fontSize: 13,
        }}
      >
        {isPaper && (
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6,
            background: "rgba(74,222,128,0.06)", border: "1px solid rgba(74,222,128,0.15)",
            borderRadius: 8, padding: "4px 12px", marginBottom: 12, fontSize: 10,
            fontWeight: 700, color: "#4ade80", letterSpacing: "0.08em" }}>
            PAPER MODE
          </div>
        )}
        <p>{isPaper ? "No simulated positions yet" : "No open positions"}</p>
        <p style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>
          {isPaper
            ? "The AI will open paper trades when it detects a strong signal"
            : "Positions will appear here once the agent opens trades"}
        </p>
      </motion.div>
    );
  }

  // Check if any position is FOREX to decide whether to show the Liq. column
  const hasForex  = positions.some(p => isForexSymbol(p.symbol));
  const hasCrypto = positions.some(p => !isForexSymbol(p.symbol));
  const showLiq   = hasCrypto; // only show liquidation column when crypto is present

  return (
    <div style={{ overflowX: "auto" }}>
      {isPaper && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10,
          padding: "6px 12px", background: "rgba(74,222,128,0.05)",
          border: "1px solid rgba(74,222,128,0.15)", borderRadius: 8 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: "#4ade80",
            background: "rgba(74,222,128,0.12)", padding: "2px 6px", borderRadius: 4,
            letterSpacing: "0.08em" }}>PAPER</span>
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
            Simulated positions — no real money
          </span>
        </div>
      )}

      {/* FOREX context hint */}
      {hasForex && (
        <div style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", marginBottom: 8, paddingLeft: 4 }}>
          Prices in instrument rate · PnL in account currency (USD) · Spot FX has no liquidation price
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Size</th>
            <th>Entry</th>
            <th>Mark</th>
            {showLiq && <th>Liq.</th>}
            <th>Lev.</th>
            <th>uPnL</th>
          </tr>
        </thead>
        <tbody>
          <AnimatePresence>
            {positions.map((p, i) => {
              const long   = (p.quantity ?? 0) > 0;
              const pnl    = p.unrealized_pnl ?? 0;
              const isFx   = isForexSymbol(p.symbol);
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
                      <span style={{
                        fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                        background: long ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                        color: long ? "var(--green)" : "var(--red)",
                        letterSpacing: "0.06em", textTransform: "uppercase",
                        border: `1px solid ${long ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
                      }}>
                        {long ? "Long" : "Short"}
                      </span>
                      <strong style={{ fontSize: 13, color: "var(--text)" }}>
                        {/* Normalise display: EUR_USD → EUR/USD */}
                        {p.symbol.replace(/_/g, "/")}
                      </strong>
                      {isFx && (
                        <span style={{ fontSize: 9, color: "rgba(255,255,255,0.25)",
                          background: "rgba(255,255,255,0.04)", borderRadius: 4,
                          padding: "1px 5px", border: "1px solid rgba(255,255,255,0.08)" }}>
                          FX
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {fmtSize(p.quantity, p.symbol, venueType)}
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {fmtPrice(p.entry_price, p.symbol)}
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {fmtPrice(p.current_price, p.symbol)}
                  </td>
                  {showLiq && (
                    <td style={{ fontFamily: "monospace", fontSize: 12, color: "var(--yellow)" }}>
                      {isFx ? "—" : (p.liquidation_price ? `$${p.liquidation_price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—")}
                    </td>
                  )}
                  <td style={{ fontSize: 12 }}>
                    {isFx && !p.leverage ? "—" : leverageStr(p.leverage)}
                  </td>
                  <td style={{ fontFamily: "monospace", fontWeight: 600, fontSize: 12, color: pnlColor(pnl) }}>
                    {pnl >= 0 ? "+" : ""}${Math.abs(pnl).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
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
