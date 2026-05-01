import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url    = new URL(req.url);
  const limit  = Math.min(parseInt(url.searchParams.get("limit") ?? "200"), 1000);
  const symbol = url.searchParams.get("symbol") ?? undefined;
  const action = url.searchParams.get("action") ?? undefined;
  const from   = url.searchParams.get("from");
  const to     = url.searchParams.get("to");

  const where: Record<string, unknown> = { userId: user.id };
  if (symbol) where.symbol = symbol;
  if (action) where.action = action;
  if (from || to) {
    where.createdAt = {
      ...(from ? { gte: new Date(from) } : {}),
      ...(to   ? { lte: new Date(to)   } : {}),
    };
  }

  const trades = await prisma.tradeLog.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
  });
  return Response.json({ trades });
}

export async function POST(req: Request) {
  const { user } = await getAuthenticatedUser();
  const body = await req.json();
  const trade = await prisma.tradeLog.create({
    data: {
      userId:        user.id,
      symbol:        body.symbol,
      action:        body.action,
      quantity:      body.quantity,
      price:         body.price,
      allocationUsd: body.allocationUsd ?? 0,
      pnl:           body.pnl ?? 0,
      source:        body.source ?? "agent",
      rationale:     body.rationale ?? null,
      tpPrice:       body.tpPrice ?? null,
      slPrice:       body.slPrice ?? null,
    },
  });
  return Response.json({ ok: true, id: trade.id });
}
