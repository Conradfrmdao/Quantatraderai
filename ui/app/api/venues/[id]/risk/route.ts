/**
 * Per-venue risk profile.
 *
 * SECURITY: ownership verified via Prisma findFirst before mutation.
 * After PATCH, fires-and-forgets a notification to the Python backend so the
 * running agent picks up the new limits without waiting for the 60-second poll.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";

const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";

const PATCH_ALLOWED = new Set([
  "maxPositionPct", "maxLeverage", "mandatorySlPct",
  "maxLossPerPositionPct", "dailyLossCircuitBreaker",
  "maxTotalExposurePct", "maxConcurrentPositions",
]);

async function resolveUserId(): Promise<string | null> {
  const { userId: clerkId } = await auth();
  if (!clerkId) return null;
  const u = await prisma.user.findUnique({ where: { clerkId }, select: { id: true } });
  return u?.id ?? null;
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await resolveUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const venue = await prisma.venue.findFirst({ where: { id, userId }, select: { id: true } });
  if (!venue) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const risk = await prisma.riskProfile.findUnique({ where: { venueId: id } });
  return NextResponse.json(risk ?? {});
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await resolveUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const venue = await prisma.venue.findFirst({ where: { id, userId }, select: { id: true } });
  if (!venue) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const body = await req.json() as Record<string, unknown>;
  // Whitelist + sanitise: numbers only, clamped to safe ranges
  const data: Record<string, number> = {};
  for (const [k, v] of Object.entries(body)) {
    if (!PATCH_ALLOWED.has(k)) continue;
    const n = Number(v);
    if (!Number.isFinite(n) || n < 0 || n > 1000) continue;
    data[k] = n;
  }

  const risk = await prisma.riskProfile.upsert({
    where:  { venueId: id },
    create: { venueId: id, ...data },
    update: data,
  });

  // Audit log: risk profile updated
  prisma.auditLog.create({
    data: {
      userId, event: "risk_updated", symbol: null, action: null,
      data: JSON.stringify({ venueId: id, changes: data }),
    },
  }).catch(() => {});

  // C1: Notify Python backend so live agent picks up new limits immediately.
  // Fire-and-forget — UX should not block on this.
  const { userId: clerkId } = await auth();
  fetch(`${PYTHON_API}/api/risk/refresh`, {
    method:  "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
      "x-user-id": clerkId ?? "",
    },
    body:    JSON.stringify({ userId: clerkId, venueId: id, risk: data }),
  }).catch(() => {});

  return NextResponse.json(risk);
}
