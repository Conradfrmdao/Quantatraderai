/**
 * Live mid-market price proxy — fetches real-time price from the user's
 * connected venue (OANDA, MetaTrader, Alpaca etc.) so the chart shows
 * the same price the user sees in their broker account.
 *
 * GET /api/price/live?symbol=EURUSD&venue=oanda
 */
import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const url    = new URL(req.url);
  const symbol = url.searchParams.get("symbol");
  const venue  = url.searchParams.get("venue");
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 });

  try {
    const ctrl = new AbortController();
    const t    = setTimeout(() => ctrl.abort(), 4000);
    const qs   = new URLSearchParams({ symbol, userId });
    if (venue) qs.set("venue", venue);

    const res = await fetch(`${PYTHON_API}/api/price/live?${qs.toString()}`, {
      signal: ctrl.signal,
      headers: { "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "" },
      cache: "no-store",
    });
    clearTimeout(t);

    if (!res.ok) {
      return NextResponse.json({ error: "Price unavailable" }, { status: 502 });
    }
    const data = await res.json();
    return NextResponse.json(data, {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (e) {
    console.error("[price/live]", e);
    return NextResponse.json({ error: "Service temporarily unavailable" }, { status: 502 });
  }
}
