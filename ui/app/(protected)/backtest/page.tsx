"use client";
import { useState, useCallback, useRef, useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Play, Square } from "lucide-react";
import { LogoWordmark } from "@/components/Logo";
import { useIsMobile } from "@/hooks/useIsMobile";
import { DarkSelect } from "@/components/ui/dark-select";
import { useToast } from "@/components/Toast";

const EquityChart = dynamic(
  () => import("@/components/EquityChart").then((m) => m.EquityChart),
  { ssr: false },
);

interface BacktestResult {
  total_return_pct:  number;
  max_drawdown_pct:  number;
  win_rate_pct:      number;
  sharpe:            number;
  calmar:            number;
  total_trades:      number;
  ending_equity:     number;
  equity_curve:      { t: string; equity: number }[];
  trades:            {
    symbol: string; action: string; entry: number; exit: number; pnl: number; bars: number;
  }[];
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "10px 14px", borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)",
  color: "#fff", fontSize: 13, outline: "none",
};
const labelStyle: React.CSSProperties = {
  display: "block", fontSize: 11, color: "rgba(255,255,255,0.4)",
  marginBottom: 5, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.07em",
};

function MetricCard({ label, value, sub, positive }: {
  label: string; value: string; sub?: string; positive?: boolean;
}) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 14, padding: "18px 20px",
    }}>
      <p style={labelStyle}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 500, color: positive === undefined ? "#fff" : positive ? "var(--green)" : "var(--red)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </p>
      {sub && <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginTop: 4 }}>{sub}</p>}
    </div>
  );
}

function PublishCta({ result, symbol, venue, timeframe }: {
  result: BacktestResult; symbol: string; venue: string; timeframe: string;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName]   = useState(`${symbol} ${timeframe} strategy`);
  const [desc, setDesc]   = useState(`Backtested on ${venue}: ${result.total_return_pct.toFixed(1)}% return, Sharpe ${result.sharpe.toFixed(2)}.`);
  const [price, setPrice] = useState("0");
  const [pub, setPub]     = useState(true);
  const [busy, setBusy]   = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast("Strategy name required", "warning"); return; }
    setBusy(true);
    const res = await fetch("/api/marketplace", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name, description: desc, isPublic: pub, price: parseFloat(price) || 0,
        sharpe:      result.sharpe,
        totalReturn: result.total_return_pct,
        maxDrawdown: result.max_drawdown_pct,
        config:      JSON.stringify({ venue, symbol, timeframe }),
      }),
    }).catch(() => null);
    setBusy(false);
    if (res?.ok) { toast("Strategy published to marketplace", "success"); setOpen(false); }
    else if (res?.status === 402) { toast("Publishing requires the PRO plan. Upgrade in Billing.", "warning"); }
    else { toast("Publish failed. Try again.", "error"); }
  };

  return (
    <>
      <div style={{ marginTop: 20, padding: "16px 20px", background: "rgba(167,139,250,0.05)",
        border: "1px solid rgba(167,139,250,0.2)", borderRadius: 14,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <p style={{ fontSize: 13, color: "#fff", fontWeight: 600 }}>Happy with these results?</p>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", marginTop: 2 }}>
            Publish this strategy to the marketplace — your verified Sharpe + return will be public.
          </p>
        </div>
        <button onClick={() => setOpen(true)} style={{ padding: "10px 18px", borderRadius: 10,
          background: "rgba(167,139,250,0.15)", border: "1px solid rgba(167,139,250,0.4)",
          color: "#a78bfa", fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
          Publish to Marketplace →
        </button>
      </div>

      {open && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 200,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            style={{ background: "#111", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 18,
              padding: 28, width: "100%", maxWidth: 480 }}>
            <p style={{ fontSize: 16, fontWeight: 600, color: "#fff", marginBottom: 6 }}>Publish Strategy</p>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginBottom: 18 }}>
              Verified metrics: Sharpe {result.sharpe.toFixed(2)} · Return {result.total_return_pct.toFixed(1)}% · MaxDD {result.max_drawdown_pct.toFixed(1)}%
            </p>
            <label style={labelStyle}>Strategy Name</label>
            <input style={inputStyle} value={name} onChange={e => setName(e.target.value)} />
            <label style={{ ...labelStyle, marginTop: 14 }}>Description</label>
            <textarea style={{ ...inputStyle, height: 80, resize: "none", fontFamily: "inherit" }}
              value={desc} onChange={e => setDesc(e.target.value)} />
            <label style={{ ...labelStyle, marginTop: 14 }}>Monthly price (USD · 0 = free)</label>
            <input style={inputStyle} type="number" min="0" value={price} onChange={e => setPrice(e.target.value)} />
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginTop: 14, fontSize: 13, color: "rgba(255,255,255,0.6)" }}>
              <input type="checkbox" checked={pub} onChange={e => setPub(e.target.checked)} />
              List publicly on marketplace
            </label>
            <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
              <button onClick={submit} disabled={busy}
                style={{ flex: 1, padding: "11px 0", borderRadius: 10, background: "#fff", color: "#000",
                  border: "none", fontWeight: 700, fontSize: 13, cursor: "pointer", opacity: busy ? 0.7 : 1 }}>
                {busy ? "Publishing…" : "Publish"}
              </button>
              <button onClick={() => setOpen(false)}
                style={{ padding: "11px 18px", borderRadius: 10, background: "transparent",
                  border: "1px solid rgba(255,255,255,0.12)", color: "rgba(255,255,255,0.5)",
                  cursor: "pointer", fontSize: 13 }}>Cancel</button>
            </div>
          </motion.div>
        </div>
      )}
    </>
  );
}

function ReplayVisualizer({ trades, capital }: {
  trades: BacktestResult["trades"];
  capital: number;
}) {
  const [step, setStep]       = useState(0);
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const max = trades.length;

  useEffect(() => {
    setStep(0);
    setPlaying(false);
  }, [trades]);

  useEffect(() => {
    if (!playing) return;
    if (step >= max) { setPlaying(false); return; }
    timerRef.current = setTimeout(() => setStep(s => s + 1), 400);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [playing, step, max]);

  if (trades.length === 0) return null;

  // Build running equity from trades up to current step
  const visible  = trades.slice(0, step);
  let equity     = capital;
  const points   = [{ i: 0, equity }];
  for (let i = 0; i < visible.length; i++) {
    equity += visible[i].pnl;
    points.push({ i: i + 1, equity });
  }

  const minEq = Math.min(...points.map(p => p.equity));
  const maxEq = Math.max(...points.map(p => p.equity));
  const W = 500; const H = 100;
  const scaleY = (v: number) => H - ((v - minEq) / (maxEq - minEq || 1)) * (H - 10) - 5;
  const scaleX = (i: number) => (i / max) * W;
  const pathD = points.map((p, idx) =>
    `${idx === 0 ? "M" : "L"}${scaleX(p.i).toFixed(1)},${scaleY(p.equity).toFixed(1)}`
  ).join(" ");

  const current = visible[visible.length - 1];
  const netPnl  = equity - capital;

  return (
    <div style={{ marginTop: 24, background: "rgba(255,255,255,0.03)",
      border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "22px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <p style={{ ...labelStyle, marginBottom: 2 }}>AI Simulation Replay</p>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            Step through every AI decision — see exactly what happened and why
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => { setStep(0); setPlaying(false); }}
            style={{ padding: "6px 12px", fontSize: 11, borderRadius: 8, cursor: "pointer",
              background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
              color: "rgba(255,255,255,0.5)" }}>
            Reset
          </button>
          <button onClick={() => setPlaying(p => !p)}
            style={{ padding: "6px 14px", fontSize: 11, fontWeight: 700, borderRadius: 8, cursor: "pointer",
              background: playing ? "rgba(239,68,68,0.15)" : "rgba(74,222,128,0.15)",
              border: `1px solid ${playing ? "rgba(239,68,68,0.3)" : "rgba(74,222,128,0.3)"}`,
              color: playing ? "#ef4444" : "#4ade80" }}>
            {playing ? "⏸ Pause" : step >= max ? "↺ Replay" : "▶ Play"}
          </button>
        </div>
      </div>

      {/* Progress strip */}
      <div style={{ height: 4, background: "rgba(255,255,255,0.06)", borderRadius: 2, marginBottom: 16 }}>
        <div style={{ height: "100%", borderRadius: 2,
          background: "linear-gradient(90deg,#4ade80,#818cf8)",
          width: `${max > 0 ? (step / max) * 100 : 0}%`,
          transition: "width 0.3s ease" }} />
      </div>

      {/* Chart */}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 100, display: "block", marginBottom: 14 }}>
        {points.length > 1 && (
          <path d={pathD} fill="none" strokeWidth={2} strokeLinecap="round"
            stroke={netPnl >= 0 ? "#4ade80" : "#ef4444"} />
        )}
        {/* Mark current trade entry */}
        {current && step > 0 && (
          <circle
            cx={scaleX(step - 1)}
            cy={scaleY(points[step - 1]?.equity ?? capital)}
            r={4}
            fill={current.action === "buy" ? "#4ade80" : "#ef4444"}
          />
        )}
      </svg>

      {/* Step counter + current trade info */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div>
          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
            Trade {step} of {max}
          </p>
          {current && (
            <div style={{ marginTop: 6, padding: "8px 12px", background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.07)", borderRadius: 8 }}>
              <span style={{ fontSize: 12, color: current.action === "buy" ? "#4ade80" : "#ef4444",
                fontWeight: 700, marginRight: 10 }}>
                {current.action.toUpperCase()} {current.symbol}
              </span>
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>
                Entry ${current.entry.toLocaleString()} → Exit ${current.exit.toLocaleString()}
              </span>
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>Running P&L</p>
          <p style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: "tabular-nums",
            color: netPnl >= 0 ? "#4ade80" : "#ef4444" }}>
            {netPnl >= 0 ? "+" : ""}${netPnl.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Step slider */}
      <input type="range" min={0} max={max} value={step}
        onChange={e => { setStep(parseInt(e.target.value)); setPlaying(false); }}
        style={{ width: "100%", marginTop: 12, accentColor: "#818cf8" }} />
    </div>
  );
}

export default function BacktestPage() {
  const isMobile  = useIsMobile();
  const toast     = useToast();
  const abortRef  = useRef<AbortController | null>(null);

  const [symbol,    setSymbol]    = useState("BTC/USDT");
  const [venue,     setVenue]     = useState("binance");
  const [timeframe, setTimeframe] = useState("1h");
  const [days,      setDays]      = useState("30");
  const [capital,   setCapital]   = useState("10000");
  const [strategy,  setStrategy]  = useState("rsi");

  const [running,  setRunning]  = useState(false);
  const [progress, setProgress] = useState(0);
  const [result,   setResult]   = useState<BacktestResult | null>(null);
  const [error,    setError]    = useState<string | null>(null);

  // Fake progress animation while waiting for backend
  useEffect(() => {
    if (!running) { setProgress(0); return; }
    setProgress(5);
    const id = setInterval(() => setProgress(p => p < 90 ? p + (90 - p) * 0.06 : p), 600);
    return () => clearInterval(id);
  }, [running]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
    setError("Backtest cancelled.");
  }, []);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          symbol, venue, timeframe,
          days: parseInt(days),
          initial_capital: parseFloat(capital),
          strategy,
        }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({})) as { detail?: string; error?: string; plan_required?: string };
        if (res.status === 402) {
          toast(`Backtesting requires the ${e.plan_required ?? "STARTER"} plan. Upgrade in Billing.`, "warning");
          setError(`Upgrade to ${e.plan_required ?? "STARTER"} to run backtests.`);
        } else {
          setError(e.detail ?? e.error ?? `Server error ${res.status}`);
        }
      } else {
        setProgress(100);
        setResult(await res.json() as BacktestResult);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(String(e));
    } finally {
      setRunning(false);
    }
  }, [symbol, venue, timeframe, days, capital, strategy, toast]);

  const isGood = result && result.total_return_pct >= 0;

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      {/* Header */}
      <header style={{
        padding: isMobile ? "0 12px" : "0 28px", height: 56,
        borderBottom: "1px solid var(--border)", display: "flex",
        alignItems: "center", gap: 12,
        background: "rgba(0,0,0,0.85)", backdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <Link href="/dashboard" style={{ color: "var(--muted)", display: "flex", alignItems: "center" }}>
          <ArrowLeft size={16} />
        </Link>
        <LogoWordmark size={26} />
        <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>/ Backtesting</span>
      </header>

      <main style={{ padding: isMobile ? "20px 12px 60px" : "32px 40px 60px", maxWidth: 1300, margin: "0 auto" }}>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>

          {/* Config panel */}
          <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "24px 28px", marginBottom: 28 }}>
            <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>
              Backtest Configuration
            </p>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(6,1fr)", gap: 14, marginBottom: 20 }}>
              <div><label style={labelStyle}>Symbol</label><input style={inputStyle} value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="BTC/USDT" /></div>
              <div><label style={labelStyle}>Venue</label>
                <DarkSelect value={venue} onChange={setVenue}
                  options={["binance","hyperliquid","bybit","okx","oanda","metatrader","alpaca"].map(v => ({ value: v, label: v }))} />
              </div>
              <div><label style={labelStyle}>Timeframe</label>
                <DarkSelect value={timeframe} onChange={setTimeframe}
                  options={["1m","5m","15m","1h","4h","1d"].map(t => ({ value: t, label: t }))} />
              </div>
              <div><label style={labelStyle}>Days of history</label><input style={inputStyle} type="number" value={days} onChange={e => setDays(e.target.value)} /></div>
              <div><label style={labelStyle}>Initial capital ($)</label><input style={inputStyle} type="number" value={capital} onChange={e => setCapital(e.target.value)} /></div>
              <div><label style={labelStyle}>Strategy</label>
                <DarkSelect value={strategy} onChange={setStrategy}
                  options={[{ value: "rsi", label: "RSI mean-reversion" }, { value: "llm", label: "AI agent" }]} />
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <button
                onClick={run} disabled={running}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  background: running ? "rgba(255,255,255,0.06)" : "#fff",
                  color: running ? "#888" : "#000",
                  border: "none", borderRadius: 10, padding: "10px 22px",
                  fontSize: 13, fontWeight: 600, cursor: running ? "default" : "pointer",
                  opacity: running ? 0.7 : 1,
                }}
              >
                <Play size={13} />
                {running ? "Running…" : "Run Backtest"}
              </button>
              {running && (
                <button onClick={cancel}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6,
                    padding: "10px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                    background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)",
                    color: "var(--red)", cursor: "pointer" }}>
                  <Square size={11} /> Cancel
                </button>
              )}
            </div>
            {/* Progress bar */}
            <AnimatePresence>
              {running && (
                <motion.div key="progress"
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  style={{ marginTop: 14, background: "rgba(255,255,255,0.05)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                  <motion.div
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                    style={{ height: "100%", background: "linear-gradient(90deg,#4ade80,#a78bfa)", borderRadius: 4 }}
                  />
                </motion.div>
              )}
            </AnimatePresence>
            {error && <p style={{ marginTop: 10, fontSize: 12, color: "var(--red)" }}>{error}</p>}
          </div>

          {/* Results */}
          {result && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(6,1fr)", gap: 12, marginBottom: 24 }}>
                <MetricCard label="Total Return" value={`${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct.toFixed(2)}%`} positive={result.total_return_pct >= 0} />
                <MetricCard label="Max Drawdown" value={`-${result.max_drawdown_pct.toFixed(2)}%`} positive={result.max_drawdown_pct < 10} />
                <MetricCard label="Win Rate"     value={`${result.win_rate_pct.toFixed(1)}%`} positive={result.win_rate_pct > 50} />
                <MetricCard label="Sharpe"       value={result.sharpe.toFixed(3)}  positive={result.sharpe > 0} />
                <MetricCard label="Calmar"       value={result.calmar.toFixed(3)}  positive={result.calmar > 0} />
                <MetricCard label="Total Trades" value={result.total_trades.toString()} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 340px", gap: 20 }}>
                <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "22px 24px" }}>
                  <p style={{ ...labelStyle, marginBottom: 16 }}>Equity Curve</p>
                  <EquityChart data={result.equity_curve} />
                </div>

                <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "22px 24px" }}>
                  <p style={{ ...labelStyle, marginBottom: 14 }}>Trade List ({result.trades.length})</p>
                  <div style={{ maxHeight: 280, overflowY: "auto" }}>
                    {result.trades.map((t, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 12 }}>
                        <span style={{ color: t.action === "buy" ? "var(--green)" : "var(--red)", fontWeight: 600, minWidth: 36 }}>{t.action.toUpperCase()}</span>
                        <span style={{ color: "#fff", flex: 1, marginLeft: 8 }}>{t.symbol}</span>
                        <span style={{ color: t.pnl >= 0 ? "var(--green)" : "var(--red)", fontVariantNumeric: "tabular-nums" }}>
                          {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Replay Visualizer */}
              <ReplayVisualizer trades={result.trades} capital={parseFloat(capital)} />

              {/* B3: Publish to Marketplace — auto-fills metrics from this backtest */}
              <PublishCta result={result} symbol={symbol} venue={venue} timeframe={timeframe} />
            </motion.div>
          )}
        </motion.div>
      </main>
    </div>
  );
}
