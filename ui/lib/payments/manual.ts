/**
 * Manual/stub payment provider — for testing without a real gateway.
 * All checkouts return a fake URL; all webhooks log + do nothing.
 * Set PAYMENT_PROVIDER=manual in .env.local.
 */

import type { PaymentProvider, PaymentEvent, CheckoutParams } from "./types";

export const ManualProvider: PaymentProvider = {
  name: "manual",

  async verifyWebhook(body) {
    return JSON.parse(body);
  },

  parseEvent(raw): PaymentEvent | null {
    console.log("[ManualProvider] webhook event:", raw);
    return null;
  },

  async createCheckout({ clerkUserId, plan, successUrl }: CheckoutParams): Promise<string> {
    console.log(`[ManualProvider] createCheckout: user=${clerkUserId} plan=${plan}`);
    return `${successUrl}?manual=true&plan=${plan}`;
  },

  async cancelSubscription(subId: string): Promise<void> {
    console.log(`[ManualProvider] cancelSubscription: ${subId}`);
  },
};
