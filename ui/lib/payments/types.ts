/**
 * Universal payment gateway abstraction.
 *
 * Swap gateways by setting PAYMENT_PROVIDER env var:
 *   stripe          — Stripe (default)
 *   paddle          — Paddle (billing 2.0)
 *   lemonsqueezy    — Lemon Squeezy
 *   paystack        — Paystack (Africa / emerging markets)
 *   flutterwave     — Flutterwave
 *   razorpay        — Razorpay (India)
 *   paypal          — PayPal
 *   manual          — Stub (for testing without a gateway)
 *
 * Each provider implements PaymentProvider and handles:
 *   1. Verifying incoming webhook signatures
 *   2. Parsing webhook events to our normalised PaymentEvent
 *   3. Creating a checkout session URL
 *   4. Cancelling a subscription
 */

export type Plan = "FREE" | "STARTER" | "PRO" | "ENTERPRISE";

export type PaymentEventType =
  | "subscription.created"
  | "subscription.updated"
  | "subscription.cancelled"
  | "payment.succeeded"
  | "payment.failed"
  | "checkout.completed";

export interface PaymentEvent {
  type:        PaymentEventType;
  customerId:  string;            // gateway customer ID
  clerkUserId: string | null;     // passed as metadata at checkout
  plan:        Plan | null;
  subId:       string | null;     // subscription ID
  periodEnd:   Date | null;
  rawEvent:    unknown;           // original gateway payload
}

export interface CheckoutParams {
  clerkUserId: string;
  plan:        Plan;
  email?:      string;
  successUrl:  string;
  cancelUrl:   string;
}

export interface PaymentProvider {
  name: string;
  /** Verify webhook signature and return parsed body. Throws on failure. */
  verifyWebhook(body: string, headers: Record<string, string>): Promise<unknown>;
  /** Normalise a verified webhook payload to our PaymentEvent. */
  parseEvent(raw: unknown): PaymentEvent | null;
  /** Create a checkout session and return the redirect URL. */
  createCheckout(params: CheckoutParams): Promise<string>;
  /** Cancel a subscription by ID. */
  cancelSubscription(subId: string): Promise<void>;
}
