/**
 * Admin Stats API — /api/admin/stats
 *
 * Returns aggregated platform metrics:
 *   - Total users, active users, new signups
 *   - Revenue (Stripe subscription counts by plan)
 *   - Active agents (live right now)
 *   - Recent trade activity
 *   - Audit log summary
 *
 * Protected: only users whose clerkId matches ADMIN_CLERK_IDS env var can access.
 */

import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

const PYTHON_API     = process.env.PYTHON_API_URL     ?? "http://localhost:8000";
const ADMIN_SECRET   = process.env.ADMIN_SECRET_KEY   ?? "";
const ADMIN_CLERK_IDS = (process.env.ADMIN_CLERK_IDS ?? "").split(",").map(s => s.trim()).filter(Boolean);

async function isAdmin(clerkId: string): Promise<boolean> {
  if (ADMIN_CLERK_IDS.length > 0) return ADMIN_CLERK_IDS.includes(clerkId);
  // Fallback: first registered user is admin (dev mode)
  const first = await prisma.user.findFirst({ orderBy: { createdAt: "asc" }, select: { clerkId: true } });
  return first?.clerkId === clerkId;
}

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  if (!(await isAdmin(userId))) {
    return NextResponse.json({ error: "Forbidden — admin only" }, { status: 403 });
  }

  const now   = new Date();
  const day1  = new Date(now.getTime() - 24  * 60 * 60 * 1000);
  const day7  = new Date(now.getTime() - 7   * 24 * 60 * 60 * 1000);
  const day30 = new Date(now.getTime() - 30  * 24 * 60 * 60 * 1000);

  // ── DB queries (parallelised) ───────────────────────────────────────────────
  const [
    totalUsers,
    newUsersDay1,
    newUsersDay7,
    newUsersDay30,
    planCounts,
    recentSignups,
    tradeCountDay1,
    tradeCountDay7,
    activeAgents,
    recentAuditEvents,
    topTraders,
  ] = await Promise.all([
    // total users
    prisma.user.count(),

    // new signups
    prisma.user.count({ where: { createdAt: { gte: day1  } } }),
    prisma.user.count({ where: { createdAt: { gte: day7  } } }),
    prisma.user.count({ where: { createdAt: { gte: day30 } } }),

    // plan breakdown (counts per plan)
    prisma.user.groupBy({ by: ["plan"], _count: { id: true } }),

    // recent 20 signups
    prisma.user.findMany({
      orderBy: { createdAt: "desc" }, take: 20,
      select: { clerkId: true, email: true, plan: true, createdAt: true },
    }),

    // trade activity
    prisma.tradeLog.count({ where: { createdAt: { gte: day1  } } }),
    prisma.tradeLog.count({ where: { createdAt: { gte: day7  } } }),

    // users with agent currently marked running
    prisma.agentRun.findMany({
      where: { isRunning: true },
      select: {
        userId: true, venue: true, symbols: true, isPaper: true,
        startedAt: true,
      },
    }),

    // recent audit events
    prisma.auditLog.findMany({
      orderBy: { createdAt: "desc" }, take: 30,
      select: { userId: true, event: true, symbol: true, action: true, createdAt: true },
    }),

    // top traders by trade count
    prisma.tradeLog.groupBy({
      by: ["userId"],
      _count: { id: true },
      orderBy: { _count: { id: "desc" } },
      take: 10,
    }),
  ]);

  // Revenue estimate: count paying users per plan
  const planMap: Record<string, number> = {};
  const PLAN_PRICE: Record<string, number> = { FREE: 0, STARTER: 20, PRO: 99, ENTERPRISE: 299 };
  for (const row of planCounts) {
    planMap[row.plan] = row._count.id;
  }
  const mrr = Object.entries(planMap).reduce((acc, [plan, count]) => {
    return acc + (PLAN_PRICE[plan] ?? 0) * count;
  }, 0);

  const payingUsers = Object.entries(planMap)
    .filter(([plan]) => plan !== "FREE")
    .reduce((a, [, c]) => a + c, 0);

  // Live agent stats from Python backend
  let serverStats: Record<string, unknown> = {};
  try {
    const res = await fetch(
      `${PYTHON_API}/api/admin/server-stats?admin_key=${encodeURIComponent(ADMIN_SECRET)}`,
      { signal: AbortSignal.timeout(3000) },
    );
    if (res.ok) serverStats = await res.json();
  } catch { /* Python may be offline */ }

  return NextResponse.json({
    users: {
      total:      totalUsers,
      paying:     payingUsers,
      new_24h:    newUsersDay1,
      new_7d:     newUsersDay7,
      new_30d:    newUsersDay30,
      by_plan:    planMap,
    },
    revenue: {
      mrr_usd:    mrr,
      arr_usd:    mrr * 12,
      by_plan:    Object.fromEntries(
        Object.entries(planMap).map(([p, c]) => [p, (PLAN_PRICE[p] ?? 0) * c])
      ),
    },
    activity: {
      trades_24h:   tradeCountDay1,
      trades_7d:    tradeCountDay7,
      active_agents_db: activeAgents.length,
      active_agents_live: serverStats.active_agents ?? 0,
      ws_clients:   serverStats.ws_clients ?? 0,
      server_uptime_s: serverStats.uptime_s ?? 0,
    },
    recent_signups: recentSignups,
    active_agents:  activeAgents,
    recent_events:  recentAuditEvents,
    top_traders:    topTraders,
    server:         serverStats,
  });
}
