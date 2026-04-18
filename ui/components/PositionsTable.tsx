"use client";

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
  if (typeof lev === "number") return `${lev}x`;
  return `${lev.value}x`;
}

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return (
      <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)", fontSize: 13 }}>
        No open positions
      </div>
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
          {positions.map((p) => {
            const long = (p.quantity ?? 0) > 0;
            const pnl = p.unrealized_pnl ?? 0;
            return (
              <tr key={p.symbol}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        fontSize: 9,
                        fontWeight: 700,
                        padding: "2px 6px",
                        borderRadius: 4,
                        background: long ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)",
                        color: long ? "var(--green)" : "var(--red)",
                        letterSpacing: "0.05em",
                      }}
                    >
                      {long ? "LONG" : "SHORT"}
                    </span>
                    <strong style={{ fontSize: 13 }}>{p.symbol}</strong>
                  </div>
                </td>
                <td style={{ fontFamily: "monospace" }}>{Math.abs(p.quantity)}</td>
                <td style={{ fontFamily: "monospace" }}>${fmt(p.entry_price)}</td>
                <td style={{ fontFamily: "monospace" }}>${fmt(p.current_price)}</td>
                <td style={{ fontFamily: "monospace", color: "var(--yellow)" }}>{p.liquidation_price ? `$${fmt(p.liquidation_price)}` : "—"}</td>
                <td>{leverageStr(p.leverage)}</td>
                <td style={{ fontFamily: "monospace", fontWeight: 600, color: pnlColor(pnl) }}>
                  {pnl >= 0 ? "+" : ""}${fmt(pnl, 4)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
