import { getAuthenticatedUser } from "@/lib/auth";
import { requirePlan } from "@/lib/plan-guard";
import { prisma } from "@/lib/prisma";

// GET  — list who you follow + who follows you
export async function GET() {
  const guard = await requirePlan("copyTrading");
  if (!guard.allowed) return guard.response;
  const { user } = await getAuthenticatedUser();
  const [following, followers] = await Promise.all([
    prisma.copyRelationship.findMany({
      where:   { followerId: user.id },
      include: { leader: { select: { id: true, name: true, email: true } } },
    }),
    prisma.copyRelationship.findMany({
      where:   { leaderId: user.id },
      include: { follower: { select: { id: true, name: true, email: true } } },
    }),
  ]);
  return Response.json({ following, followers });
}

// POST — follow a leader  { leaderId: string, maxAllocPct?: number }
export async function POST(req: Request) {
  const guard = await requirePlan("copyTrading");
  if (!guard.allowed) return guard.response;
  const { user } = await getAuthenticatedUser();
  const body = await req.json() as { leaderId: string; maxAllocPct?: number };
  if (!body.leaderId) return Response.json({ error: "leaderId required" }, { status: 400 });
  if (body.leaderId === user.id) return Response.json({ error: "Cannot follow yourself" }, { status: 400 });
  const rel = await prisma.copyRelationship.upsert({
    where: { leaderId_followerId: { leaderId: body.leaderId, followerId: user.id } },
    create: { leaderId: body.leaderId, followerId: user.id, maxAllocPct: body.maxAllocPct ?? 3, isActive: true },
    update: { isActive: true, maxAllocPct: body.maxAllocPct ?? 3 },
  });
  return Response.json({ ok: true, id: rel.id });
}

// DELETE — unfollow  ?leaderId=xxx
export async function DELETE(req: Request) {
  const { user } = await getAuthenticatedUser();
  const url      = new URL(req.url);
  const leaderId = url.searchParams.get("leaderId");
  if (!leaderId) return Response.json({ error: "leaderId required" }, { status: 400 });
  await prisma.copyRelationship.updateMany({
    where: { leaderId, followerId: user.id },
    data:  { isActive: false },
  });
  return Response.json({ ok: true });
}
