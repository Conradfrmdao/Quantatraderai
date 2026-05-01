/**
 * Payment gateway factory.
 *
 * Set PAYMENT_PROVIDER env var to switch gateways:
 *   stripe        — Stripe (default)
 *   lemonsqueezy  — Lemon Squeezy
 *   manual        — No-op stub (dev/testing)
 *
 * To add a new gateway:
 *   1. Create ui/lib/payments/<name>.ts implementing PaymentProvider
 *   2. Add a case below
 *   3. Set the relevant env vars
 */

import type { PaymentProvider } from "./types";

export type { PaymentProvider, PaymentEvent, CheckoutParams, Plan } from "./types";
export { PLAN_LIMITS, PLAN_PRICING, getPlanLimits, checkLimit } from "../plan-limits";

export function getPaymentProvider(): PaymentProvider {
  const name = (process.env.PAYMENT_PROVIDER ?? "stripe").toLowerCase().trim();

  switch (name) {
    case "stripe": {
      const { StripeProvider } = require("./stripe");
      return StripeProvider;
    }
    case "lemonsqueezy":
    case "lemon_squeezy": {
      const { LemonSqueezyProvider } = require("./lemonsqueezy");
      return LemonSqueezyProvider;
    }
    case "manual":
    case "stub":
    case "none": {
      const { ManualProvider } = require("./manual");
      return ManualProvider;
    }
    default:
      throw new Error(
        `Unknown PAYMENT_PROVIDER="${name}". ` +
        `Supported: stripe | lemonsqueezy | manual`
      );
  }
}
