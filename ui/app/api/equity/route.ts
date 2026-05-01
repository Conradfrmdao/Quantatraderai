import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url    = new URL(req.url);
  const limit  = Math.min(parseInt(url.searchParams.get("limit") ?? "200"), 1000);

  const points = await prisma.equityPoint.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    take: limit,
    select: { equity: true, balance: true, pnl: true, tickCount: true, createdAt: true },
  });

  return Response.json({ points: points.reverse() });
}

export async function POST(req: Request) {
  // Called by Python backend to persist an equity tick
  const { user } = await getAuthenticatedUser();
  const body = await req.json() as { equity: number; balance: number; pnl?: number; tickCount?: number };
  const point = await prisma.equityPoint.create({
    data: {
      userId:    user.id,
      equity:    body.equity,
      balance:   body.balance,
      pnl:       body.pnl ?? 0,
      tickCount: body.tickCount ?? 0,
    },
  });
  return Response.json({ ok: true, id: point.id });
}
