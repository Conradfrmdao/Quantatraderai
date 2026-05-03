import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { getPlanLimits } from "@/lib/plan-limits";
import { rateLimit } from "@/lib/rate-limit";

const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";

// Agent-control verbs live at /api/agent/* on Python. Everything else (account,
// positions, status, risk, decisions, candles, calendar, etc.) lives at /api/*.
const AGENT_VERBS = new Set([
  "start", "stop", "killswitch",
  "timeline", "personas", "pending-order", "trust",
  "execute-signal", "strategies",
]);

function buildPythonPath(subpath: string): string {
  // If the first segment is an agent verb, forward as /api/agent/<verb>.
  // Otherwise, forward as /api/<rest>.
  const first = subpath.split("/")[0] ?? "";
  if (AGENT_VERBS.has(first)) {
    return `/api/agent/${subpath}`;
  }
  return `/api/${subpath}`;
}

async function proxy(req: NextRequest, params: { path: string[] }) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const subpath = params.path.join("/");

  // ── Rate limits + plan enforcement on agent-control endpoints ─────────────
  if (subpath === "start" && req.method === "POST") {
    const rl = rateLimit(userId, "agent_start", 20, 3_600_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many agent starts. Max 20/hour. Retry in ${Math.ceil(rl.resetIn / 60000)} min.` },
        { status: 429 },
      );
    }
  }

  if (subpath === "killswitch" && req.method === "POST") {
    const rl = rateLimit(userId, "killswitch", 5, 300_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Kill switch rate-limited. Max 5/5min. Wait ${Math.ceil(rl.resetIn / 1000)}s.` },
        { status: 429 },
      );
    }
  }

  // Plan enforcement on agent/start — FAIL CLOSED
  if (subpath === "start" && req.method === "POST") {
    const dbUser = await prisma.user.findUnique({ where: { clerkId: userId }, select: { plan: true } });
    const plan   = (dbUser?.plan as "FREE" | "STARTER" | "PRO" | "ENTERPRISE") ?? "FREE";
    const limits = getPlanLimits(plan);
    const body   = await req.clone().json().catch(() => ({})) as { isPaper?: boolean; symbols?: string[] };

    if (!limits.liveTrading && body.isPaper !== true) {
      return NextResponse.json({
        error:         "Upgrade to Starter or higher to enable live trading. FREE plan must explicitly set isPaper=true.",
        plan_required: "STARTER",
        upgrade_url:   "/billing",
      }, { status: 402 });
    }
    const symbols = body.symbols ?? [];
    if (symbols.length > limits.maxAssets) {
      return NextResponse.json({
        error:         `Your ${plan} plan allows max ${limits.maxAssets} asset(s).`,
        plan_required: plan === "FREE" ? "STARTER" : "PRO",
        upgrade_url:   "/billing",
      }, { status: 402 });
    }
  }

  const pythonPath = buildPythonPath(subpath);

  // ── Forward to Python ─────────────────────────────────────────────────────
  if (req.method === "GET") {
    const incomingUrl = new URL(req.url);
    const params      = new URLSearchParams(incomingUrl.search);
    params.set("userId", userId);  // always overwrite — never trust client-supplied userId
    const url = `${PYTHON_API}${pythonPath}?${params.toString()}`;
    try {
      const res  = await fetch(url);
      const data = await res.json().catch(() => ({}));
      return NextResponse.json(data, { status: res.status });
    } catch {
      return NextResponse.json({ error: "Backend offline" }, { status: 503 });
    }
  }

  const body     = await req.json().catch(() => ({})) as Record<string, unknown>;
  const enriched = { ...body, userId };

  try {
    const res  = await fetch(`${PYTHON_API}${pythonPath}`, {
      method:  req.method,
      headers: { "Content-Type": "application/json", "X-User-Id": userId },
      body:    JSON.stringify(enriched),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Backend offline" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
