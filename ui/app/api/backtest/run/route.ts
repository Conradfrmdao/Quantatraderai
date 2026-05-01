import { requirePlan } from "@/lib/plan-guard";
import { rateLimit }   from "@/lib/rate-limit";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const guard = await requirePlan("backtesting");
  if (!guard.allowed) return guard.response;

  // M13: 10 backtests per hour per user
  const rl = rateLimit(guard.userId, "backtest", 10, 3_600_000);
  if (!rl.allowed) {
    return Response.json(
      { error: `Rate limit: max 10 backtests/hour. Resets in ${Math.ceil(rl.resetIn / 60000)} min.` },
      { status: 429, headers: { "Retry-After": String(Math.ceil(rl.resetIn / 1000)) } },
    );
  }

  const body = await req.json();

  // Forward with a generous 120s timeout — backtests can take time
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const res = await fetch(`${PYTHON_API}/api/backtest/run`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });
    clearTimeout(timeout);
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch (err) {
    clearTimeout(timeout);
    if ((err as Error).name === "AbortError") {
      return Response.json({ error: "Backtest timed out (>120 s)" }, { status: 504 });
    }
    return Response.json({ error: "Backend unreachable" }, { status: 502 });
  }
}
