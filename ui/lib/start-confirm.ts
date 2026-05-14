export function getStartConfirmActionState(isLive: boolean, acked: boolean) {
  const accent = isLive ? "#ef4444" : "#4ade80";
  const muted = "rgba(255,255,255,0.25)";
  return {
    label: isLive ? "Start Live Agent" : "Start Paper Agent",
    eyebrow: isLive ? "Real execution" : "Simulated execution",
    subcopy: isLive ? "Uses connected venue funds" : "No real money at risk",
    accent,
    iconColor: acked ? "#050505" : muted,
    textColor: acked ? "#050505" : muted,
    background: acked
      ? `linear-gradient(135deg, ${accent} 0%, ${isLive ? "#fb7185" : "#86efac"} 100%)`
      : "rgba(255,255,255,0.045)",
    border: acked ? `1px solid ${accent}` : "1px solid rgba(255,255,255,0.08)",
    boxShadow: acked ? `0 16px 36px ${accent}2e` : "none",
  };
}
