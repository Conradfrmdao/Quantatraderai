import { useState, useEffect, useCallback } from "react";
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, RefreshControl } from "react-native";
import { useAuth, useSession } from "@clerk/clerk-expo";
import { useRouter } from "expo-router";

const API = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

interface AccountData { balance: number; equity: number; total_return_pct: number; open_positions: number; sharpe: number }
interface StatusData   { status: string; provider: string; model: string; assets: string[]; tick_count: number; uptime_seconds: number }

export default function DashboardScreen() {
  const { signOut }  = useAuth();
  const { session }  = useSession();
  const router       = useRouter();

  const [account,    setAccount]  = useState<AccountData | null>(null);
  const [status,     setStatus]   = useState<StatusData  | null>(null);
  const [refreshing, setRefresh]  = useState(false);
  const [toggling,   setToggling] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [acct, stat] = await Promise.all([
        fetch(`${API}/api/account`).then(r => r.json()),
        fetch(`${API}/api/status`).then(r => r.json()),
      ]);
      setAccount(acct);
      setStatus(stat);
    } catch {}
  }, []);

  useEffect(() => { fetchData(); const id = setInterval(fetchData, 8000); return () => clearInterval(id); }, [fetchData]);

  const onRefresh = async () => { setRefresh(true); await fetchData(); setRefresh(false); };

  const toggleAgent = async () => {
    const running = status?.status === "running";
    setToggling(true);
    try {
      const token = await session?.getToken();
      await fetch(`${API}/api/agent/${running ? "stop" : "start"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(running ? {} : { timeframe: "1h" }),
      });
      setTimeout(() => { fetchData(); setToggling(false); }, 1200);
    } catch { setToggling(false); }
  };

  const running = status?.status === "running";

  return (
    <ScrollView style={s.root} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.logo}>QuntaTradeAI</Text>
        <TouchableOpacity onPress={() => signOut().then(() => router.replace("/(auth)/sign-in"))}>
          <Text style={s.signOut}>Sign out</Text>
        </TouchableOpacity>
      </View>

      {/* Status badge */}
      <View style={[s.statusBadge, { backgroundColor: running ? "rgba(74,222,128,0.1)" : "rgba(255,255,255,0.05)" }]}>
        <View style={[s.dot, { backgroundColor: running ? "#4ade80" : "#555" }]} />
        <Text style={[s.statusTxt, { color: running ? "#4ade80" : "#777" }]}>
          {status?.status?.toUpperCase() ?? "CONNECTING…"}
        </Text>
        {status && <Text style={s.statusSub}>{status.provider} · {status.model?.split("-").slice(-2).join("-")}</Text>}
      </View>

      {/* Stat cards */}
      <View style={s.grid}>
        {[
          { label: "Portfolio Equity", value: account ? `$${account.equity.toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—" },
          { label: "Total Return",     value: account ? `${account.total_return_pct >= 0 ? "+" : ""}${account.total_return_pct.toFixed(2)}%` : "—", color: account && account.total_return_pct >= 0 ? "#4ade80" : "#f87171" },
          { label: "Open Positions",   value: String(account?.open_positions ?? "—") },
          { label: "Sharpe Ratio",     value: account ? account.sharpe.toFixed(3) : "—" },
        ].map(card => (
          <View key={card.label} style={s.card}>
            <Text style={s.cardLabel}>{card.label}</Text>
            <Text style={[s.cardValue, card.color ? { color: card.color } : {}]}>{card.value}</Text>
          </View>
        ))}
      </View>

      {/* Agent control */}
      <TouchableOpacity style={[s.agentBtn, { backgroundColor: running ? "rgba(239,68,68,0.12)" : "rgba(74,222,128,0.12)", borderColor: running ? "rgba(239,68,68,0.35)" : "rgba(74,222,128,0.35)" }]} onPress={toggleAgent} disabled={toggling}>
        <Text style={[s.agentBtnTxt, { color: running ? "#ef4444" : "#4ade80" }]}>
          {toggling ? "…" : running ? "⬛  Stop Agent" : "▶  Start Agent"}
        </Text>
      </TouchableOpacity>

      {/* Assets */}
      {status?.assets && (
        <View style={s.assets}>
          {status.assets.map(a => (
            <View key={a} style={s.assetTag}><Text style={s.assetTxt}>{a}</Text></View>
          ))}
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  root:       { flex: 1, backgroundColor: "#000" },
  header:     { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 20, paddingTop: 56 },
  logo:       { fontSize: 18, fontWeight: "700", color: "#fff" },
  signOut:    { fontSize: 12, color: "#555" },
  statusBadge:{ marginHorizontal: 16, borderRadius: 12, padding: 14, flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 18 },
  dot:        { width: 8, height: 8, borderRadius: 4 },
  statusTxt:  { fontSize: 12, fontWeight: "700", letterSpacing: 1 },
  statusSub:  { fontSize: 11, color: "#444", marginLeft: "auto" },
  grid:       { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 12, gap: 10, marginBottom: 18 },
  card:       { width: "47%", backgroundColor: "#111", borderRadius: 14, padding: 16, borderWidth: 1, borderColor: "#1f1f1f" },
  cardLabel:  { fontSize: 10, color: "#555", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 8 },
  cardValue:  { fontSize: 22, fontWeight: "500", color: "#fff", fontVariant: ["tabular-nums"] },
  agentBtn:   { marginHorizontal: 16, borderRadius: 14, padding: 18, alignItems: "center", borderWidth: 1, marginBottom: 16 },
  agentBtnTxt:{ fontSize: 15, fontWeight: "700" },
  assets:     { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 16, gap: 8 },
  assetTag:   { backgroundColor: "#111", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: "#1f1f1f" },
  assetTxt:   { fontSize: 12, color: "#888", fontWeight: "500" },
});
