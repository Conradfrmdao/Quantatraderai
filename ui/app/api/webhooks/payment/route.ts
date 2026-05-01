/**
 * Universal payment webhook receiver.
 *
 * Routes to whichever gateway is configured via PAYMENT_PROVIDER env var.
 * Handles subscription lifecycle events and keeps User.plan in sync.
 *
 * Point your gateway's webhook URL to:
 *   https://yourdomain.com/api/webhooks/payment
 */

import { prisma } from "@/lib/prisma";
import { getPaymentProvider } from "@/lib/payments";
import type { PaymentEvent } from "@/lib/payments";

export async function POST(req: Request) {
  const body    = await req.text();
  const headers = Object.fromEntries(req.headers.entries());

  const provider = getPaymentProvider();

  let raw: unknown;
  try {
    raw = await provider.verifyWebhook(body, headers);
  } catch (err) {
    console.error(`[${provider.name}] Webhook verification failed:`, err);
    return new Response("Invalid signature", { status: 401 });
  }

  const event: PaymentEvent | null = provider.parseEvent(raw);
  if (!event) return new Response("OK (unhandled event)", { status: 200 });

  console.log(`[${provider.name}] ${event.type} customer=${event.customerId}`);

  // Find user — by Clerk ID (passed at checkout) or by stored gateway customer ID
  let user = event.clerkUserId
    ? await prisma.user.findUnique({ where: { clerkId: event.clerkUserId } }).catch(() => null)
    : null;

  if (!user && event.customerId) {
    user = await prisma.user.findFirst({ where: { stripeCustomerId: event.customerId } }).catch(() => null);
  }

  if (!user) {
    console.warn(`[${provider.name}] No user found for event`, event.type, event.customerId);
    return new Response("OK (user not found)", { status: 200 });
  }

  switch (event.type) {
    case "checkout.completed":
    case "subscription.created":
    case "subscription.updated":
    case "payment.succeeded":
      if (event.plan && event.plan !== "FREE") {
        await prisma.user.update({
          where: { id: user.id },
          data: {
            plan:            event.plan,
            stripeCustomerId: event.customerId || user.stripeCustomerId,
            stripeSubId:      event.subId      || user.stripeSubId,
            planExpiresAt:    event.periodEnd,
          },
        });
      }
      break;

    case "subscription.cancelled":
    case "payment.failed":
      await prisma.user.update({
        where: { id: user.id },
        data: { plan: "FREE", stripeSubId: null, planExpiresAt: null },
      });
      break;
  }

  return new Response("OK", { status: 200 });
}
