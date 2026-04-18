"use client";

interface StatusData {
  status?: string;
  provider?: string;
  model?: string;
  venue?: string;
  tick_count?: number;
  uptime_seconds?: number;
  assets?: string[];
}

function fmt_uptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function StatusBar({ data }: { data: StatusData | null }) {
  const running = data?.status === "running";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        padding: "10px 20px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        flexWrap: "wrap",
      }}
    >
      {/* Live indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <span
          className={running ? "pulse" : ""}
          style={{
            width: 8, height: 8, borderRadius: "50%",
            background: running ? "var(--green)" : "var(--muted)",
            display: "inline-block",
            boxShadow: running ? "0 0 8px var(--green-glow)" : undefined,
          }}
        />
        <span style={{ fontSize: 12, fontWeight: 600, color: running ? "var(--green)" : "var(--muted)" }}>
          {running ? "LIVE" : "OFFLINE"}
        </span>
      </div>

      <Chip label="Venue" value={data?.venue ?? "—"} />
      <Chip label="Provider" value={data?.provider ?? "—"} />
      <Chip label="Model" value={data?.model ? data.model.replace("llama-", "").replace("-versatile","").replace("-instruct","") : "—"} />
      <Chip label="Assets" value={data?.assets?.join(", ") ?? "—"} />
      <Chip label="Ticks" value={data?.tick_count?.toString() ?? "0"} />
      {data?.uptime_seconds !== undefined && (
        <Chip label="Uptime" value={fmt_uptime(data.uptime_seconds)} />
      )}
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
      <span style={{ fontSize: 12, color: "var(--text)", fontWeight: 500 }}>{value}</span>
    </div>
  );
}
