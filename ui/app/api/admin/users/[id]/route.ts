/**
 * Admin User Detail API
 *
 * GET  /api/admin/users/[id]  — full user profile + Stripe invoices + trade stats
 * PATCH /api/admin/users/[id] — manual plan override (customer support)
 */
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

const ADMIN_CLERK_IDS = (process.env.ADMIN_CLERK_IDS ?? "").split(",").map(s => s.trim()).filter(Boolean);

async function isAdmin(clerkId: string) {
  if (ADMIN_CLERK_IDS.includes(clerkId)) return true;
  const first = await prisma.user.findFirst({ orderBy: { createdAt: "asc" }, select: { clerkId: true } });
  return first?.clerkId === clerkId;
}

// ── GET: full user detail ──────────────────────────────────────────────────────
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { userId: adminId } = await auth();
  if (!adminId || !(await isAdmin(adminId))) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { id } = await params;

  const user = await prisma.user.findUnique({
    where: { id },
    select: {
      id: true, clerkId: true, email: true, name: true,
      plan: true, stripeCustomerId: true, stripeSubId: true,
      planExpiresAt: true, createdAt: true,
      trades:  { orderBy: { createdAt: "desc" }, take: 20,
                 select: { id: true, symbol: true, action: true, price: true,
                           quantity: true, pnl: true, createdAt: true, source: true } },
      venues:  { select: { id: true, type: true, displayName: true, isPaper: true, createdAt: true } },
      audits:  { orderBy: { createdAt: "desc" }, take: 30,
                 select: { event: true, symbol: true, action: true, createdAt: true } },
    },
  });

  if (!user) return NextResponse.json({ error: "User not found" }, { status: 404 });

  // Fetch real Stripe invoices if the user has a Stripe customer ID
  let invoices: {
    id: string; amount: number; currency: string; status: string;
    created: number; description: string | null; hostedUrl: string | null;
  }[] = [];

  if (user.stripeCustomerId && process.env.STRIPE_SECRET_KEY) {
    try {
      const Stripe = await import("stripe").then(m => m.default);
      const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
      const inv = await stripe.invoices.list({
        customer: user.stripeCustomerId,
        limit: 24,
      });
      invoices = inv.data.map(i => ({
        id:          i.id,
        amount:      i.amount_paid / 100,
        currency:    i.currency.toUpperCase(),
        status:      i.status ?? "unknown",
        created:     i.created,
        description: i.description ?? (i.lines.data[0]?.description ?? null),
        hostedUrl:   i.hosted_invoice_url ?? null,
      }));
    } catch { /* Stripe not configured or customer not found */ }
  }

  // Trade stats
  const allTrades = await prisma.tradeLog.findMany({
    where: { userId: id },
    select: { pnl: true, createdAt: true },
  });
  const totalPnl  = allTrades.reduce((a, t) => a + (t.pnl ?? 0), 0);
  const wins      = allTrades.filter(t => (t.pnl ?? 0) > 0).length;
  const winRate   = allTrades.length ? (wins / allTrades.length) * 100 : 0;
  const totalRevenue = invoices
    .filter(i => i.status === "paid")
    .reduce((a, i) => a + i.amount, 0);

  return NextResponse.json({
    user,
    invoices,
    stats: {
      totalTrades:   allTrades.length,
      totalPnl:      Math.round(totalPnl * 100) / 100,
      winRate:       Math.round(winRate * 10) / 10,
      totalRevenue,
      venueCount:    user.venues.length,
    },
  });
}

// ── PATCH: manual plan override ────────────────────────────────────────────────
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { userId: adminId } = await auth();
  if (!adminId || !(await isAdmin(adminId))) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { id }   = await params;
  const { plan, reason, expiresAt } = await req.json() as {
    plan: string; reason?: string; expiresAt?: string;
  };

  const VALID_PLANS = ["FREE", "STARTER", "PRO", "ENTERPRISE"];
  if (!VALID_PLANS.includes(plan)) {
    return NextResponse.json({ error: "Invalid plan" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { id }, select: { email: true, clerkId: true } });
  if (!user) return NextResponse.json({ error: "User not found" }, { status: 404 });

  // Update plan in DB
  const updated = await prisma.user.update({
    where: { id },
    data: {
      plan: plan as "FREE" | "STARTER" | "PRO" | "ENTERPRISE",
      planExpiresAt: expiresAt ? new Date(expiresAt) : null,
    },
    select: { id: true, plan: true, planExpiresAt: true },
  });

  // Write audit log
  await prisma.auditLog.create({
    data: {
      userId:  id,
      event:   "admin_plan_override",
      symbol:  null,
      action:  plan,
      data:    { reason: reason ?? "Manual override by admin", adminId, previousPlan: "unknown" },
    },
  });

  // Bust Python plan cache so the change is instant
  try {
    const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";
    await fetch(`${PYTHON_API}/api/plan/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId: user.clerkId }),
      signal: AbortSignal.timeout(3000),
    });
  } catch { /* non-fatal */ }

  return NextResponse.json({ ok: true, user: updated });
}
