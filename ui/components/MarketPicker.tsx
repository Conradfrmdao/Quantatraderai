"use client";
/**
 * MarketPicker — browse all markets (Crypto / Forex / Stocks / Indices / Commodities)
 * regardless of which venue is configured.
 * Viewing a chart != executing a trade.
 */
import { useState } from "react";
import { Search } from "lucide-react";

interface Market {
  symbol:    string;   // symbol sent to TradingChart
  label:     string;   // display name
  category:  string;
}

const ALL_MARKETS: Market[] = [
  // ── Crypto ────────────────────────────────────────────────────────
  { symbol: "BTCUSDT",  label: "Bitcoin",   category: "Crypto" },
  { symbol: "ETHUSDT",  label: "Ethereum",  category: "Crypto" },
  { symbol: "SOLUSDT",  label: "Solana",    category: "Crypto" },
  { symbol: "BNBUSDT",  label: "BNB",       category: "Crypto" },
  { symbol: "XRPUSDT",  label: "XRP",       category: "Crypto" },
  { symbol: "DOGEUSDT", label: "Dogecoin",  category: "Crypto" },
  { symbol: "AVAXUSDT", label: "Avalanche", category: "Crypto" },
  { symbol: "LINKUSDT", label: "Chainlink", category: "Crypto" },
  { symbol: "ARBUSDT",  label: "Arbitrum",  category: "Crypto" },
  { symbol: "SUIUSDT",  label: "SUI",       category: "Crypto" },

  // ── Forex ──────────────────────────────────────────────────────────
  { symbol: "EURUSD",   label: "EUR / USD",    category: "Forex" },
  { symbol: "GBPUSD",   label: "GBP / USD",    category: "Forex" },
  { symbol: "USDJPY",   label: "USD / JPY",    category: "Forex" },
  { symbol: "AUDUSD",   label: "AUD / USD",    category: "Forex" },
  { symbol: "USDCAD",   label: "USD / CAD",    category: "Forex" },
  { symbol: "USDCHF",   label: "USD / CHF",    category: "Forex" },
  { symbol: "NZDUSD",   label: "NZD / USD",    category: "Forex" },
  { symbol: "EURGBP",   label: "EUR / GBP",    category: "Forex" },
  { symbol: "EURJPY",   label: "EUR / JPY",    category: "Forex" },
  { symbol: "GBPJPY",   label: "GBP / JPY",    category: "Forex" },

  // ── Metals & Commodities ───────────────────────────────────────────
  { symbol: "XAUUSD",   label: "Gold",      category: "Commodities" },
  { symbol: "XAGUSD",   label: "Silver",    category: "Commodities" },
  { symbol: "USOIL",    label: "Crude Oil", category: "Commodities" },

  // ── Indices ───────────────────────────────────────────────────────
  { symbol: "US30",     label: "Dow Jones",   category: "Indices" },
  { symbol: "NAS100",   label: "Nasdaq 100",  category: "Indices" },
  { symbol: "SPX500",   label: "S&P 500",     category: "Indices" },
  { symbol: "DE40",     label: "DAX 40",      category: "Indices" },
  { symbol: "UK100",    label: "FTSE 100",    category: "Indices" },
  { symbol: "JP225",    label: "Nikkei 225",  category: "Indices" },

  // ── US Stocks ─────────────────────────────────────────────────────
  { symbol: "AAPL",     label: "Apple",       category: "Stocks" },
  { symbol: "TSLA",     label: "Tesla",       category: "Stocks" },
  { symbol: "NVDA",     label: "Nvidia",      category: "Stocks" },
  { symbol: "MSFT",     label: "Microsoft",   category: "Stocks" },
  { symbol: "GOOGL",    label: "Alphabet",    category: "Stocks" },
  { symbol: "AMZN",     label: "Amazon",      category: "Stocks" },
  { symbol: "META",     label: "Meta",        category: "Stocks" },
  { symbol: "SPY",      label: "S&P 500 ETF", category: "Stocks" },
  { symbol: "QQQ",      label: "Nasdaq ETF",  category: "Stocks" },
];

const CATEGORIES = ["All", "Crypto", "Forex", "Commodities", "Indices", "Stocks"];

// Category → which venueType the TradingChart should use for correct price format
export const MARKET_VENUE_TYPE: Record<string, string> = {
  Crypto:      "BINANCE",
  Forex:       "METATRADER",
  Commodities: "METATRADER",
  Indices:     "METATRADER",
  Stocks:      "ALPACA",
};

interface Props {
  value:     string;
  venueType: string;
  onChange:  (symbol: string, venueType: string) => void;
}

export function MarketPicker({ value, venueType, onChange }: Props) {
  const [open,   setOpen]   = useState(false);
  const [cat,    setCat]    = useState("All");
  const [query,  setQuery]  = useState("");

  const filtered = ALL_MARKETS.filter(m =>
    (cat === "All" || m.category === cat) &&
    (!query || m.label.toLowerCase().includes(query.toLowerCase()) ||
               m.symbol.toLowerCase().includes(query.toLowerCase()))
  );

  const current = ALL_MARKETS.find(m => m.symbol === value);
  const currentVenue = MARKET_VENUE_TYPE[current?.category ?? "Crypto"] ?? venueType ?? "BINANCE";

  return (
    <div style={{ position: "relative" }}>
      {/* Trigger */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 14px", borderRadius: 10,
          background: open ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)",
          border: `1px solid ${open ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.1)"}`,
          color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
          minWidth: 160, transition: "all 0.15s",
        }}
      >
        <span style={{ flex: 1, textAlign: "left" }}>
          {current ? (
            <>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 10, fontWeight: 400, marginRight: 6 }}>
                {current.category}
              </span>
              {current.label}
            </>
          ) : value}
        </span>
        <span style={{ fontSize: 9, color: "rgba(255,255,255,0.35)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 999, padding: "2px 6px" }}>
          {currentVenue}
        </span>
        <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", transform: open ? "rotate(180deg)" : undefined, display: "inline-block", transition: "transform 0.2s" }}>▼</span>
      </button>

      {/* Panel */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0,
          zIndex: 200, width: 340,
          background: "#0d0d0d",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 14,
          boxShadow: "0 20px 50px rgba(0,0,0,0.7)",
          overflow: "hidden",
        }}>
          {/* Search */}
          <div style={{ padding: "10px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", gap: 8 }}>
            <Search size={12} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} />
            <input
              autoFocus
              placeholder="Search markets…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{
                flex: 1, background: "transparent", border: "none", outline: "none",
                color: "#fff", fontSize: 13,
              }}
            />
          </div>

          {/* Category tabs */}
          <div style={{ display: "flex", gap: 2, padding: "8px 10px", borderBottom: "1px solid rgba(255,255,255,0.06)", overflowX: "auto" }}>
            {CATEGORIES.map(c => (
              <button key={c} onClick={() => setCat(c)} style={{
                padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500,
                whiteSpace: "nowrap", cursor: "pointer",
                background: cat === c ? "rgba(255,255,255,0.1)" : "transparent",
                border: cat === c ? "1px solid rgba(255,255,255,0.15)" : "1px solid transparent",
                color: cat === c ? "#fff" : "rgba(255,255,255,0.4)",
              }}>
                {c}
              </button>
            ))}
          </div>

          {/* Market list */}
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {filtered.length === 0 ? (
              <p style={{ padding: "20px", textAlign: "center", fontSize: 12, color: "rgba(255,255,255,0.3)" }}>
                No results for "{query}"
              </p>
            ) : filtered.map(m => {
              const isSelected = m.symbol === value;
              const vType = MARKET_VENUE_TYPE[m.category] ?? "BINANCE";
              return (
                <button
                  key={m.symbol}
                  onClick={() => { onChange(m.symbol, vType); setOpen(false); setQuery(""); }}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 12,
                    padding: "10px 14px", background: isSelected ? "rgba(255,255,255,0.06)" : "transparent",
                    border: "none", borderBottom: "1px solid rgba(255,255,255,0.03)",
                    cursor: "pointer", textAlign: "left",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)"; }}
                  onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 13, fontWeight: isSelected ? 600 : 500, color: "#fff", margin: 0 }}>{m.label}</p>
                    <p style={{ fontSize: 10, color: "rgba(255,255,255,0.35)", margin: 0, marginTop: 1 }}>{m.symbol}</p>
                  </div>
                  <span style={{
                    fontSize: 9, fontWeight: 600, padding: "2px 7px", borderRadius: 6,
                    textTransform: "uppercase", letterSpacing: "0.06em",
                    background: m.category === "Crypto" ? "rgba(251,191,36,0.1)" :
                                m.category === "Forex"  ? "rgba(74,222,128,0.1)" :
                                m.category === "Stocks" ? "rgba(96,165,250,0.1)" :
                                m.category === "Indices"? "rgba(167,139,250,0.1)" :
                                "rgba(249,115,22,0.1)",
                    color: m.category === "Crypto"  ? "#fbbf24" :
                           m.category === "Forex"   ? "#4ade80" :
                           m.category === "Stocks"  ? "#60a5fa" :
                           m.category === "Indices" ? "#a78bfa" :
                           "#f97316",
                  }}>
                    {m.category}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Custom symbol footer */}
          <div style={{ padding: "8px 12px", borderTop: "1px solid rgba(255,255,255,0.06)", display: "flex", gap: 8 }}>
            <input
              placeholder="Type any symbol (e.g. AUDJPY, GOOG)"
              onKeyDown={e => {
                if (e.key === "Enter") {
                  const t = (e.target as HTMLInputElement).value.trim().toUpperCase();
                  if (t) {
                    // Guess venue type from symbol
                    const vType = /[A-Z]{6}/.test(t) && !t.endsWith("USDT") && !t.endsWith("USD") ? "METATRADER" :
                                  /^[A-Z]{1,5}$/.test(t) ? "ALPACA" : "BINANCE";
                    onChange(t, vType);
                    setOpen(false);
                    setQuery("");
                  }
                }
              }}
              style={{
                flex: 1, padding: "6px 10px", borderRadius: 8,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "rgba(255,255,255,0.6)", fontSize: 12, outline: "none",
              }}
            />
          </div>
          <div style={{ padding: "0 12px 10px", display: "flex", flexWrap: "wrap", gap: 6 }}>
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.45)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 999, padding: "3px 8px" }}>
              Selected venue {currentVenue}
            </span>
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.45)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 999, padding: "3px 8px" }}>
              Charts use backend market API
            </span>
          </div>
        </div>
      )}

      {/* Backdrop */}
      {open && (
        <div onClick={() => setOpen(false)} style={{
          position: "fixed", inset: 0, zIndex: 199,
        }} />
      )}
    </div>
  );
}
