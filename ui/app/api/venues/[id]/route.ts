/**
 * Per-venue PATCH / DELETE.
 *
 * SECURITY:
 *   - Auth resolved via Clerk auth() on every call (no cache).
 *   - Ownership verified via Prisma findFirst before any mutation.
 *   - Whitelist of patchable fields — caller cannot set userId/createdAt/etc.
 *   - Mutations to apiKey/apiSecret/apiPassphrase/metaApiToken always re-encrypt.
 *   - PATCH never returns decrypted secrets in response.
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { encrypt } from "@/lib/encryption";

async function resolveUserId(): Promise<string | null> {
  const { userId: clerkId } = await auth();
  if (!clerkId) return null;
  const u = await prisma.user.findUnique({ where: { clerkId }, select: { id: true } });
  return u?.id ?? null;
}

const PATCH_ALLOWED = new Set([
  "displayName", "apiKey", "apiSecret", "apiPassphrase",
  "accountId", "ccxtExchangeId", "network",
  "metaApiToken", "metaApiAccountId",
  "isPaper", "isActive",
]);
const ENCRYPT_FIELDS = new Set(["apiKey", "apiSecret", "apiPassphrase", "metaApiToken"]);

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await resolveUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const owned = await prisma.venue.findFirst({ where: { id, userId }, select: { id: true } });
  if (!owned) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const body = await req.json() as Record<string, unknown>;
  // Strip any keys not on the whitelist
  const data: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(body)) {
    if (!PATCH_ALLOWED.has(k)) continue;
    if (ENCRYPT_FIELDS.has(k) && typeof v === "string" && v) {
      data[k] = encrypt(v);
    } else {
      data[k] = v;
    }
  }

  const v = await prisma.venue.update({
    where: { id },
    data,
    include: { riskProfile: true },
  });
  return NextResponse.json({
    id: v.id, displayName: v.displayName, type: v.type,
    accountId: v.accountId, ccxtExchangeId: v.ccxtExchangeId, network: v.network,
    metaApiAccountId: v.metaApiAccountId, isPaper: v.isPaper, isActive: v.isActive,
    hasApiKey: Boolean(v.apiKey), hasApiSecret: Boolean(v.apiSecret),
    apiKey: v.apiKey ? "••••••••" : "", apiSecret: v.apiSecret ? "••••••••" : "",
    riskProfile: v.riskProfile,
  });
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await resolveUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const owned = await prisma.venue.findFirst({
    where: { id, userId },
    select: { id: true, type: true, displayName: true, isPaper: true },
  });
  if (!owned) return NextResponse.json({ error: "Not found" }, { status: 404 });

  await prisma.venue.delete({ where: { id } });

  // Audit log: venue disconnected
  prisma.auditLog.create({
    data: {
      userId, event: "venue_disconnected", symbol: null, action: null,
      data: JSON.stringify({
        venueId: owned.id, type: owned.type,
        displayName: owned.displayName, isPaper: owned.isPaper,
      }),
    },
  }).catch(() => {});

  return new Response(null, { status: 204 });
}
