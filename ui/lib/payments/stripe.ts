/**
 * Stripe payment provider.
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY
 *   STRIPE_WEBHOOK_SECRET
 *   STRIPE_PRICE_STARTER
 *   STRIPE_PRICE_PRO
 *   STRIPE_PRICE_ENTERPRISE
 */

import type { PaymentProvider, PaymentEvent, CheckoutParams, Plan } from "./types";

const PRICE_TO_PLAN: Record<string, Plan> = {
  [process.env.STRIPE_PRICE_STARTER    ?? ""]: "STARTER",
  [process.env.STRIPE_PRICE_PRO        ?? ""]: "PRO",
  [process.env.STRIPE_PRICE_ENTERPRISE ?? ""]: "ENTERPRISE",
};

export const StripeProvider: PaymentProvider = {
  name: "stripe",

  async verifyWebhook(body, headers) {
    const stripe = await import("stripe").then(m => new m.default(process.env.STRIPE_SECRET_KEY!));
    const sig    = headers["stripe-signature"] ?? "";
    return stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!);
  },

  parseEvent(raw): PaymentEvent | null {
    const ev  = raw as { type: string; data: { object: Record<string, unknown> } };
    const obj = ev.data.object;

    const type_map: Record<string, PaymentEvent["type"]> = {
      "checkout.session.completed":    "checkout.completed",
      "customer.subscription.created": "subscription.created",
      "customer.subscription.updated": "subscription.updated",
      "customer.subscription.deleted": "subscription.cancelled",
      "invoice.payment_succeeded":     "payment.succeeded",
      "invoice.payment_failed":        "payment.failed",
    };

    const eventType = type_map[ev.type];
    if (!eventType) return null;

    const customerId   = (obj.customer as string) ?? "";
    const clerkUserId  = (obj.client_reference_id as string) ?? null;
    const subId        = (obj.subscription as string) ?? (obj.id as string) ?? null;
    const periodEndTs  = obj.current_period_end as number | undefined;
    const periodEnd    = periodEndTs ? new Date(periodEndTs * 1000) : null;
    const priceId      = ((obj as { items?: { data: { price: { id: string } }[] } }).items?.data[0]?.price?.id) ?? "";
    const plan: Plan   = PRICE_TO_PLAN[priceId] ?? (eventType === "subscription.cancelled" ? "FREE" : null);

    return { type: eventType, customerId, clerkUserId, plan, subId, periodEnd, rawEvent: raw };
  },

  async createCheckout({ clerkUserId, plan, email, successUrl, cancelUrl }) {
    const priceMap: Record<string, string | undefined> = {
      STARTER:    process.env.STRIPE_PRICE_STARTER,
      PRO:        process.env.STRIPE_PRICE_PRO,
      ENTERPRISE: process.env.STRIPE_PRICE_ENTERPRISE,
    };
    const priceId = priceMap[plan];
    if (!priceId) throw new Error(`No Stripe price ID for plan ${plan}`);
    const stripe  = await import("stripe").then(m => new m.default(process.env.STRIPE_SECRET_KEY!));
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      line_items: [{ price: priceId, quantity: 1 }],
      client_reference_id: clerkUserId,
      customer_email: email,
      success_url: successUrl,
      cancel_url:  cancelUrl,
    });
    return session.url!;
  },

  async cancelSubscription(subId) {
    const stripe = await import("stripe").then(m => new m.default(process.env.STRIPE_SECRET_KEY!));
    await stripe.subscriptions.cancel(subId);
  },
};
