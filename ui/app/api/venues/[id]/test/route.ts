/**
 * Test venue connection — ask the Python backend to fetch balance + symbol meta
 * using the stored credentials. Returns { ok, balance?, error? }.
 */

import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

const TYPE_TO_REGISTRY: Record<string, string> = {
  HYPERLIQUID: "hyperliquid", BINANCE: "binance", BYBIT: "bybit", OKX: "okx",
  KRAKEN: "kraken", COINBASE: "coinbase", OANDA: "oanda", METATRADER: "metatrader",
  ALPACA: "alpaca", IBKR: "ibkr", CCXT: "ccxt", POLYMARKET: "polymarket",
};

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { user } = await getAuthenticatedUser();
  const { id }   = await params;

  const venue = await prisma.venue.findFirst({
    where:  { id, userId: user.id },
    select: { type: true, isPaper: true },
  });
  if (!venue) return Response.json({ ok: false, error: "Venue not found" }, { status: 404 });

  const registry = TYPE_TO_REGISTRY[venue.type] ?? "binance";

  try {
    const res = await fetch(`${PYTHON_API}/api/venues/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: user.clerkId,
        venue:  registry,
        isPaper: venue.isPaper,
      }),
    });
    const data = await res.json();

    // Audit log: venue test attempted
    prisma.auditLog.create({
      data: {
        userId: user.id, event: "venue_tested", symbol: null,
        action: data?.ok ? "success" : "failure",
        data: JSON.stringify({
          venueId: id, type: venue.type, isPaper: venue.isPaper,
          ok: !!data?.ok,
          ...(data?.ok ? { currency: data.currency, balance: data.balance } : { error: data?.error }),
        }),
      },
    }).catch(() => {});

    return Response.json(data, { status: res.status });
  } catch (e) {
    return Response.json({ ok: false, error: String(e) }, { status: 502 });
  }
}
