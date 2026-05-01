import { requirePlan } from "@/lib/plan-guard";
import { prisma } from "@/lib/prisma";

export async function GET(req: Request) {
  const url    = new URL(req.url);
  const sortBy = url.searchParams.get("sort") ?? "sharpe";
  const limit  = Math.min(parseInt(url.searchParams.get("limit") ?? "50"), 200);

  const listings = await prisma.strategyListing.findMany({
    where: { isPublic: true },
    orderBy: sortBy === "return"
      ? { totalReturn: "desc" }
      : { sharpe: "desc" },
    take: limit,
    select: {
      id: true, name: true, description: true,
      sharpe: true, totalReturn: true, maxDrawdown: true,
      price: true, createdAt: true,
      user: { select: { id: true, name: true } },
    },
  });
  return Response.json({ listings });
}

export async function POST(req: Request) {
  const guard = await requirePlan("marketplace");
  if (!guard.allowed) return guard.response;
  const body = await req.json() as {
    name: string; description?: string; config?: string;
    sharpe?: number; totalReturn?: number; maxDrawdown?: number;
    isPublic?: boolean; price?: number;
  };
  if (!body.name) return Response.json({ error: "name required" }, { status: 400 });

  const listing = await prisma.strategyListing.create({
    data: {
      userId:      guard.userId,
      name:        body.name,
      description: body.description ?? null,
      config:      body.config ?? "{}",
      sharpe:      body.sharpe ?? 0,
      totalReturn: body.totalReturn ?? 0,
      maxDrawdown: body.maxDrawdown ?? 0,
      isPublic:    body.isPublic ?? false,
      price:       body.price ?? 0,
    },
  });
  return Response.json({ ok: true, id: listing.id });
}
