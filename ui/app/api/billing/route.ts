/**
 * Billing API — create checkout sessions + get current plan.
 *
 * GET  /api/billing         → { plan, subId, expiresAt }
 * POST /api/billing         → { checkoutUrl } (body: { plan: "STARTER"|"PRO"|"ENTERPRISE" })
 * DELETE /api/billing       → cancel subscription
 */

import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { getPaymentProvider } from "@/lib/payments";
import { APP_URL } from "@/lib/env-check";

const BASE_URL = APP_URL;

export async function GET() {
  const { user } = await getAuthenticatedUser();
  // M14: Single raw SQL query for all usage counts — 1 round-trip instead of 4
  type BillingRow = {
    plan: string; stripe_sub_id: string | null; plan_expires_at: Date | null;
    venue_count: bigint; trade_count: bigint; copy_count: bigint;
  };
  const rows = await prisma.$queryRaw<BillingRow[]>`
    SELECT
      u.plan,
      u."stripeSubId"     AS stripe_sub_id,
      u."planExpiresAt"   AS plan_expires_at,
      (SELECT COUNT(*) FROM "Venue"            WHERE "userId" = u.id)::bigint             AS venue_count,
      (SELECT COUNT(*) FROM "TradeLog"         WHERE "userId" = u.id)::bigint             AS trade_count,
      (SELECT COUNT(*) FROM "CopyRelationship" WHERE "followerId" = u.id AND "isActive" = true)::bigint AS copy_count
    FROM "User" u
    WHERE u.id = ${user.id}
    LIMIT 1
  `;
  const row = rows[0];
  return Response.json({
    plan:      row?.plan       ?? "FREE",
    subId:     row?.stripe_sub_id ?? null,
    expiresAt: row?.plan_expires_at ?? null,
    provider:  process.env.PAYMENT_PROVIDER ?? "stripe",
    usage: {
      venues:        Number(row?.venue_count ?? 0),
      tradesLogged:  Number(row?.trade_count ?? 0),
      copyFollowing: Number(row?.copy_count  ?? 0),
    },
  });
}

export async function POST(req: Request) {
  const { user } = await getAuthenticatedUser();
  const { plan } = await req.json() as { plan: string };
  if (!["STARTER", "PRO", "ENTERPRISE"].includes(plan)) {
    return Response.json({ error: "Invalid plan" }, { status: 400 });
  }
  const provider = getPaymentProvider();
  try {
    const url = await provider.createCheckout({
      clerkUserId: user.clerkId,
      plan:        plan as "STARTER" | "PRO" | "ENTERPRISE",
      email:       user.email,
      successUrl:  `${BASE_URL}/dashboard?upgraded=true`,
      cancelUrl:   `${BASE_URL}/billing`,
    });
    return Response.json({ checkoutUrl: url });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 502 });
  }
}

export async function DELETE() {
  const { user } = await getAuthenticatedUser();
  const dbUser   = await prisma.user.findUnique({ where: { id: user.id }, select: { stripeSubId: true } });
  if (!dbUser?.stripeSubId) return Response.json({ error: "No active subscription" }, { status: 400 });
  const provider = getPaymentProvider();
  try {
    await provider.cancelSubscription(dbUser.stripeSubId);
    await prisma.user.update({ where: { id: user.id }, data: { plan: "FREE", stripeSubId: null, planExpiresAt: null } });
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 502 });
  }
}
