/**
 * Weekly report sender — scheduled via Vercel cron or manual POST.
 * Protected by ADMIN_SECRET_KEY header.
 *
 * Vercel cron (add to vercel.json):
 *   { "crons": [{ "path": "/api/email/weekly-report", "schedule": "0 8 * * 1" }] }
 */
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { sendWeeklyReport } from "@/lib/email";

export async function POST(req: NextRequest) {
  if (req.headers.get("x-admin-secret") !== process.env.ADMIN_SECRET_KEY) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const week = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const activeUsers = await prisma.tradeLog.groupBy({
    by: ["userId"],
    where: { createdAt: { gte: week } },
    _count: { id: true },
  });

  let sent = 0;
  for (const row of activeUsers) {
    try {
      const user = await prisma.user.findUnique({
        where: { id: row.userId },
        select: { email: true, name: true },
      });
      if (!user?.email) continue;

      const trades = await prisma.tradeLog.findMany({
        where: { userId: row.userId, createdAt: { gte: week } },
        select: { pnl: true },
      });

      const withPnl     = trades.filter(t => t.pnl !== null);
      const wins        = withPnl.filter(t => (t.pnl ?? 0) > 0).length;
      const totalReturn = withPnl.reduce((a, t) => a + (t.pnl ?? 0), 0);
      const winRate     = withPnl.length > 0 ? (wins / withPnl.length) * 100 : 0;
      const sorted      = [...withPnl].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));

      await sendWeeklyReport(user.email, user.name?.split(" ")[0] ?? "Trader", {
        totalReturn: Math.round(totalReturn * 100) / 100,
        winRate:     Math.round(winRate * 10) / 10,
        totalTrades: trades.length,
        bestTrade:   sorted[0]?.pnl ?? 0,
        worstTrade:  sorted[sorted.length - 1]?.pnl ?? 0,
        sharpe:      0,
      });
      sent++;
    } catch { /* skip individual failures */ }
  }
  return NextResponse.json({ ok: true, sent });
}
