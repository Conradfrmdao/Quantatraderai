"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useUser, UserProfile, useClerk } from "@clerk/nextjs";
import { LogoWordmark } from "@/components/Logo";
import { ArrowLeft, Plus, Trash2, Save, Shield, Bell, User, Lock, Wifi, Eye, EyeOff } from "lucide-react";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useToast } from "@/components/Toast";
import { DarkSelect } from "@/components/ui/dark-select";

/* ─── Types ─────────────────────────────────────────────────────── */
type VenueType =
  | "HYPERLIQUID" | "BINANCE" | "OANDA" | "POLYMARKET" | "CCXT"
  | "METATRADER" | "BYBIT" | "OKX" | "KRAKEN" | "COINBASE" | "ALPACA" | "IBKR";

interface Venue {
  id: string;
  displayName: string;
  type: VenueType;
  apiKey: string;
  apiSecret: string;
  apiPassphrase: string | null;
  accountId: string | null;
  ccxtExchangeId: string | null;
  network: string | null;
  metaApiToken: string | null;
  metaApiAccountId: string | null;
  isPaper: boolean;
  isActive: boolean;
  riskProfile: RiskProfile | null;
}

interface RiskProfile {
  maxPositionPct: number;
  maxLeverage: number;
  mandatorySlPct: number;
  maxLossPerPositionPct: number;
  dailyLossCircuitBreaker: number;
  maxTotalExposurePct: number;
  maxConcurrentPositions: number;
}

interface UserSettings {
  telegramToken: string | null;
  telegramChatId: string | null;
  emailNotifications: boolean;
  timezone: string;
}

/* ─── Styles ─────────────────────────────────────────────────────── */
const card: React.CSSProperties = {
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: 16,
  padding: "24px 28px",
  marginBottom: 20,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "11px 14px",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(255,255,255,0.04)",
  color: "#fff",
  fontSize: 14,
  outline: "none",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "rgba(255,255,255,0.45)",
  marginBottom: 6,
  fontWeight: 500,
};

const btnPrimary: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 7,
  background: "#fff", color: "#000", border: "none",
  padding: "10px 20px", borderRadius: 10,
  fontSize: 13, fontWeight: 600, cursor: "pointer",
};

const btnOutline: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 7,
  background: "transparent",
  color: "rgba(255,255,255,0.55)",
  border: "1px solid rgba(255,255,255,0.12)",
  padding: "9px 18px", borderRadius: 10,
  fontSize: 13, fontWeight: 500, cursor: "pointer",
};

const VENUE_TYPES: VenueType[] = [
  "HYPERLIQUID", "BINANCE", "BYBIT", "OKX", "KRAKEN", "COINBASE",
  "OANDA", "METATRADER", "ALPACA", "IBKR", "POLYMARKET", "CCXT",
];

const VENUE_LABELS: Record<VenueType, string> = {
  HYPERLIQUID: "Hyperliquid (DEX perps)",
  BINANCE:     "Binance (crypto spot + futures)",
  BYBIT:       "Bybit (crypto perps)",
  OKX:         "OKX (crypto + DeFi)",
  KRAKEN:      "Kraken (crypto spot + futures)",
  COINBASE:    "Coinbase Advanced Trade",
  OANDA:       "OANDA (forex / CFDs)",
  METATRADER:  "MetaTrader 4/5 (forex / metals / indices)",
  ALPACA:      "Alpaca (US stocks / options)",
  IBKR:        "Interactive Brokers (stocks / options / futures)",
  POLYMARKET:  "Polymarket (prediction markets)",
  CCXT:        "Other exchange (CCXT)",
};

/* ─── Sub-components ─────────────────────────────────────────────── */
function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>
      {children}
    </p>
  );
}

/* ─── Venue Form ────────────────────────────────────────────────── */
function VenueForm({ onSave, onCancel, initialType }: {
  onSave: (v: Partial<Venue>) => void;
  onCancel: () => void;
  initialType?: string;
}) {
  // Pre-select onboarding choice if it's a valid VenueType
  const safeInitial = (initialType && VENUE_TYPES.includes(initialType as VenueType))
    ? (initialType as VenueType)
    : "HYPERLIQUID";
  const [form, setForm] = useState<Partial<Venue>>({ type: safeInitial, isPaper: true });
  const set = (k: keyof Venue, v: unknown) => setForm(f => ({ ...f, [k]: v }));
  const isMobile = useIsMobile();
  const [showSecret, setShowSecret] = useState(false);
  const [showApiKey, setShowApiKey]  = useState(false);

  return (
    <div style={{ ...card, border: "1px solid rgba(255,255,255,0.14)" }}>
      <SectionTitle>New Venue</SectionTitle>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
        <FieldGroup label="Display Name">
          <input style={inputStyle} placeholder="e.g. My Hyperliquid" value={form.displayName ?? ""} onChange={e => set("displayName", e.target.value)} />
        </FieldGroup>
        <FieldGroup label="Venue Type">
          <DarkSelect
            value={form.type ?? "HYPERLIQUID"}
            onChange={v => set("type", v as VenueType)}
            options={VENUE_TYPES.map(t => ({ value: t, label: VENUE_LABELS[t] }))}
            style={{ width: "100%" }}
          />
        </FieldGroup>
        {form.type !== "POLYMARKET" && form.type !== "METATRADER" && (<>
          <FieldGroup label={form.type === "HYPERLIQUID" ? "Private Key (API wallet)" : "API Key"}>
            <div style={{ position: "relative" }}>
              <input style={{ ...inputStyle, paddingRight: 36 }}
                placeholder={form.type === "HYPERLIQUID" ? "0x... (Hyperliquid API wallet key)" : "API key"}
                type={showApiKey ? "text" : "password"}
                value={form.apiKey ?? ""} onChange={e => set("apiKey", e.target.value)} />
              <button type="button" onClick={() => setShowApiKey(s => !s)}
                style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                  background: "none", border: "none", cursor: "pointer",
                  color: "rgba(255,255,255,0.3)", fontSize: 11, padding: 0 }}>
                {showApiKey ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </FieldGroup>
          {form.type !== "HYPERLIQUID" && (
            <FieldGroup label="API Secret">
              <div style={{ position: "relative" }}>
                <input style={{ ...inputStyle, paddingRight: 36 }} placeholder="API secret"
                  type={showSecret ? "text" : "password"}
                  value={form.apiSecret ?? ""} onChange={e => set("apiSecret", e.target.value)} />
                <button type="button" onClick={() => setShowSecret(s => !s)}
                  style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer",
                    color: "rgba(255,255,255,0.3)", fontSize: 11, padding: 0 }}>
                  {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
            </FieldGroup>
          )}
        </>)}
        {(form.type === "OANDA") && (
          <FieldGroup label="Account ID">
            <input style={inputStyle} placeholder="101-001-12345678-001" value={form.accountId ?? ""} onChange={e => set("accountId", e.target.value)} />
          </FieldGroup>
        )}
        {(form.type === "CCXT") && (
          <FieldGroup label="Exchange ID (CCXT)">
            <input style={inputStyle} placeholder="e.g. kraken, okx, bybit" value={form.ccxtExchangeId ?? ""} onChange={e => set("ccxtExchangeId", e.target.value)} />
          </FieldGroup>
        )}
        {(form.type === "HYPERLIQUID") && (
          <FieldGroup label="Network">
            <select style={{ ...inputStyle, appearance: "none" }} value={form.network ?? "testnet"} onChange={e => set("network", e.target.value)}>
              <option value="testnet">Testnet</option>
              <option value="mainnet">Mainnet</option>
            </select>
          </FieldGroup>
        )}
        {(form.type === "METATRADER") && (<>
          <FieldGroup label="MetaAPI Token">
            <div style={{ position: "relative" }}>
              <input style={{ ...inputStyle, paddingRight: 36 }} placeholder="From metaapi.cloud dashboard"
                type={showSecret ? "text" : "password"}
                value={form.metaApiToken ?? ""} onChange={e => set("metaApiToken", e.target.value)} />
              <button type="button" onClick={() => setShowSecret(s => !s)}
                style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                  background: "none", border: "none", cursor: "pointer",
                  color: "rgba(255,255,255,0.3)", fontSize: 11, padding: 0 }}>
                {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </FieldGroup>
          <FieldGroup label="MetaAPI Account ID">
            <input style={inputStyle} placeholder="MT4/MT5 account ID on MetaAPI" value={form.metaApiAccountId ?? ""} onChange={e => set("metaApiAccountId", e.target.value)} />
          </FieldGroup>
        </>)}
        {(form.type === "POLYMARKET") && (
          <FieldGroup label="Ethereum Private Key (dedicated trading wallet)">
            <input style={inputStyle} type="password"
              placeholder="0x... — never paste your main wallet's key"
              value={form.apiKey ?? ""} onChange={e => set("apiKey", e.target.value)} />
            <p style={{ fontSize: 11, color: "rgba(251,191,36,0.7)", marginTop: 6, lineHeight: 1.5 }}>
              ⚠️ Use a fresh wallet funded only with USDC for trading. The key is encrypted
              with AES-256-GCM before storage. Connect Wallet (MetaMask) coming soon — no
              private key required.
            </p>
          </FieldGroup>
        )}
        {!(["METATRADER","ALPACA","IBKR"] as VenueType[]).includes(form.type!) && (
          <FieldGroup label="Passphrase (optional)">
            <div style={{ position: "relative" }}>
              <input style={{ ...inputStyle, paddingRight: 36 }} type={showSecret ? "text" : "password"}
                placeholder="Only for Coinbase, OKX, etc."
                value={form.apiPassphrase ?? ""} onChange={e => set("apiPassphrase", e.target.value)} />
              <button type="button" onClick={() => setShowSecret(s => !s)}
                style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                  background: "none", border: "none", cursor: "pointer",
                  color: "rgba(255,255,255,0.3)", padding: 0, display: "flex" }}>
                {showSecret ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </FieldGroup>
        )}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginTop: 4, marginBottom: 20 }}>
        <div
          onClick={() => set("isPaper", !form.isPaper)}
          style={{
            width: 36, height: 20, borderRadius: 10,
            background: form.isPaper ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.12)",
            position: "relative", transition: "background .2s", cursor: "pointer",
          }}
        >
          <div style={{
            position: "absolute", top: 2, left: form.isPaper ? 18 : 2, width: 16, height: 16,
            borderRadius: "50%", background: form.isPaper ? "#000" : "rgba(255,255,255,0.4)",
            transition: "left .2s",
          }} />
        </div>
        <span style={{ fontSize: 13, color: "rgba(255,255,255,0.5)" }}>Paper trading mode {form.isPaper ? "(safe)" : "(live)"}</span>
      </label>

      {/* Trust Signals */}
      <div style={{ marginTop: 6, marginBottom: 14, display: "flex", flexDirection: "column", gap: 6 }}>
        {[
          { icon: "🔒", text: "Your API key is encrypted with AES-256-GCM before storage — never stored in plain text." },
          { icon: "🚫", text: "QuantatraderAI never requests withdrawal permissions. Read-only + trade access only." },
          { icon: "🗑️", text: "You can revoke access anytime — delete the venue to permanently remove your credentials." },
        ].map(({ icon, text }) => (
          <div key={icon} style={{ display: "flex", alignItems: "flex-start", gap: 8,
            padding: "8px 12px", background: "rgba(74,222,128,0.04)",
            border: "1px solid rgba(74,222,128,0.1)", borderRadius: 8 }}>
            <span style={{ fontSize: 13, flexShrink: 0 }}>{icon}</span>
            <p style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", lineHeight: 1.5 }}>{text}</p>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <button style={btnPrimary} onClick={() => onSave(form)}>
          <Save size={13} /> Save Venue
        </button>
        <button style={btnOutline} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

/* ─── Risk Tab ───────────────────────────────────────────────────── */
function RiskTab({ venues }: { venues: Venue[] }) {
  const [selectedId, setSelectedId] = useState<string>("");
  const [risk, setRisk] = useState<Partial<RiskProfile>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!selectedId) return;
    fetch(`/api/venues/${selectedId}/risk`)
      .then(r => r.json())
      .then(d => setRisk(d))
      .catch(() => {});
  }, [selectedId]);

  const save = async () => {
    if (!selectedId) return;
    setSaving(true);
    await fetch(`/api/venues/${selectedId}/risk`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(risk),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const FIELDS: { key: keyof RiskProfile; label: string; step: number }[] = [
    { key: "maxPositionPct",          label: "Max Position Size (%)",          step: 0.5 },
    { key: "maxLeverage",             label: "Max Leverage (×)",               step: 0.5 },
    { key: "mandatorySlPct",          label: "Mandatory Stop-Loss (%)",        step: 0.5 },
    { key: "maxLossPerPositionPct",   label: "Max Loss Per Position (%)",      step: 0.5 },
    { key: "dailyLossCircuitBreaker", label: "Daily Loss Circuit Breaker (%)", step: 0.5 },
    { key: "maxTotalExposurePct",     label: "Max Total Exposure (%)",         step: 1   },
    { key: "maxConcurrentPositions",  label: "Max Concurrent Positions",       step: 1   },
  ];

  return (
    <div>
      <SectionTitle>Risk Settings per Venue</SectionTitle>
      {venues.length === 0 ? (
        <p style={{ fontSize: 14, color: "rgba(255,255,255,0.3)" }}>No connected venues yet. Add one in the Venues tab first.</p>
      ) : (
        <>
          <FieldGroup label="Select Venue">
            <DarkSelect
              value={selectedId}
              onChange={setSelectedId}
              placeholder="— choose a venue —"
              options={venues.map(v => ({ value: v.id, label: v.displayName, sub: VENUE_LABELS[v.type] }))}
              style={{ maxWidth: 340 }}
            />
          </FieldGroup>

          {selectedId && (
            <div style={card}>
              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
                {FIELDS.map(f => (
                  <FieldGroup key={f.key} label={f.label}>
                    <input
                      type="number" step={f.step} min={0} style={inputStyle}
                      value={(risk[f.key] as number) ?? ""}
                      onChange={e => setRisk(r => ({ ...r, [f.key]: parseFloat(e.target.value) }))}
                    />
                  </FieldGroup>
                ))}
              </div>
              <button style={btnPrimary} onClick={save} disabled={saving}>
                <Save size={13} /> {saving ? "Saving…" : saved ? "Saved ✓" : "Save Risk Config"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── Main Settings Page ─────────────────────────────────────────── */
const TABS = [
  { id: "profile",  label: "Profile",          icon: User   },
  { id: "venues",   label: "Connected Venues",  icon: Wifi   },
  { id: "risk",     label: "Risk Settings",     icon: Shield },
  { id: "alerts",   label: "Alerts",            icon: Bell   },
  { id: "security", label: "Security",          icon: Lock   },
] as const;

type TabId = typeof TABS[number]["id"];

export default function SettingsPage() {
  const toast = useToast();
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();
  const isMobile = useIsMobile();

  // Read URL query (?tab=venues&onboarding=1&venue=BINANCE)
  const initialTab     = (typeof window !== "undefined"
    ? (new URLSearchParams(window.location.search).get("tab") as TabId | null)
    : null) ?? "profile";
  const isOnboarding   = typeof window !== "undefined"
    && new URLSearchParams(window.location.search).get("onboarding") === "1";
  const onboardingVenue = typeof window !== "undefined"
    ? new URLSearchParams(window.location.search).get("venue")
    : null;

  const [tab, setTab] = useState<TabId>(initialTab);

  const [venues, setVenues]       = useState<Venue[]>([]);
  const [showVenueForm, setShowVenueForm] = useState(false);

  // C2: First-run UX — auto-open the add-venue form and pre-select the chosen type
  useEffect(() => {
    if (isOnboarding && tab === "venues" && venues.length === 0) {
      setShowVenueForm(true);
    }
  }, [isOnboarding, tab, venues.length]);

  const [alertSettings, setAlertSettings] = useState<Partial<UserSettings>>({});
  const [alertSaving, setAlertSaving]   = useState(false);
  const [alertSaved, setAlertSaved]     = useState(false);

  const [profileName, setProfileName] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved]   = useState(false);

  useEffect(() => {
    if (user?.fullName) setProfileName(user.fullName);
  }, [user]);

  const loadVenues = useCallback(() => {
    fetch("/api/venues").then(r => r.json()).then(d => Array.isArray(d) && setVenues(d)).catch(() => {});
  }, []);

  const loadAlerts = useCallback(() => {
    fetch("/api/user/settings").then(r => r.json()).then(d => d && !d.error && setAlertSettings(d)).catch(() => {});
  }, []);

  useEffect(() => { loadVenues(); loadAlerts(); }, [loadVenues, loadAlerts]);

  const saveVenue = async (form: Partial<Venue>) => {
    const res = await fetch("/api/venues", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await res.json().catch(() => ({})) as {
      connectionTest?: { ok: boolean; balance?: number; currency?: string; error?: string; warning?: string };
      error?: string;
    };
    if (!res.ok) {
      toast(data.error ?? "Could not save venue", "error");
      return;
    }
    // Surface auto-test result
    if (data.connectionTest?.ok) {
      const bal = data.connectionTest.balance != null
        ? `Balance: ${data.connectionTest.balance} ${data.connectionTest.currency ?? ""}`
        : "Connection verified";
      toast(`Venue saved. ${bal}`, "success");
      if (data.connectionTest.warning) {
        toast(data.connectionTest.warning, "warning");
      }
    } else if (data.connectionTest?.error) {
      toast(`Saved, but connection test failed: ${data.connectionTest.error}`, "warning");
    } else {
      toast("Venue saved", "success");
    }
    setShowVenueForm(false);
    loadVenues();
  };

  const deleteVenue = async (id: string) => {
    await fetch(`/api/venues/${id}`, { method: "DELETE" });
    loadVenues();
  };

  const togglePaper = async (v: Venue) => {
    await fetch(`/api/venues/${v.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isPaper: !v.isPaper }),
    });
    loadVenues();
  };

  const saveAlerts = async () => {
    setAlertSaving(true);
    await fetch("/api/user/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(alertSettings),
    });
    setAlertSaving(false);
    setAlertSaved(true);
    setTimeout(() => setAlertSaved(false), 2000);
  };

  const saveProfile = async () => {
    if (!user) return;
    setProfileSaving(true);
    await user.update({ firstName: profileName.split(" ")[0], lastName: profileName.split(" ").slice(1).join(" ") || undefined });
    setProfileSaving(false);
    setProfileSaved(true);
    setTimeout(() => setProfileSaved(false), 2000);
  };

  const clerkAppearance = {
    variables: {
      colorBackground: "rgba(10,10,10,0.9)",
      colorInputBackground: "rgba(255,255,255,0.04)",
      colorInputText: "#ffffff",
      colorText: "#ffffff",
      colorTextSecondary: "rgba(255,255,255,0.5)",
      colorPrimary: "#ffffff",
      borderRadius: "12px",
      fontFamily: "inherit",
    },
    elements: {
      card: { background: "transparent", border: "none", boxShadow: "none", padding: 0 },
      headerTitle: { color: "#ffffff" },
      headerSubtitle: { color: "rgba(255,255,255,0.45)" },
      formButtonPrimary: { background: "#ffffff", color: "#000000", fontWeight: "600" },
      formFieldInput: { background: "rgba(255,255,255,0.04)", borderColor: "rgba(255,255,255,0.1)", color: "#ffffff" },
      formFieldLabel: { color: "rgba(255,255,255,0.55)" },
      footerActionLink: { color: "rgba(255,255,255,0.6)" },
      navbar: { background: "transparent" },
      navbarButton: { color: "rgba(255,255,255,0.5)" },
      navbarButtonActive: { color: "#ffffff" },
      rootBox: { width: "100%" },
    },
  };

  if (!isLoaded) {
    return (
      <div style={{ background: "#000", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "rgba(255,255,255,0.3)", fontSize: 14 }}>Loading…</div>
      </div>
    );
  }

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#fff" }}>
      {/* Header */}
      <header style={{
        position: "sticky", top: 0, zIndex: 50,
        background: "rgba(0,0,0,0.88)", backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        padding: isMobile ? "0 12px" : "0 28px", height: 60,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <Link href="/" style={{ textDecoration: "none" }}><LogoWordmark size={28} /></Link>
        <Link href="/dashboard" style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          fontSize: 13, color: "rgba(255,255,255,0.4)", textDecoration: "none",
        }}>
          <ArrowLeft size={13} /> Dashboard
        </Link>
      </header>

      {/* Horizontal tab bar (mobile) */}
      {isMobile && (
        <div style={{
          overflowX: "auto", display: "flex", gap: 4,
          padding: "12px 12px 0",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          scrollbarWidth: "none",
        }}>
          {TABS.map(t => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", borderRadius: "10px 10px 0 0", border: "none",
                  borderBottom: active ? "2px solid #fff" : "2px solid transparent",
                  background: active ? "rgba(255,255,255,0.06)" : "transparent",
                  color: active ? "#fff" : "rgba(255,255,255,0.4)",
                  fontSize: 12, fontWeight: active ? 600 : 400,
                  cursor: "pointer", whiteSpace: "nowrap", transition: "all .15s",
                  flexShrink: 0,
                }}
              >
                <Icon size={13} /> {t.label}
              </button>
            );
          })}
        </div>
      )}

      <div style={{ maxWidth: 1000, margin: "0 auto", padding: isMobile ? "20px 12px 60px" : "40px 28px 80px", display: isMobile ? "block" : "grid", gridTemplateColumns: "200px 1fr", gap: 40, alignItems: "start" }}>

        {/* ── Mobile tab selector (dropdown) ── */}
        {isMobile && (
          <div style={{ marginBottom: 20 }}>
            <select
              value={tab}
              onChange={e => setTab(e.target.value as TabId)}
              style={{
                width: "100%", padding: "13px 16px", borderRadius: 12,
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "#fff", fontSize: 14, fontWeight: 600,
                cursor: "pointer", outline: "none",
                appearance: "none", WebkitAppearance: "none",
                backgroundImage: "url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.4)' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")",
                backgroundRepeat: "no-repeat",
                backgroundPosition: "right 14px center",
                paddingRight: 40,
              }}
            >
              {TABS.map(t => (
                <option key={t.id} value={t.id} style={{ background: "#111", color: "#fff" }}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Sidebar tabs (desktop only) */}
        {!isMobile && (
        <aside style={{ position: "sticky", top: 80 }}>
          <p style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: "rgba(255,255,255,0.25)", marginBottom: 12 }}>
            Settings
          </p>
          <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {TABS.map(t => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "9px 12px", borderRadius: 10, border: "none",
                    background: active ? "rgba(255,255,255,0.07)" : "transparent",
                    color: active ? "#fff" : "rgba(255,255,255,0.4)",
                    fontSize: 13, fontWeight: active ? 600 : 400,
                    cursor: "pointer", textAlign: "left", transition: "all .15s",
                  }}
                >
                  <Icon size={14} /> {t.label}
                </button>
              );
            })}
          </nav>
        </aside>
        )}

        {/* Main content */}
        <main>

          {/* ── Profile ── */}
          {tab === "profile" && (
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, letterSpacing: "-0.02em" }}>Profile</h2>
              <div style={card}>
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
                  {user?.imageUrl && (
                    <img src={user.imageUrl} alt="avatar" style={{ width: 60, height: 60, borderRadius: "50%", objectFit: "cover", border: "1px solid rgba(255,255,255,0.1)" }} />
                  )}
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600 }}>{user?.fullName || "—"}</div>
                    <div style={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>{user?.primaryEmailAddress?.emailAddress}</div>
                  </div>
                </div>
                <FieldGroup label="Full Name">
                  <input style={{ ...inputStyle, maxWidth: 360 }} value={profileName} onChange={e => setProfileName(e.target.value)} />
                </FieldGroup>
                <FieldGroup label="Email">
                  <input style={{ ...inputStyle, maxWidth: 360, opacity: 0.45, cursor: "not-allowed" }} value={user?.primaryEmailAddress?.emailAddress ?? ""} readOnly />
                </FieldGroup>
                <button style={btnPrimary} onClick={saveProfile} disabled={profileSaving}>
                  <Save size={13} /> {profileSaving ? "Saving…" : profileSaved ? "Saved ✓" : "Save Changes"}
                </button>
              </div>
            </div>
          )}

          {/* ── Connected Venues ── */}
          {tab === "venues" && (
            <div>
              {/* M2: Onboarding banner — clear next-action for first-time users */}
              {isOnboarding && venues.length === 0 && (
                <div style={{
                  background: "rgba(74,222,128,0.05)", border: "1px solid rgba(74,222,128,0.2)",
                  borderRadius: 14, padding: "16px 20px", marginBottom: 20,
                  display: "flex", alignItems: "center", gap: 14,
                }}>
                  <div style={{ width: 32, height: 32, borderRadius: "50%",
                    background: "rgba(74,222,128,0.15)", border: "1px solid rgba(74,222,128,0.4)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 13, fontWeight: 700, color: "#4ade80", flexShrink: 0 }}>3</div>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                      Last step — connect your {onboardingVenue ?? "exchange"} API key
                    </p>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 2 }}>
                      Your API key is encrypted with AES-256-GCM before it touches our servers. We never see it in plaintext.
                    </p>
                  </div>
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <h2 style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.02em" }}>Connected Venues</h2>
                {!showVenueForm && (
                  <button style={btnPrimary} onClick={() => setShowVenueForm(true)}>
                    <Plus size={13} /> Add Venue
                  </button>
                )}
              </div>

              {showVenueForm && <VenueForm onSave={saveVenue} onCancel={() => setShowVenueForm(false)} initialType={onboardingVenue ?? undefined} />}

              {venues.length === 0 && !showVenueForm ? (
                <div style={{ ...card, textAlign: "center", padding: "48px 28px" }}>
                  <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 14, marginBottom: 16 }}>No venues connected yet.</p>
                  <button style={btnPrimary} onClick={() => setShowVenueForm(true)}><Plus size={13} /> Add Your First Venue</button>
                </div>
              ) : (
                venues.map(v => (
                  <div key={v.id} style={{ ...card, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 15, fontWeight: 600 }}>{v.displayName}</span>
                        <span style={{
                          fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
                          textTransform: "uppercase", padding: "2px 8px", borderRadius: 6,
                          background: "rgba(255,255,255,0.07)", color: "rgba(255,255,255,0.5)",
                        }}>{VENUE_LABELS[v.type]}</span>
                      </div>
                      <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", marginTop: 4 }}>
                        {v.network && <span style={{ marginRight: 10 }}>{v.network}</span>}
                        Key: {v.apiKey.slice(0, 8)}…
                      </div>
                      <div style={{ display: "flex", gap: 5, marginTop: 6, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
                          padding: "2px 7px", borderRadius: 4, textTransform: "uppercase",
                          background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.2)",
                          color: "#4ade80" }}>
                          🔒 AES-256 Encrypted
                        </span>
                        <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
                          padding: "2px 7px", borderRadius: 4, textTransform: "uppercase",
                          background: "rgba(74,222,128,0.05)", border: "1px solid rgba(74,222,128,0.15)",
                          color: "rgba(74,222,128,0.7)" }}>
                          🚫 No Withdrawal Access
                        </span>
                        {v.isPaper ? (
                          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
                            padding: "2px 7px", borderRadius: 4, textTransform: "uppercase",
                            background: "rgba(129,140,248,0.08)", border: "1px solid rgba(129,140,248,0.2)",
                            color: "#818cf8" }}>
                            PAPER MODE
                          </span>
                        ) : (
                          <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
                            padding: "2px 7px", borderRadius: 4, textTransform: "uppercase",
                            background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
                            color: "#ef4444" }}>
                            ● LIVE
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      {/* Test connection */}
                      <button
                        onClick={async () => {
                          const r = await fetch(`/api/venues/${v.id}/test`, { method: "POST" }).catch(() => null);
                          const data = await r?.json().catch(() => null) as {
                            ok: boolean; balance?: number; currency?: string;
                            error?: string; warning?: string;
                          } | null;
                          if (data?.ok) {
                            const bal = data.balance != null ? `Balance: ${data.balance?.toFixed(4)} ${data.currency ?? ""}` : "Connection verified";
                            toast(`✓ ${bal}`, "success");
                            if (data.warning) toast(`⚠️ ${data.warning}`, "warning");
                          } else {
                            toast(`❌ ${data?.error ?? "Connection failed"}`, "error");
                          }
                        }}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 6,
                          padding: "6px 12px", borderRadius: 8,
                          background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)",
                          color: "#60a5fa", fontSize: 12, fontWeight: 500, cursor: "pointer",
                        }}
                      >
                        <Wifi size={11} /> Test
                      </button>
                      {/* Phase 5: Paper / Live / Testnet pill */}
                      {(() => {
                        const isTestnet = !v.isPaper && (
                          (v.type === "HYPERLIQUID" && v.network === "testnet") ||
                          (["BINANCE","BYBIT","OKX","KRAKEN","COINBASE","CCXT"].includes(v.type))
                        ) && v.isPaper;
                        const label = v.isPaper
                          ? (v.type === "HYPERLIQUID" && v.network === "testnet" ? "Testnet" : "Paper")
                          : "Live";
                        const bg    = v.isPaper ? "rgba(74,222,128,0.08)"  : "rgba(239,68,68,0.1)";
                        const bdr   = v.isPaper ? "rgba(74,222,128,0.25)"  : "rgba(239,68,68,0.3)";
                        const clr   = v.isPaper ? "#4ade80"                : "#f87171";
                        return (
                          <button onClick={() => togglePaper(v)}
                            title={v.isPaper ? "Click to switch to live trading" : "Click to switch to paper mode"}
                            style={{ display: "inline-flex", alignItems: "center", gap: 5,
                              padding: "4px 10px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                              background: bg, border: `1px solid ${bdr}`, color: clr,
                              cursor: "pointer", letterSpacing: "0.04em" }}>
                            <span style={{ width: 5, height: 5, borderRadius: "50%",
                              background: clr, flexShrink: 0 }} />
                            {label}
                          </button>
                        );
                      })()}
                      <button onClick={() => deleteVenue(v.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.25)", padding: 6 }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* ── Risk ── */}
          {tab === "risk" && (
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, letterSpacing: "-0.02em" }}>Risk Settings</h2>
              <RiskTab venues={venues} />
            </div>
          )}

          {/* ── Alerts ── */}
          {tab === "alerts" && (
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, letterSpacing: "-0.02em" }}>Alerts & Notifications</h2>

              {/* ── Telegram ── */}
              <div style={{ ...card, marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
                  <div style={{ width: 36, height: 36, borderRadius: "50%", background: "rgba(37,211,102,0.1)", border: "1px solid rgba(37,211,102,0.25)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>✈</div>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>Telegram Alerts</div>
                    <div style={{ fontSize: 12, color: "rgba(255,255,255,0.35)" }}>Instant notifications for every trade, stop loss, and agent event</div>
                  </div>
                  {alertSettings.telegramChatId && (
                    <div style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: "#4ade80", background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.2)", borderRadius: 20, padding: "3px 10px" }}>Connected ✓</div>
                  )}
                </div>

                {/* Step-by-step instructions */}
                <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 12, padding: "16px 18px", marginBottom: 20 }}>
                  <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 14 }}>3 steps to connect</p>
                  {[
                    { n: 1, title: "Start the bot", body: <span>Open Telegram and start <a href="https://t.me/QuantatraderAI_bot" target="_blank" rel="noopener noreferrer" style={{ color: "#4ade80", textDecoration: "none", fontWeight: 600 }}>@QuantatraderAI_bot</a> — tap Start or send any message.</span> },
                    { n: 2, title: "Get your Chat ID", body: <span>Message <a href="https://t.me/userinfobot" target="_blank" rel="noopener noreferrer" style={{ color: "#4ade80", textDecoration: "none", fontWeight: 600 }}>@userinfobot</a> on Telegram. It will instantly reply with your Chat ID — a number like <span style={{ fontFamily: "monospace", color: "rgba(255,255,255,0.6)" }}>1234567890</span>. Copy it.</span> },
                    { n: 3, title: "Paste it below", body: "Enter your Chat ID in the field below and click Save. That's it — alerts will start arriving immediately." },
                  ].map(step => (
                    <div key={step.n} style={{ display: "flex", gap: 14, marginBottom: 16 }}>
                      <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#4ade80", flexShrink: 0 }}>{step.n}</div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.75)", marginBottom: 3 }}>{step.title}</div>
                        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", lineHeight: 1.6 }}>{step.body}</div>
                      </div>
                    </div>
                  ))}
                </div>

                <FieldGroup label="Your Telegram Chat ID">
                  <input
                    style={inputStyle}
                    placeholder="e.g. 1234567890"
                    value={alertSettings.telegramChatId ?? ""}
                    onChange={e => setAlertSettings(s => ({ ...s, telegramChatId: e.target.value }))}
                  />
                </FieldGroup>

                {/* What you'll receive */}
                <div style={{ marginBottom: 20 }}>
                  <p style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.25)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>You will receive alerts for</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {["Trade opened", "Trade closed", "Stop loss hit", "Circuit breaker", "Agent started", "Agent stopped", "Risk block"].map(ev => (
                      <span key={ev} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 20, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.4)" }}>{ev}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* ── Email ── */}
              <div style={{ ...card, marginBottom: 16 }}>
                <SectionTitle>Email Notifications</SectionTitle>
                <label style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer", marginBottom: 8 }}>
                  <div
                    onClick={() => setAlertSettings(s => ({ ...s, emailNotifications: !s.emailNotifications }))}
                    style={{ width: 40, height: 22, borderRadius: 11, background: alertSettings.emailNotifications ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.12)", position: "relative", transition: "background .2s", cursor: "pointer", flexShrink: 0 }}
                  >
                    <div style={{ position: "absolute", top: 3, left: alertSettings.emailNotifications ? 21 : 3, width: 16, height: 16, borderRadius: "50%", background: alertSettings.emailNotifications ? "#000" : "rgba(255,255,255,0.4)", transition: "left .2s" }} />
                  </div>
                  <span style={{ fontSize: 13, color: "rgba(255,255,255,0.55)" }}>
                    Email notifications {alertSettings.emailNotifications ? "enabled" : "disabled"}
                  </span>
                </label>
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.25)", lineHeight: 1.6 }}>
                  Weekly performance reports and agent alerts sent to your registered email address.
                </p>
              </div>

              <button style={btnPrimary} onClick={saveAlerts} disabled={alertSaving}>
                <Save size={13} /> {alertSaving ? "Saving…" : alertSaved ? "Saved ✓" : "Save Alert Settings"}
              </button>
            </div>
          )}

          {/* ── Security ── */}
          {tab === "security" && (
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 24, letterSpacing: "-0.02em" }}>Security</h2>
              <UserProfile routing="hash" appearance={clerkAppearance} />

              {/* Sign out */}
              <div style={{ marginTop: 32, paddingTop: 24, borderTop: "1px solid var(--border)" }}>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>
                  Signed in as <strong style={{ color: "rgba(255,255,255,0.7)" }}>{user?.primaryEmailAddress?.emailAddress}</strong>
                </p>
                <button
                  onClick={async () => {
                    // Clear server-side caches before Clerk drops the session
                    await fetch("/api/auth/signout", { method: "POST", credentials: "same-origin" }).catch(() => {});
                    signOut({ redirectUrl: "/" });
                  }}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 8,
                    background: "rgba(239,68,68,0.1)",
                    border: "1px solid rgba(239,68,68,0.3)",
                    color: "#ef4444",
                    borderRadius: 10, padding: "10px 20px",
                    fontSize: 14, fontWeight: 600, cursor: "pointer",
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(239,68,68,0.18)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(239,68,68,0.1)")}
                >
                  Sign out of QuantatraderAI
                </button>
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}
