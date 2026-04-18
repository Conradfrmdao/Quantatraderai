"use client";

interface Decision {
  ts?: string;
  asset?: string;
  action?: string;
  reasoning?: string;
  trade_decisions?: Array<{
    asset: string;
    action: string;
    rationale?: string;
    allocation_usd?: number;
    tp_price?: number;
    sl_price?: number;
  }>;
}

const actionColor: Record<string, string> = {
  buy: "var(--green)",
  sell: "var(--red)",
  hold: "var(--muted)",
};
const actionBg: Record<string, string> = {
  buy: "rgba(16,185,129,0.12)",
  sell: "rgba(244,63,94,0.12)",
  hold: "rgba(100,116,139,0.12)",
};

export function DecisionsFeed({ decisions }: { decisions: Decision[] }) {
  const flat = decisions.flatMap((d) =>
    (d.trade_decisions ?? []).map((td) => ({
      ts: d.ts,
      ...td,
    }))
  ).reverse();

  if (!flat.length) {
    return (
      <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)", fontSize: 13 }}>
        No decisions yet — agent hasn't run a full tick
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {flat.slice(0, 12).map((d, i) => {
        const action = (d.action ?? "hold").toLowerCase();
        return (
          <div
            key={i}
            className="fade-in"
            style={{
              padding: "12px 14px",
              borderRadius: 10,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              display: "flex",
              gap: 12,
              alignItems: "flex-start",
            }}
          >
            {/* Action badge */}
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                padding: "3px 8px",
                borderRadius: 6,
                background: actionBg[action] ?? actionBg.hold,
                color: actionColor[action] ?? "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                flexShrink: 0,
                marginTop: 1,
              }}
            >
              {action}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, gap: 8 }}>
                <strong style={{ fontSize: 13 }}>{d.asset}</strong>
                <span style={{ fontSize: 11, color: "var(--muted)", flexShrink: 0 }}>
                  {d.ts ? new Date(d.ts).toLocaleTimeString() : ""}
                </span>
              </div>
              {d.rationale && (
                <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                  {d.rationale}
                </p>
              )}
              {(d.tp_price || d.sl_price) && (
                <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                  {d.tp_price && <span style={{ fontSize: 11, color: "var(--green)" }}>TP ${d.tp_price.toLocaleString()}</span>}
                  {d.sl_price && <span style={{ fontSize: 11, color: "var(--red)" }}>SL ${d.sl_price.toLocaleString()}</span>}
                  {d.allocation_usd != null && d.allocation_usd > 0 && (
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>${d.allocation_usd.toLocaleString()}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
