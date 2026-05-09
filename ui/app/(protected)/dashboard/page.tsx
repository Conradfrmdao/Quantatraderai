"use client";
import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { UserButton, useSession } from "@clerk/nextjs";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import {
  TrendingUp, TrendingDown, Activity, Layers, Shield, RefreshCw, Settings,
  Play, Square, Wifi, WifiOff, Zap, BookOpen, BarChart2, Copy, ShoppingBag,
  Brain, FileText, Calendar,
} from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useWebSocket } from "@/hooks/useWebSocket";
import { StatCard }          from "@/components/StatCard";
import { StatusBar }         from "@/components/StatusBar";
import { PositionsTable }    from "@/components/PositionsTable";
import { DecisionsFeed }          from "@/components/DecisionsFeed";
import { DecisionTimeline }       from "@/components/DecisionTimeline";
import { GettingStartedChecklist } from "@/components/GettingStartedChecklist";
import { StartConfirmModal, type StartConfig } from "@/components/StartConfirmModal";
import { FirstTradeReaction } from "@/components/FirstTradeReaction";
import { RiskPanel }         from "@/components/RiskPanel";
import { EquityChart }       from "@/components/EquityChart";
import { LogoWordmark }      from "@/components/Logo";
import { MacroIntelStrip }   from "@/components/MacroIntelStrip";
import { NLCommandBar }      from "@/components/NLCommandBar";
import { ErrorBoundary }     from "@/components/ErrorBoundary";
import { useVenues, VENUE_SYMBOLS, VENUE_REGISTRY_NAME, VENUE_LABEL } from "@/hooks/useVenues";
import { useToast }            from "@/components/Toast";
import { DarkSelect }          from "@/components/ui/dark-select";
import { MarketPicker, MARKET_VENUE_TYPE } from "@/components/MarketPicker";
import { MobileBottomNav }    from "@/components/MobileBottomNav";

const TradingChart = dynamic(
  () => import("@/components/TradingChart").then((m) => m.TradingChart),
  { ssr: false, loading: () => <div style={{ height: 300, background: "rgba(255,255,255,0.02)", borderRadius: 8 }} /> },
);

const API    = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL  || "ws://localhost:8000";

/**
 * SECURITY: usePolled clears state when sessionKey changes (user sign-out / switch),
 * never displays previous user's data on shared devices.
 */
function usePolled<T>(path: string, interval = 8000, sessionKey?: string | null) {
  const [data, setData] = useState<T | null>(null);
  const proxyPath = path.startsWith("/api/")
    ? `/api/agent/${path.replace(/^\/api\//, "")}`
    : path;
  const fetch_ = useCallback(() => {
    if (!sessionKey) return; // do not fetch when unauthenticated
    fetch(proxyPath, { credentials: "same-origin" })
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, [proxyPath, sessionKey]);

  // Clear data immediately when user changes / signs out
  useEffect(() => { setData(null); }, [sessionKey]);

  useEffect(() => {
    if (!sessionKey) return;
    fetch_();
    const id = setInterval(fetch_, interval);
    return () => clearInterval(id);
  }, [fetch_, interval, sessionKey]);
  return { data, refresh: fetch_, set: setData };
}

interface AccountData   { balance: number; equity: number; initial_equity: number; total_return_pct: number; open_positions: number; sharpe: number }
interface PositionsData { positions: { symbol: string; quantity: number; entry_price: number; current_price: number; unrealized_pnl: number; leverage?: number; liquidation_price?: number }[]; is_paper?: boolean }
interface StatusData    { status: string; provider: string; model: string; venue: string; tick_count: number; uptime_seconds: number; assets: string[]; timeframe?: string; is_paper?: boolean; last_tick_ago_s?: number | null; next_tick_in_s?: number | null; tick_interval_s?: number; strategy_type?: string | null; latest_log?: { ts: string; msg: string } | null; daily_trade_count?: number }
interface RiskData      { max_position_pct: string; max_leverage: string; mandatory_sl_pct: string; max_loss_per_position_pct: string; daily_loss_circuit_breaker_pct: string; max_total_exposure_pct: string; max_concurrent_positions: string }
interface DecisionsData { decisions: { ts: string; trade_decisions: { asset: string; action: string; rationale: string; tp_price: number; sl_price: number; allocation_usd: number; confidence?: number; deadlock?: boolean }[] }[] }

export default function Dashboard() {
  // SECURITY: every piece of state is keyed off Clerk session ID.
  // When the user signs out / switches accounts, every cached datum is wiped.
  const { session } = useSession();
  const sessionKey  = session?.id ?? null;

  const account   = usePolled<AccountData>  ("/api/account",   8000,  sessionKey);
  const positions = usePolled<PositionsData>("/api/positions", 8000,  sessionKey);
  const status    = usePolled<StatusData>   ("/api/status",    5000, sessionKey);
  const risk      = usePolled<RiskData>     ("/api/risk",     60000, sessionKey);
  const decisions = usePolled<DecisionsData>("/api/decisions",10000, sessionKey);

  const [refreshing, setRefreshing]       = useState(false);
  const [agentLoading, setAgentLoading]   = useState(false);
  const [killConfirm, setKillConfirm]     = useState(false);
  const [livePrice, setLivePrice]         = useState<number | null>(null);
  const [strategyType, setStrategyType]     = useState<string>("MOMENTUM_HUNTER");
  const [timeframe, setTimeframe]           = useState<string>("5m");
  const [market, setMarket]                 = useState<string>("spot");
  const [paperCapital, setPaperCapital]     = useState<number>(10000);
  const [showGuards, setShowGuards]         = useState(false);
  const [minConfidence, setMinConfidence]   = useState(0);    // 0-100
  const [maxDailyLoss, setMaxDailyLoss]     = useState(0);    // 0-100 %
  const [maxTradesDay, setMaxTradesDay]     = useState(0);    // 0 = no limit
  const [lossCooldown, setLossCooldown]     = useState(0);    // 0 = no cooldown
  const [showStartConfirm, setShowStartConfirm] = useState(false);

  // Venue + symbol (driven by user's configured venues)
  const { venues: userVenues, loading: venuesLoading, reload: reloadVenues } = useVenues();
  const activeVenue  = userVenues.find(v => v.isActive) ?? userVenues[0];
  const venueType    = activeVenue?.type ?? "BINANCE";
  const venueSymbols = VENUE_SYMBOLS[venueType] ?? VENUE_SYMBOLS.BINANCE;
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [chartVenueType, setChartVenueType] = useState("BINANCE");

  // When the active venue changes (or loads for the first time), sync the default
  // symbol and chart venue type so a FOREX user sees EUR/USD not BTC/USDT.
  useEffect(() => {
    if (!venuesLoading && activeVenue) {
      const defaultSym = VENUE_SYMBOLS[venueType]?.[0] ?? "BTCUSDT";
      setSymbol(defaultSym);
      setChartVenueType(venueType);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [venueType, venuesLoading]);

  const isForexVenue = venueType === "OANDA" || venueType === "METATRADER";

  const toast = useToast();

  // Reset derived UI state immediately on user switch / sign-out
  useEffect(() => {
    setLivePrice(null);
    setKillConfirm(false);
    setAgentLoading(false);
  }, [sessionKey]);

  // Pass Clerk session token to WebSocket for JWT auth
  const getToken = useCallback(
    () => (session ? session.getToken() : Promise.resolve(null)),
    [session],
  );

  const { connected, lastEvent } = useWebSocket(`${WS_URL}/ws`, getToken);
  const { handleWsEvent, requestPermission } = usePushNotifications(true);

  // Request notification permission once on mount
  useEffect(() => { requestPermission(); }, [requestPermission]);

  // handle WebSocket events
  useEffect(() => {
    if (!lastEvent) return;
    handleWsEvent(lastEvent as Parameters<typeof handleWsEvent>[0]);
    if (lastEvent.type === "price_update") {
      const ev = lastEvent as { type: string; symbol: string; price: number };
      if (ev.symbol?.toUpperCase() === symbol.toUpperCase()) setLivePrice(ev.price);
    }
    if (lastEvent.type === "account_update") {
      const ev = lastEvent as { type: string; data?: AccountData };
      if (ev.data) account.set(ev.data);
    }
    if (lastEvent.type === "positions_update") {
      const ev = lastEvent as { type: string; data?: PositionsData };
      if (ev.data) positions.set(ev.data);
    }
    if (lastEvent.type === "decision" || lastEvent.type === "decisions_update") {
      decisions.refresh();
    }
    if (lastEvent.type === "trade_executed") {
      positions.refresh();
      account.refresh();
    }
    if (lastEvent.type === "status_update") {
      status.refresh();
    }
  }, [lastEvent, symbol]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    account.refresh(); positions.refresh(); status.refresh(); decisions.refresh(); risk.refresh();
    setTimeout(() => setRefreshing(false), 1000);
  }, [account, positions, status, decisions, risk]);

  // Actual start — called after the safety gate is confirmed
  const doStartAgent = useCallback(async () => {
    setShowStartConfirm(false);
    setAgentLoading(true);
    try {
      const venueName = VENUE_REGISTRY_NAME[venueType] ?? "binance";
      const body = {
        venue:            venueName,
        symbols:          [symbol],
        timeframe:        timeframe,
        market:           market,
        isPaper:          activeVenue?.isPaper ?? true,
        strategyType:     strategyType,
        minConfidencePct: minConfidence,
        maxDailyLossPct:  maxDailyLoss,
        maxTradesPerDay:  maxTradesDay,
        lossCooldownCount: lossCooldown,
        paperCapital:     paperCapital,
      };
      const res = await fetch("/api/agent/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = (err as { error?: string }).error ?? `Failed (HTTP ${res.status})`;
        toast(msg, res.status === 402 ? "warning" : "error");
      } else {
        const data = await res.json().catch(() => ({})) as { warning?: string };
        toast(`Agent started on ${VENUE_LABEL[venueType] ?? venueType}`, "success");
        if (data.warning) toast(data.warning, "warning");
      }
      setTimeout(() => { status.refresh(); setAgentLoading(false); }, 1200);
    } catch (err) {
      setAgentLoading(false);
      toast("Failed to reach the trading backend. Check your connection.", "error");
    }
  }, [symbol, venueType, activeVenue, strategyType, minConfidence, maxDailyLoss,
      maxTradesDay, lossCooldown, status, toast]);

  const handleAgentToggle = useCallback(async () => {
    const running = status.data?.status === "running";
    if (running) {
      // Stopping — no gate needed
      setAgentLoading(true);
      try {
        const res = await fetch("/api/agent/stop", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          toast((err as { error?: string }).error ?? `Failed (HTTP ${res.status})`, "error");
        }
        setTimeout(() => { status.refresh(); setAgentLoading(false); }, 1200);
      } catch { setAgentLoading(false); }
    } else {
      // Starting — show safety gate first
      setShowStartConfirm(true);
    }
  }, [status, toast]);

  const handleKillSwitch = useCallback(async () => {
    if (!killConfirm) {
      setKillConfirm(true);
      setTimeout(() => setKillConfirm(false), 5000);
      return;
    }
    setKillConfirm(false);
    setAgentLoading(true);
    try {
      const res = await fetch("/api/agent/killswitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, ts: Date.now() / 1000 }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast((err as { error?: string }).error ?? "Kill switch failed", "error");
      } else {
        toast("All positions closed. Agent stopped.", "success");
      }
      setTimeout(() => { status.refresh(); positions.refresh(); setAgentLoading(false); }, 1200);
    } catch { setAgentLoading(false); }
  }, [killConfirm, status, positions, toast]);

  const [equityHistory, setEquityHistory] = useState<{ t: string; equity: number }[]>([]);
  // SECURITY: clear history immediately on user switch (no leakage between users)
  useEffect(() => { setEquityHistory([]); }, [sessionKey]);
  useEffect(() => {
    if (!account.data?.equity) return;
    setEquityHistory((prev) => {
      const point = { t: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), equity: account.data?.equity ?? 0 };
      return [...prev, point].slice(-40);
    });
  }, [decisions.data, account.data]);

  // Plan badge — refetched per session (no cross-user leakage)
  const [currentPlan, setCurrentPlan] = useState<string>("FREE");
  useEffect(() => {
    setCurrentPlan("FREE"); // reset on user change
    if (!sessionKey) return;
    fetch("/api/billing", { credentials: "same-origin", cache: "no-store" })
      .then(r => r.json())
      .then((d: { plan?: string }) => { if (d.plan) setCurrentPlan(d.plan); })
      .catch(() => {});
  }, [sessionKey]);

  const isMobile = useIsMobile();

  const PERSONA_DISPLAY: Record<string, { name: string; tagline: string }> = {
    MOMENTUM_HUNTER: { name: "Momentum Hunter", tagline: "Ride the wave — catch strong trends early" },
    SCALPER_AI:      { name: "Scalper AI",       tagline: "Fast in/out on short-term signals" },
    SWING_MASTER:    { name: "Swing Master",      tagline: "1-3 day holds with macro confluence" },
    NEWS_REACTOR:    { name: "News Reactor",      tagline: "Sentiment-driven, reacts to economic events" },
  };

  const acc      = account.data;
  const pos      = positions.data?.positions ?? [];
  const totalPnL = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const isUp     = (acc?.total_return_pct ?? 0) >= 0;
  const running  = status.data?.status === "running";

  // Normalise both sides: strip slashes and uppercase so "BTC/USDT", "BTCUSDT", "BTC" all match.
  const _normSym = (s: string) => s.toUpperCase().replace(/[/\-_]/g, "");
  const displayPrice = livePrice ?? pos.find((p) => _normSym(p.symbol) === _normSym(symbol))?.current_price;

  // M3: Backend connectivity check — banner shown if Python is unreachable
  // After the first poll completes, status.data should be populated. If it's still null
  // 15s after mount, we infer the backend is down.
  const [backendDown, setBackendDown] = useState(false);
  useEffect(() => {
    if (!sessionKey) return;
    setBackendDown(false);
    const t = setTimeout(() => {
      if (!status.data && !account.data) setBackendDown(true);
    }, 15_000);
    return () => clearTimeout(t);
  }, [sessionKey, status.data, account.data]);

  return (
    <ErrorBoundary label="Dashboard">
    <div className="dvh-min" style={{ background: "var(--bg)" }}>

      {/* ── First trade reaction overlay ───────────────────────────── */}
      <FirstTradeReaction lastEvent={lastEvent as Record<string, unknown> | null} />

      {/* ── Pre-start safety gate ──────────────────────────────────── */}
      {showStartConfirm && (
        <StartConfirmModal
          config={{
            strategyType:      strategyType,
            strategyName:      PERSONA_DISPLAY[strategyType]?.name     ?? strategyType,
            strategyTagline:   PERSONA_DISPLAY[strategyType]?.tagline  ?? "",
            isPaper:           activeVenue?.isPaper ?? true,
            venueName:         VENUE_LABEL[venueType] ?? venueType,
            market:            market,
            paperCapital:      paperCapital,
            minConfidencePct:  minConfidence,
            maxDailyLossPct:   maxDailyLoss,
            maxTradesPerDay:   maxTradesDay,
            lossCooldownCount: lossCooldown,
            symbols:           [symbol],
          } as StartConfig}
          onConfirm={doStartAgent}
          onCancel={() => setShowStartConfirm(false)}
        />
      )}

      {backendDown && (
        <div style={{
          background: "rgba(239,68,68,0.08)", borderBottom: "1px solid rgba(239,68,68,0.25)",
          padding: "10px 20px", textAlign: "center",
          fontSize: 12, color: "#fecaca",
        }}>
          <strong style={{ color: "#fca5a5" }}>Backend offline.</strong>{" "}
          The trading engine isn&apos;t responding. Live data, agent control, and trades are temporarily unavailable.
        </div>
      )}

      {!connected && status.data?.status === "running" && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, zIndex: 999,
          background: "#ef4444", color: "#fff", textAlign: "center",
          padding: "8px 16px", fontSize: 13, fontWeight: 600,
        }}>
          ⚠ Live data disconnected — reconnecting… Open positions may not reflect current prices.
        </div>
      )}

      {/* Mode banner — shows clearly whether agent is in paper or live mode */}
      {running && (
        activeVenue && !activeVenue.isPaper ? (
          /* LIVE mode — red urgent banner */
          <div style={{
            background: "linear-gradient(90deg, rgba(239,68,68,0.15), rgba(251,146,60,0.12))",
            borderBottom: "1px solid rgba(239,68,68,0.35)",
            padding: "8px 20px", display: "flex", alignItems: "center",
            justifyContent: "center", gap: 10,
          }}>
            <motion.span animate={{ opacity: [1, 0.5, 1] }} transition={{ duration: 1.2, repeat: Infinity }}
              style={{ width: 7, height: 7, borderRadius: "50%", background: "#ef4444",
                display: "inline-block", flexShrink: 0 }} />
            <span style={{ fontSize: 11, fontWeight: 700, color: "#fca5a5",
              letterSpacing: "0.08em", textTransform: "uppercase" }}>
              LIVE TRADING — Real money at risk. AI is placing real orders.
            </span>
            <a href="/settings?tab=venues" style={{ marginLeft: 4, fontSize: 10,
              color: "rgba(252,165,165,0.55)", textDecoration: "underline" }}>
              Switch to paper
            </a>
          </div>
        ) : (
          /* PAPER mode — green calm banner */
          <div style={{
            background: "rgba(74,222,128,0.04)",
            borderBottom: "1px solid rgba(74,222,128,0.15)",
            padding: "7px 20px", display: "flex", alignItems: "center",
            justifyContent: "center", gap: 10,
          }}>
            <span style={{ fontSize: 9, fontWeight: 700, color: "#4ade80",
              background: "rgba(74,222,128,0.12)", border: "1px solid rgba(74,222,128,0.25)",
              padding: "2px 8px", borderRadius: 4, letterSpacing: "0.1em" }}>
              PAPER TRADING
            </span>
            <span style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>
              Simulated trades only — no real money at risk.
              Balance: <strong style={{ color: "#4ade80" }}>
                ${(acc?.equity ?? paperCapital).toLocaleString("en-US", { maximumFractionDigits: 2 })}
              </strong> (virtual)
            </span>
            <a href="/settings?tab=venues" style={{ fontSize: 10,
              color: "rgba(74,222,128,0.5)", textDecoration: "underline" }}>
              Switch to live
            </a>
          </div>
        )
      )}

      {/* ── Guard Settings Drawer ──────────────────────────────────── */}
      <AnimatePresence>
        {showGuards && !running && (
          <motion.div
            initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
            style={{ overflow: "hidden", borderBottom: "1px solid rgba(251,191,36,0.15)",
              background: "rgba(251,191,36,0.04)" }}
          >
            <div style={{ padding: "14px 24px", display: "flex", gap: 28, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24",
                  textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Guard Settings
                </span>
                <button onClick={() => setShowGuards(false)}
                  aria-label="Close guard settings"
                  style={{ display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 22, height: 22, borderRadius: 6,
                    background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.25)",
                    color: "#fbbf24", cursor: "pointer", padding: 0 }}>
                  <span style={{ fontSize: 14, lineHeight: 1, fontWeight: 700 }}>×</span>
                </button>
              </div>
              {/* Paper capital — only relevant for paper mode */}
              {(activeVenue?.isPaper ?? true) && (
                <div title="Simulated starting balance for paper trading">
                  <p style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", marginBottom: 4 }}>
                    Paper Capital: ${paperCapital.toLocaleString()}
                  </p>
                  <select value={paperCapital} onChange={e => setPaperCapital(Number(e.target.value))}
                    style={{ background: "rgba(74,222,128,0.06)", border: "1px solid rgba(74,222,128,0.2)",
                      borderRadius: 6, padding: "3px 8px", fontSize: 11, color: "#4ade80", cursor: "pointer" }}>
                    <option value={1000}>$1,000</option>
                    <option value={5000}>$5,000</option>
                    <option value={10000}>$10,000</option>
                    <option value={25000}>$25,000</option>
                    <option value={50000}>$50,000</option>
                    <option value={100000}>$100,000</option>
                  </select>
                </div>
              )}

              {[
                { label: `Min Confidence: ${minConfidence}%`, value: minConfidence, set: setMinConfidence, min: 0, max: 95, tip: "Skip trades below this confidence" },
                { label: `Max Daily Loss: ${maxDailyLoss > 0 ? maxDailyLoss + "%" : "Off"}`, value: maxDailyLoss, set: setMaxDailyLoss, min: 0, max: 30, tip: "Stop after X% daily loss" },
                { label: `Max Trades/Day: ${maxTradesDay > 0 ? maxTradesDay : "Unlimited"}`, value: maxTradesDay, set: setMaxTradesDay, min: 0, max: 50, tip: "Hard cap on daily trades" },
                { label: `Loss Cooldown: ${lossCooldown > 0 ? lossCooldown + " losses" : "Off"}`, value: lossCooldown, set: setLossCooldown, min: 0, max: 10, tip: "Pause after N consecutive losses" },
              ].map(({ label, value, set, min, max, tip }) => (
                <div key={label} title={tip}>
                  <p style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", marginBottom: 4 }}>{label}</p>
                  <input type="range" min={min} max={max} value={value}
                    onChange={e => set(parseInt(e.target.value))}
                    style={{ width: 120, accentColor: "#fbbf24" }} />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <motion.header
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
          padding: isMobile ? "0 12px" : "0 28px",
          height: 60,
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "rgba(0,0,0,0.85)",
          position: "sticky",
          top: 0,
          zIndex: 50,
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          overflow: "hidden",
        }}
      >
        <Link href="/" style={{ textDecoration: "none" }}>
          <LogoWordmark size={30} />
        </Link>

        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, overflow: "hidden" }}>
          {/* WS dot */}
          <span title={connected ? "Live feed connected" : "Disconnected"} style={{ display: "flex", alignItems: "center", flexShrink: 0, color: connected ? "#22c55e" : "rgba(255,255,255,0.3)" }}>
            {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
          </span>

          {/* Live price — compact */}
          {displayPrice && !isMobile && (
            <span style={{ fontSize: 11, color: "rgba(255,255,255,0.65)", fontVariantNumeric: "tabular-nums",
              flexShrink: 0, whiteSpace: "nowrap" }}>
              {symbol.replace(/_/g, "/").replace("USDT", "")}{" "}
              <strong>
                {isForexVenue
                  // FOREX: show 4–5 decimal places, no $ prefix (it's a rate not a USD price)
                  ? displayPrice.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 5 })
                  // Crypto/stocks: rounded, $ prefix
                  : `$${displayPrice.toLocaleString("en-US", { maximumFractionDigits: displayPrice >= 1000 ? 0 : 2 })}`
                }
              </strong>
            </span>
          )}

          {/* Controls group — only when not mobile */}
          {!isMobile && !running && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
              {/* Persona — compact */}
              <select value={strategyType} onChange={e => setStrategyType(e.target.value)}
                style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 7, padding: "4px 6px", fontSize: 10, color: "rgba(255,255,255,0.55)",
                  cursor: "pointer", maxWidth: 110 }}>
                <option value="MOMENTUM_HUNTER">Momentum</option>
                <option value="SCALPER_AI">Scalper</option>
                <option value="SWING_MASTER">Swing</option>
                <option value="NEWS_REACTOR">News</option>
              </select>
              {/* Timeframe — compact */}
              <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
                style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 7, padding: "4px 6px", fontSize: 10, color: "rgba(255,255,255,0.55)",
                  cursor: "pointer", maxWidth: 70 }}>
                <option value="1m">1m</option>
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="1h">1h</option>
                <option value="4h">4h</option>
              </select>
              {/* Spot/Futures — only relevant for Binance/CCXT, not FOREX */}
              {!isForexVenue && (
                <select value={market} onChange={e => setMarket(e.target.value)}
                  title="spot = standard account, futures = requires Binance Futures account"
                  style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 7, padding: "4px 6px", fontSize: 10, color: "rgba(255,255,255,0.55)",
                    cursor: "pointer", maxWidth: 68 }}>
                  <option value="spot">Spot</option>
                  <option value="futures">Futures</option>
                </select>
              )}
              {/* Guards — icon+label compact */}
              <button onClick={() => setShowGuards(g => !g)}
                title="Guard settings: confidence gate, loss limits"
                style={{ display: "flex", alignItems: "center", gap: 4,
                  background: showGuards ? "rgba(251,191,36,0.12)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${showGuards ? "rgba(251,191,36,0.35)" : "rgba(255,255,255,0.08)"}`,
                  borderRadius: 7, padding: "4px 8px", fontSize: 10, cursor: "pointer",
                  color: showGuards ? "#fbbf24" : "rgba(255,255,255,0.4)" }}>
                <Shield size={9} /> Guards
              </button>
            </div>
          )}

          {/* Start / Stop agent */}
          <button
            onClick={!activeVenue && !running ? () => toast("Connect a venue in Settings first.", "warning") : handleAgentToggle}
            disabled={agentLoading}
            title={!activeVenue && !running ? "Connect a venue in Settings first" : undefined}
            style={{
              display: "flex", alignItems: "center", gap: 5, flexShrink: 0,
              background: running ? "rgba(239,68,68,0.15)" : !activeVenue ? "rgba(255,255,255,0.04)" : "rgba(34,197,94,0.15)",
              border: `1px solid ${running ? "rgba(239,68,68,0.4)" : !activeVenue ? "rgba(255,255,255,0.1)" : "rgba(34,197,94,0.4)"}`,
              color: running ? "#ef4444" : !activeVenue ? "var(--muted)" : "#22c55e",
              borderRadius: 8, padding: isMobile ? "7px" : "5px 12px",
              cursor: agentLoading ? "default" : "pointer",
              fontSize: 11, fontWeight: 700, whiteSpace: "nowrap",
              opacity: agentLoading ? 0.6 : 1, transition: "all 0.2s",
            }}
          >
            {running ? <Square size={10} /> : <Play size={10} />}
            {agentLoading ? "…" : running ? "Stop" : !activeVenue ? "No venue" : "Start"}
          </button>

          {/* Kill switch — close ALL positions immediately */}
          {running && (
            <button
              onClick={handleKillSwitch}
              disabled={agentLoading}
              title="Emergency: close all positions immediately"
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: killConfirm ? "rgba(239,68,68,0.25)" : "rgba(239,68,68,0.07)",
                border: `1px solid ${killConfirm ? "rgba(239,68,68,0.7)" : "rgba(239,68,68,0.2)"}`,
                color: "#ef4444",
                borderRadius: 10, padding: isMobile ? "7px" : "6px 12px",
                cursor: agentLoading ? "default" : "pointer",
                fontSize: 12, fontWeight: 500,
                opacity: agentLoading ? 0.6 : 1,
                transition: "all 0.2s",
              }}
            >
              <Zap size={11} />
              {!isMobile && (killConfirm ? "Tap to close ALL positions" : "Emergency: Close All")}
            </button>
          )}

          {/* Icon-only nav links — compact, no text, tooltip on hover */}
          {!isMobile && (
            <div style={{ display: "flex", alignItems: "center", gap: 2, flexShrink: 0 }}>
              {([
                { href: "/backtest",    icon: BarChart2,   title: "Backtest" },
                { href: "/journal",     icon: BookOpen,    title: "Journal"  },
                { href: "/marketplace", icon: ShoppingBag, title: "Market"   },
                { href: "/copy-trading",icon: Copy,        title: "Copy"     },
                { href: "/rag-memory",  icon: Brain,       title: "Memory"   },
                { href: "/audit",       icon: FileText,    title: "Audit"    },
                { href: "/trust",       icon: Shield,      title: "Trust"    },
              ] as { href: string; icon: React.ElementType; title: string }[]).map(({ href, icon: Icon, title }) => (
                <Link key={href} href={href} title={title}
                  style={{ display: "flex", alignItems: "center", justifyContent: "center",
                    width: 28, height: 28, borderRadius: 7,
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    color: "var(--muted)", textDecoration: "none",
                    transition: "all 0.15s" }}>
                  <Icon size={12} />
                </Link>
              ))}
            </div>
          )}
          <Link href="/billing" title={currentPlan === "FREE" ? "Upgrade plan" : "Manage billing"}
            style={{ display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0,
              background: currentPlan === "FREE" ? "rgba(255,255,255,0.04)"
                : currentPlan === "PRO" || currentPlan === "ENTERPRISE" ? "rgba(74,222,128,0.1)"
                : "rgba(167,139,250,0.1)",
              border: `1px solid ${currentPlan === "FREE" ? "rgba(255,255,255,0.1)"
                : currentPlan === "PRO" || currentPlan === "ENTERPRISE" ? "rgba(74,222,128,0.3)"
                : "rgba(167,139,250,0.3)"}`,
              borderRadius: 7, padding: "4px 8px",
              color: currentPlan === "FREE" ? "rgba(255,255,255,0.4)"
                : currentPlan === "PRO" || currentPlan === "ENTERPRISE" ? "var(--green)"
                : "#a78bfa",
              fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
              textDecoration: "none", whiteSpace: "nowrap" }}>
            {currentPlan}
            {currentPlan === "FREE" && <span style={{ fontSize: 9, opacity: 0.6 }}>↑</span>}
          </Link>
          <Link href="/settings" title="Settings"
            style={{ display: "flex", alignItems: "center", justifyContent: "center",
              width: 28, height: 28, borderRadius: 7, flexShrink: 0,
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
              color: "var(--muted)", textDecoration: "none" }}>
            <Settings size={13} />
          </Link>
          <UserButton />
          <button onClick={handleRefresh} disabled={refreshing} title="Refresh data"
            style={{ display: "flex", alignItems: "center", justifyContent: "center",
              width: 28, height: 28, borderRadius: 7, flexShrink: 0,
              background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
              cursor: refreshing ? "default" : "pointer",
              color: refreshing ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.5)",
              transition: "all 0.2s" }}>
            <RefreshCw size={12} style={{ animation: refreshing ? "spin 1s linear infinite" : undefined }} />
          </button>
        </div>
      </motion.header>

      {/* ── Main content ────────────────────────────────────────────── */}
      <main style={{ padding: isMobile ? "16px 12px 100px" : "32px 36px 56px", maxWidth: 1500, margin: "0 auto" }}>

        {/* Getting started checklist — shown for new users for 14 days */}
        <GettingStartedChecklist userId={sessionKey} />

        {/* Status bar */}
        <div style={{ marginBottom: 14 }}>
          <StatusBar data={status.data} />
        </div>

        {/* Macro intel strip — fear/greed, MTF bias, news */}
        <div style={{ marginBottom: 14 }}>
          <ErrorBoundary label="MacroIntelStrip">
            <MacroIntelStrip symbols={status.data?.assets} />
          </ErrorBoundary>
        </div>

        {/* NL command bar — "buy BTC when RSI < 30" */}
        <div style={{ marginBottom: 24 }}>
          <ErrorBoundary label="NLCommandBar">
            <NLCommandBar />
          </ErrorBoundary>
        </div>

        {/* Stat cards */}
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, minmax(0, 1fr))", gap: isMobile ? 10 : 16, marginBottom: 24 }}>
          <StatCard
            label="Portfolio Equity"
            value={acc ? `$${(acc.equity ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
            sub={acc ? `${isUp ? "▲" : "▼"} ${Math.abs(acc.total_return_pct ?? 0).toFixed(2)}% total return` : undefined}
            icon={TrendingUp} trend={isUp ? "up" : "down"} glow delay={0}
          />
          <StatCard
            label="Unrealised PnL"
            value={totalPnL ? `${totalPnL >= 0 ? "+" : ""}$${totalPnL.toFixed(2)}` : "$0.00"}
            sub={acc ? `Available: $${(acc.balance ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined}
            icon={totalPnL >= 0 ? TrendingUp : TrendingDown} trend={totalPnL >= 0 ? "up" : "down"} delay={0.07}
          />
          <StatCard
            label="Open Positions"
            value={pos.length.toString()}
            sub={`Max ${risk.data?.max_concurrent_positions ?? "—"} allowed`}
            icon={Layers} trend="neutral" delay={0.14}
          />
          <StatCard
            label="Sharpe Ratio"
            value={acc ? (acc.sharpe ?? 0).toFixed(3) : "—"}
            sub="Risk-adjusted return"
            icon={Activity} trend={acc && acc.sharpe > 0 ? "up" : "neutral"} delay={0.21}
          />
        </div>

        {/* Main grid */}
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 400px", gap: isMobile ? 14 : 22 }}>

          {/* Left column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

            {/* TradingView chart */}
            <motion.section
              className="card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              style={{ padding: "22px 24px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
                {/* Venue selector */}
                {userVenues.length === 0 && !venuesLoading ? (
                  <Link href="/settings" style={{ padding: "6px 14px", borderRadius: 8,
                    background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.3)",
                    color: "#fbbf24", fontSize: 12, fontWeight: 600, textDecoration: "none" }}>
                    ⚠ Configure a venue in Settings →
                  </Link>
                ) : (
                  <DarkSelect
                    value={activeVenue?.id ?? ""}
                    onChange={(id) => {
                      const v = userVenues.find(x => x.id === id);
                      if (v) {
                        userVenues.forEach(uv => {
                          if (uv.id !== v.id && uv.isActive)
                            fetch(`/api/venues/${uv.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ isActive: false }) });
                        });
                        fetch(`/api/venues/${v.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ isActive: true }) })
                          .then(() => reloadVenues());
                      }
                    }}
                    options={userVenues.map(v => ({
                      value: v.id,
                      label: `${VENUE_LABEL[v.type] ?? v.type}`,
                      sub:   v.isPaper ? "Paper trading" : "Live",
                    }))}
                    style={{ minWidth: 220 }}
                  />
                )}

                {/* Market picker — all markets: Crypto / Forex / Stocks / Indices */}
                <MarketPicker
                  value={symbol}
                  venueType={chartVenueType}
                  onChange={(sym, vType) => { setSymbol(sym); setChartVenueType(vType); }}
                />
              </div>
              <ErrorBoundary label="TradingChart">
                <TradingChart symbol={symbol} venueType={chartVenueType} livePrice={livePrice} />
              </ErrorBoundary>
            </motion.section>

            {/* Equity curve */}
            <motion.section className="card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.25 }} style={{ padding: "22px 24px" }}>
              <p style={{ fontSize: 11, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--muted)", marginBottom: 16 }}>
                Equity Curve
              </p>
              <EquityChart data={equityHistory} />
            </motion.section>

            {/* Open Positions */}
            <motion.section className="card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.32 }}>
              <div style={{ padding: "20px 24px 14px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                <Layers size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)", letterSpacing: "0.02em" }}>Open Positions</span>
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)", background: "rgba(255,255,255,0.05)", padding: "2px 10px", borderRadius: 20 }}>{pos.length}</span>
              </div>
              <PositionsTable positions={pos} isPaper={positions.data?.is_paper ?? activeVenue?.isPaper} venueType={venueType} />
            </motion.section>
          </div>

          {/* Right column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <motion.section className="card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.35 }} style={{ padding: "22px 24px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
                <Shield size={14} style={{ color: "rgba(255,255,255,0.4)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>Risk Config</span>
              </div>
              <RiskPanel risk={risk.data} />
            </motion.section>

            <motion.section className="card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.42 }} style={{ padding: "22px 24px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
                <span style={{ fontSize: 14, lineHeight: 1 }}>⚡</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>AI Decisions</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: connected ? "#22c55e" : "var(--muted)" }}>
                  {connected ? "● live" : "polling"}
                </span>
              </div>
              {/* Last AI Decision — prominent card */}
              {running && decisions.data?.decisions?.[0] && (() => {
                const latest = decisions.data?.decisions?.[0];
                const d = latest.trade_decisions?.[0];
                if (!d) return null;
                const isBuy = d.action === "buy";
                const isSell = d.action === "sell";
                const isHold = d.action === "hold" || (!isBuy && !isSell);
                const color = isBuy ? "#4ade80" : isSell ? "#ef4444" : "rgba(255,255,255,0.4)";
                const bg    = isBuy ? "rgba(74,222,128,0.06)" : isSell ? "rgba(239,68,68,0.06)" : "rgba(255,255,255,0.02)";
                const border= isBuy ? "rgba(74,222,128,0.2)"  : isSell ? "rgba(239,68,68,0.2)"  : "rgba(255,255,255,0.07)";
                const conf  = d.confidence ? Math.round(Number(d.confidence) * 100) : null;
                return (
                  <div style={{ background: bg, border: `1px solid ${border}`,
                    borderRadius: 12, padding: "14px 16px", marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "flex-start", gap: 10 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                          <span style={{ fontSize: 9, fontWeight: 700, color,
                            background: `${color}18`, border: `1px solid ${color}30`,
                            padding: "2px 8px", borderRadius: 4, letterSpacing: "0.1em",
                            textTransform: "uppercase" as const }}>
                            AI {d.action.toUpperCase()}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
                            {d.asset}
                          </span>
                          {d.allocation_usd > 0 && !isHold && (
                            <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                              ${Number(d.allocation_usd).toLocaleString("en-US", { maximumFractionDigits: 0 })}
                            </span>
                          )}
                          {conf !== null && (
                            <span style={{ fontSize: 10, color: conf >= 70 ? "#4ade80" : conf >= 50 ? "#fbbf24" : "#f87171",
                              marginLeft: "auto" }}>
                              {conf}% confidence
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.55 }}>
                          <strong style={{ color: "rgba(255,255,255,0.7)" }}>Why:</strong>{" "}
                          {String(d.rationale ?? "No rationale provided").slice(0, 200)}
                        </p>
                        {(d.tp_price || d.sl_price) && !isHold && (
                          <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                            {d.tp_price && (
                              <span style={{ fontSize: 10, color: "#4ade80" }}>
                                TP:{" "}
                                {isForexVenue
                                  ? Number(d.tp_price).toFixed(5)
                                  : `$${Number(d.tp_price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                              </span>
                            )}
                            {d.sl_price && (
                              <span style={{ fontSize: 10, color: "#ef4444" }}>
                                SL:{" "}
                                {isForexVenue
                                  ? Number(d.sl_price).toFixed(5)
                                  : `$${Number(d.sl_price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <p style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", marginTop: 6 }}>
                      {new Date(latest.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      {" · AI reasoning based on RSI, MACD, EMA + macro sentiment"}
                    </p>
                  </div>
                );
              })()}
              <DecisionsFeed decisions={decisions.data?.decisions ?? []} />
            </motion.section>

            {/* Decision Timeline */}
            {running && (
              <motion.section
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                style={{ marginTop: 16 }}
              >
                <DecisionTimeline userId={sessionKey} />
              </motion.section>
            )}
          </div>
        </div>
      </main>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer style={{ borderTop: "1px solid var(--border)", padding: isMobile ? "16px 12px" : "20px 28px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <LogoWordmark size={24} />
        {!isMobile && <span style={{ fontSize: 12, color: "var(--muted)" }}>
          Hyperliquid · Binance · Bybit · OKX · Kraken · Coinbase · OANDA · MetaTrader · Alpaca · IBKR
        </span>}
        {/* Admin link */}
        <Link href="/admin"
          style={{ fontSize: 11, color: "rgba(255,255,255,0.15)", textDecoration: "none",
            display: "flex", alignItems: "center", gap: 4 }}>
          ⚙ Admin
        </Link>

        {/* Replay tour for existing users */}
        <button
          onClick={() => {
            try {
              localStorage.removeItem("qt:onboarding_done_v2");
              localStorage.removeItem("qt:onboarding");
            } catch { /* private mode */ }
            window.location.href = "/onboarding";
          }}
          style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", background: "none",
            border: "none", cursor: "pointer", textDecoration: "underline" }}>
          Take the setup tour again
        </button>
      </footer>
      {isMobile && <div style={{ height: 60 }} />}

      {/* ── Mobile bottom navigation + controls drawer ── */}
      {isMobile && (
        <MobileBottomNav
          running={running}
          agentLoading={agentLoading}
          onStart={() => setShowStartConfirm(true)}
          onStop={handleAgentToggle}
          onKillswitch={handleKillSwitch}
          strategyType={strategyType}
          timeframe={timeframe}
          market={market}
          onStrategy={setStrategyType}
          onTimeframe={setTimeframe}
          onMarket={setMarket}
          showGuards={showGuards}
          onToggleGuards={() => setShowGuards(g => !g)}
        />
      )}
    </div>
    </ErrorBoundary>
  );
}
