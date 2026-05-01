import { requirePlan } from "@/lib/plan-guard";
import { prisma } from "@/lib/prisma";

export async function GET(req: Request) {
  const guard = await requirePlan(null); // auth check — all plans get audit trail
  if (!guard.allowed) return guard.response;
  const url = new URL(req.url);
  const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "50"), 100);
  const skip  = Math.max(parseInt(url.searchParams.get("skip")  ?? "0"),   0);
  const event = url.searchParams.get("event") ?? undefined;

  const logs = await prisma.auditLog.findMany({
    where:   { userId: guard.userId, ...(event ? { event } : {}) },
    orderBy: { createdAt: "desc" },
    skip,
    take:    limit,
    select:  { id: true, event: true, symbol: true, action: true, data: true, createdAt: true },
  });
  return Response.json({ logs });
}
