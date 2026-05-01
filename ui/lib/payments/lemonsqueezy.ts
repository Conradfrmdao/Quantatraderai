/**
 * Lemon Squeezy payment provider (popular Stripe alternative, flat fees).
 *
 * Required env vars:
 *   LEMONSQUEEZY_API_KEY
 *   LEMONSQUEEZY_WEBHOOK_SECRET
 *   LEMONSQUEEZY_STORE_ID
 *   LEMONSQUEEZY_VARIANT_STARTER
 *   LEMONSQUEEZY_VARIANT_PRO
 *   LEMONSQUEEZY_VARIANT_ENTERPRISE
 */

import type { PaymentProvider, PaymentEvent, CheckoutParams, Plan } from "./types";
import crypto from "crypto";

const VARIANT_TO_PLAN: Record<string, Plan> = {
  [process.env.LEMONSQUEEZY_VARIANT_STARTER    ?? ""]: "STARTER",
  [process.env.LEMONSQUEEZY_VARIANT_PRO        ?? ""]: "PRO",
  [process.env.LEMONSQUEEZY_VARIANT_ENTERPRISE ?? ""]: "ENTERPRISE",
};

export const LemonSqueezyProvider: PaymentProvider = {
  name: "lemonsqueezy",

  async verifyWebhook(body, headers) {
    const secret = process.env.LEMONSQUEEZY_WEBHOOK_SECRET!;
    const sig    = headers["x-signature"] ?? "";
    const hmac   = crypto.createHmac("sha256", secret).update(body).digest("hex");
    if (hmac !== sig) throw new Error("Invalid LemonSqueezy signature");
    return JSON.parse(body);
  },

  parseEvent(raw): PaymentEvent | null {
    const ev  = raw as { meta: { event_name: string; custom_data?: { clerk_user_id?: string } }; data: Record<string, unknown> };
    const name = ev.meta.event_name;
    const obj  = ev.data.attributes as Record<string, unknown> ?? {};
    const type_map: Record<string, PaymentEvent["type"]> = {
      "subscription_created":         "subscription.created",
      "subscription_updated":         "subscription.updated",
      "subscription_cancelled":       "subscription.cancelled",
      "subscription_payment_success": "payment.succeeded",
      "subscription_payment_failed":  "payment.failed",
    };
    const eventType = type_map[name];
    if (!eventType) return null;
    const variantId  = String(obj.variant_id ?? "");
    const plan: Plan = VARIANT_TO_PLAN[variantId] ?? (name === "subscription_cancelled" ? "FREE" : null);
    const periodEnd  = obj.renews_at ? new Date(obj.renews_at as string) : null;
    return {
      type:        eventType,
      customerId:  String(obj.customer_id ?? ""),
      clerkUserId: ev.meta.custom_data?.clerk_user_id ?? null,
      plan, subId: String(ev.data.id ?? ""), periodEnd, rawEvent: raw,
    };
  },

  async createCheckout({ clerkUserId, plan, email, successUrl, cancelUrl }) {
    const variantMap: Record<string, string | undefined> = {
      STARTER:    process.env.LEMONSQUEEZY_VARIANT_STARTER,
      PRO:        process.env.LEMONSQUEEZY_VARIANT_PRO,
      ENTERPRISE: process.env.LEMONSQUEEZY_VARIANT_ENTERPRISE,
    };
    const variantId = variantMap[plan];
    if (!variantId) throw new Error(`No LemonSqueezy variant for ${plan}`);
    const res = await fetch("https://api.lemonsqueezy.com/v1/checkouts", {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.LEMONSQUEEZY_API_KEY}`, "Content-Type": "application/vnd.api+json" },
      body: JSON.stringify({
        data: {
          type: "checkouts",
          attributes: {
            checkout_data: { email, custom: { clerk_user_id: clerkUserId } },
            checkout_options: { success_url: successUrl, cancel_url: cancelUrl },
          },
          relationships: {
            store:   { data: { type: "stores",   id: process.env.LEMONSQUEEZY_STORE_ID } },
            variant: { data: { type: "variants", id: variantId } },
          },
        },
      }),
    });
    const data = await res.json() as { data: { attributes: { url: string } } };
    return data.data.attributes.url;
  },

  async cancelSubscription(subId) {
    await fetch(`https://api.lemonsqueezy.com/v1/subscriptions/${subId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${process.env.LEMONSQUEEZY_API_KEY}` },
    });
  },
};
