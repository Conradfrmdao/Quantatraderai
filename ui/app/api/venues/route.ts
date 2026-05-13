/**
 * Venues API — list/create user-scoped venues.
 *
 * SECURITY:
 *   - GET never returns decrypted secrets (apiKey/apiSecret/apiPassphrase/metaApiToken).
 *     Only a masked preview ("ABCD…1234") is sent to the client.
 *   - Auth resolved via Clerk auth() on every call — no cached identity.
 *   - All writes scoped by the authenticated user's Prisma id.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { VenueType } from "@prisma/client";
import { encrypt } from "@/lib/encryption";
import { getPlanLimits, type Plan } from "@/lib/plan-limits";
import {
  getVenueCapability,
  getVenueCatalog,
  normalizeVenueMarket,
} from "@/lib/server/venue-capabilities";

function normalizePaperCapital(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return 10_000;
  return Math.min(10_000_000, Math.max(100, parsed));
}

/** Mask a value for safe display: "abcd…wxyz" */
function maskSecret(s: string | null | undefined): string {
  if (!s || s.length < 8) return s ? "••••" : "";
  // Don't decrypt — just show that something is set
  return "••••••••";
}

async function resolveUser() {
  const { userId: clerkId } = await auth();
  if (!clerkId) return null;
  return prisma.user.findUnique({
    where: { clerkId },
    select: { id: true, plan: true },
  });
}

export async function GET() {
  const user = await resolveUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const venues = await prisma.venue.findMany({
    where: { userId: user.id },
    include: { riskProfile: true },
    orderBy: { createdAt: "asc" },
  });

  const catalog = getVenueCatalog();

  // SECURITY: scrub all sensitive fields before sending to client
  const safe = venues.map(v => ({
    id:               v.id,
    displayName:      v.displayName,
    type:             v.type,
    accountId:        v.accountId,
    ccxtExchangeId:   v.ccxtExchangeId,
    network:          v.network,
    market:           v.market,
    paperCapital:     v.paperCapital,
    metaApiAccountId: v.metaApiAccountId,
    isPaper:          v.isPaper,
    isActive:         v.isActive,
    createdAt:        v.createdAt,
    updatedAt:        v.updatedAt,
    apiKey:           maskSecret(v.apiKey),
    apiSecret:        maskSecret(v.apiSecret),
    apiPassphrase:    v.apiPassphrase ? "••••" : "",
    metaApiToken:     v.metaApiToken  ? "••••" : "",
    hasApiKey:        Boolean(v.apiKey),
    hasApiSecret:     Boolean(v.apiSecret),
    riskProfile:      v.riskProfile,
    capability:       getVenueCapability(v.type),
  }));
  return NextResponse.json({ venues: safe, catalog });
}

export async function POST(req: Request) {
  const { userId: clerkId } = await auth();
  if (!clerkId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const user = await prisma.user.findUnique({
    where: { clerkId }, select: { id: true, plan: true },
  });
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const limits     = getPlanLimits((user.plan ?? "FREE") as Plan);
  const venueCount = await prisma.venue.count({ where: { userId: user.id } });
  if (venueCount >= limits.maxVenues) {
    return NextResponse.json({
      error: `You have reached the venue limit (${limits.maxVenues}) for your plan. Upgrade to add more.`,
      current: venueCount, max: limits.maxVenues, upgrade_url: "/billing",
    }, { status: 402 });
  }

  // First venue is auto-activated — user doesn't need to toggle anything.
  const isFirstVenue = venueCount === 0;

  const body = await req.json() as {
    displayName: string;
    type: VenueType;
    apiKey: string;
    apiSecret: string;
    apiPassphrase?: string;
    accountId?: string;
    ccxtExchangeId?: string;
    network?: string;
    market?: string;
    paperCapital?: number;
    isPaper?: boolean;
    metaApiToken?: string;
    metaApiAccountId?: string;
  };

  if (!body.displayName?.trim() || !body.type) {
    return NextResponse.json({ error: "displayName and type are required" }, { status: 400 });
  }

  const market = normalizeVenueMarket(body.type, body.market);

  const venue = await prisma.venue.create({
    data: {
      userId:           user.id,
      displayName:      body.displayName.trim(),
      type:             body.type,
      apiKey:           body.apiKey        ? encrypt(body.apiKey)        : "",
      apiSecret:        body.apiSecret     ? encrypt(body.apiSecret)     : "",
      apiPassphrase:    body.apiPassphrase ? encrypt(body.apiPassphrase) : null,
      accountId:        body.accountId        ?? null,
      ccxtExchangeId:   body.ccxtExchangeId   ?? null,
      network:          body.network          ?? null,
      market,
      paperCapital:     normalizePaperCapital(body.paperCapital),
      metaApiToken:     body.metaApiToken     ? encrypt(body.metaApiToken) : null,
      metaApiAccountId: body.metaApiAccountId ?? null,
      isPaper:          body.isPaper          ?? true,
      isActive:         isFirstVenue,
    },
    include: { riskProfile: true },
  });

  // Phase 3: Audit log — venue connected (key masked, never raw)
  prisma.auditLog.create({
    data: {
      userId: user.id, event: "venue_connected", symbol: null, action: null,
      data: JSON.stringify({
        venueId: venue.id, type: venue.type, displayName: venue.displayName,
        isPaper: venue.isPaper, network: venue.network, market: venue.market,
        keyMasked: body.apiKey ? `${body.apiKey.slice(0, 4)}…${body.apiKey.slice(-4)}` : "",
      }),
    },
  }).catch(() => {});

  // Phase 3: Auto-test the connection inline. If it fails we keep the venue
  // (so the user can fix the credentials), but surface the error in the response
  // so the UI can show it in a toast.
  const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";
  const TYPE_TO_REGISTRY: Record<string, string> = {
    HYPERLIQUID: "hyperliquid", BINANCE: "binance", BYBIT: "bybit", OKX: "okx",
    KRAKEN: "kraken", COINBASE: "coinbase", OANDA: "oanda", METATRADER: "metatrader",
    ALPACA: "alpaca", IBKR: "ibkr", CCXT: "ccxt", POLYMARKET: "polymarket",
  };
  let connectionTest: { ok: boolean; balance?: number; currency?: string; error?: string; warning?: string } | null = null;
  try {
    const ctrl = new AbortController();
    const t    = setTimeout(() => ctrl.abort(), 12_000);
    const res  = await fetch(`${PYTHON_API}/api/venues/test`, {
      method:  "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
        "x-user-id": clerkId,
      },
      body: JSON.stringify({
        userId: clerkId,
        venue:  TYPE_TO_REGISTRY[venue.type] ?? "binance",
        isPaper: venue.isPaper,
      }),
      signal: ctrl.signal,
    });
    clearTimeout(t);
    connectionTest = await res.json();
  } catch (e) {
    console.error("[venues] connection test", e);
    connectionTest = { ok: false, error: "Connection test timed out — saved anyway. Click Test to retry." };
  }

  // Return safe version (no secrets)
  return NextResponse.json({
    id:               venue.id,
    displayName:      venue.displayName,
    type:             venue.type,
    accountId:        venue.accountId,
    ccxtExchangeId:   venue.ccxtExchangeId,
    network:          venue.network,
    market:           venue.market,
    paperCapital:     venue.paperCapital,
    metaApiAccountId: venue.metaApiAccountId,
    isPaper:          venue.isPaper,
    isActive:         venue.isActive,
    createdAt:        venue.createdAt,
    apiKey:           maskSecret(venue.apiKey),
    apiSecret:        maskSecret(venue.apiSecret),
    hasApiKey:        Boolean(venue.apiKey),
    hasApiSecret:     Boolean(venue.apiSecret),
    riskProfile:      venue.riskProfile,
    capability:       getVenueCapability(venue.type),
    connectionTest,
  }, { status: 201 });
}
