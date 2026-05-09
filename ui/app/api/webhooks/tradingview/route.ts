/**
 * TradingView webhook receiver.
 *
 * In TradingView Pine Script, set your alert message to JSON:
 *   {"action":"buy","symbol":"BTCUSDT","size":500,"venueId":"<your-venue-id>","secret":"<TRADINGVIEW_WEBHOOK_SECRET>"}
 *
 * Point the webhook URL to: https://yourdomain.com/api/webhooks/tradingview
 *
 * Required env var:
 *   TRADINGVIEW_WEBHOOK_SECRET — shared secret you set in TradingView alert
 *
 * The signal is forwarded to the Python backend's risk validation pipeline
 * (same RiskManager guards as autonomous agent decisions).
 *
 * SECURITY: userId is never accepted from the webhook payload to prevent
 * user_id spoofing. The Python backend must resolve the target user at
 * configuration time, not at request time.
 */

const TV_SECRET = process.env.TRADINGVIEW_WEBHOOK_SECRET;
const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

interface TVSignal {
  secret:   string;
  action:   "buy" | "sell" | "close";
  symbol:   string;
  size?:    number;      // USD allocation
  tp?:      number;
  sl?:      number;
  venueId?: string;      // optional: target a specific venue
  // userId intentionally removed — accepting userId from webhook payload
  // allows anyone with the secret to trigger trades for arbitrary users.
}

export async function POST(req: Request) {
  // 1. Parse body
  let signal: TVSignal;
  try {
    signal = await req.json() as TVSignal;
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // 2. Validate shared secret
  if (!TV_SECRET) {
    return Response.json({ error: "Webhook not configured" }, { status: 500 });
  }
  if (signal.secret !== TV_SECRET) {
    return Response.json({ error: "Invalid secret" }, { status: 401 });
  }

  // 3. Validate required fields
  if (!signal.action || !signal.symbol) {
    return Response.json({ error: "Missing action or symbol" }, { status: 400 });
  }
  if (!["buy", "sell", "close"].includes(signal.action)) {
    return Response.json({ error: "action must be buy | sell | close" }, { status: 400 });
  }

  // 4. Forward to Python risk pipeline
  // SECURITY: user_id is NOT forwarded from the webhook payload.
  // The Python backend must resolve the target user from its own configuration.
  try {
    const pyRes = await fetch(`${PYTHON_API}/api/agent/execute-signal`, {
      method:  "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      },
      body: JSON.stringify({
        source:   "tradingview",
        action:   signal.action,
        symbol:   signal.symbol,
        size_usd: signal.size ?? 0,
        tp_price: signal.tp ?? null,
        sl_price: signal.sl ?? null,
        venue_id: signal.venueId ?? null,
      }),
    });

    const result = await pyRes.json().catch(() => ({}));
    return Response.json({ ok: true, result }, { status: 200 });
  } catch (err) {
    console.error("TradingView webhook forward failed:", err);
    return Response.json({ error: "Python backend unavailable" }, { status: 502 });
  }
}
