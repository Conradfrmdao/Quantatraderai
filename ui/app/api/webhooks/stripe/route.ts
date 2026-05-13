/**
 * Stripe webhook handler — H7: all plan updates are atomic (single prisma.update).
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY       — from Stripe dashboard
 *   STRIPE_WEBHOOK_SECRET   — from "stripe listen --forward-to ..."
 *   STRIPE_PRICE_STARTER    — Stripe price ID for Starter plan
 *   STRIPE_PRICE_PRO        — Stripe price ID for Pro plan
 *   STRIPE_PRICE_ENTERPRISE — Stripe price ID for Enterprise plan
 */

import { prisma } from "@/lib/prisma";

const STRIPE_SECRET  = process.env.STRIPE_SECRET_KEY;
const WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET;
const PYTHON_API     = process.env.PYTHON_API_URL ?? "http://localhost:8000";

/** Tell the Python backend to drop its plan cache for this user. */
async function bustPythonPlanCache(clerkId: string) {
  try {
    await fetch(`${PYTHON_API}/api/plan/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-token": process.env.PYTHON_INTERNAL_TOKEN ?? "",
        "x-user-id": clerkId,
      },
      body: JSON.stringify({ userId: clerkId }),
    });
  } catch (e) { console.warn("[stripe] plan cache bust failed:", e); }
}

const PRICE_TO_PLAN: Record<string, "STARTER" | "PRO" | "ENTERPRISE"> = {
  [process.env.STRIPE_PRICE_STARTER    ?? "price_starter"]:    "STARTER",
  [process.env.STRIPE_PRICE_PRO        ?? "price_pro"]:        "PRO",
  [process.env.STRIPE_PRICE_ENTERPRISE ?? "price_enterprise"]: "ENTERPRISE",
};

async function getStripe() {
  const Stripe = await import("stripe").then(m => m.default);
  return new Stripe(STRIPE_SECRET!);
}

async function verifyEvent(body: string, sig: string) {
  if (!WEBHOOK_SECRET) throw new Error("STRIPE_WEBHOOK_SECRET not set");
  const stripe = await getStripe();
  return stripe.webhooks.constructEvent(body, sig, WEBHOOK_SECRET);
}

export async function POST(req: Request) {
  if (!STRIPE_SECRET || !WEBHOOK_SECRET) {
    console.error("[stripe webhook] STRIPE_SECRET_KEY or STRIPE_WEBHOOK_SECRET not set");
    return new Response("Stripe not configured", { status: 500 });
  }

  const body = await req.text();
  const sig  = req.headers.get("stripe-signature") ?? "";

  let event: Awaited<ReturnType<typeof verifyEvent>>;
  try {
    event = await verifyEvent(body, sig);
  } catch (err) {
    console.error("[stripe webhook] signature invalid:", err);
    return new Response("Invalid signature", { status: 401 });
  }

  const obj = event.data.object as unknown as Record<string, unknown>;

  async function findUser(customerId: string) {
    return prisma.user.findFirst({ where: { stripeCustomerId: customerId as string } });
  }

  try {
    switch (event.type) {
      case "checkout.session.completed": {
        const session  = obj as { customer: string; client_reference_id?: string; subscription?: string };
        const clerkId  = session.client_reference_id;
        const custId   = session.customer;
        const subId    = session.subscription ?? null;

        if (!clerkId) break;

        // Ownership check: if this clerkId already has a Stripe customer, it must match.
        // Prevents a compromised webhook payload from associating a payment to a different user.
        const existingUser = await prisma.user.findUnique({ where: { clerkId }, select: { stripeCustomerId: true } });
        if (existingUser?.stripeCustomerId && existingUser.stripeCustomerId !== custId) {
          console.error("[stripe webhook] customer ID mismatch — possible spoofing attempt", { clerkId, custId, existing: existingUser.stripeCustomerId });
          break;
        }

        // Fetch full subscription to get the price → plan mapping atomically
        let plan: "FREE" | "STARTER" | "PRO" | "ENTERPRISE" = "FREE";
        let expiresAt: Date | null = null;
        if (subId) {
          try {
            const stripe = await getStripe();
            const sub    = await stripe.subscriptions.retrieve(subId);
            const priceId = (sub.items.data[0]?.price as { id: string })?.id ?? "";
            plan      = PRICE_TO_PLAN[priceId] ?? "FREE";
            expiresAt = new Date(sub.current_period_end * 1000);
          } catch (subErr) {
            console.error("[stripe webhook] sub retrieve failed:", subErr);
          }
        }

        // Single atomic update — clerkId lookup avoids race with subscription events
        await prisma.user.upsert({
          where:  { clerkId },
          update: { stripeCustomerId: custId, stripeSubId: subId, plan, planExpiresAt: expiresAt },
          create: {
            clerkId, email: `stripe-${custId}@placeholder.invalid`,
            stripeCustomerId: custId, stripeSubId: subId, plan, planExpiresAt: expiresAt,
          },
        });
        break;
      }

      case "customer.subscription.updated":
      case "customer.subscription.created": {
        const sub  = obj as { customer: string; id: string; status: string; items: { data: { price: { id: string } }[] }; current_period_end: number };
        const user = await findUser(sub.customer);
        if (!user) break;
        const priceId = sub.items.data[0]?.price?.id ?? "";
        const plan    = PRICE_TO_PLAN[priceId] ?? "FREE";
        const active  = sub.status === "active" || sub.status === "trialing";
        // Atomic: all three fields updated together or not at all
        const updated = await prisma.user.update({
          where: { id: user.id },
          data: {
            plan:          active ? plan : "FREE",
            stripeSubId:   sub.id,
            planExpiresAt: active ? new Date(sub.current_period_end * 1000) : null,
          },
          select: { clerkId: true },
        });
        // C3: bust the Python backend's plan cache so the upgrade is immediate
        if (updated.clerkId) await bustPythonPlanCache(updated.clerkId);
        break;
      }

      case "customer.subscription.deleted": {
        const sub  = obj as { customer: string };
        const user = await findUser(sub.customer);
        if (user) {
          const updated = await prisma.user.update({
            where: { id: user.id },
            data:  { plan: "FREE", stripeSubId: null, planExpiresAt: null },
            select: { clerkId: true },
          });
          if (updated.clerkId) await bustPythonPlanCache(updated.clerkId);
        }
        break;
      }

      case "invoice.payment_failed": {
        const inv  = obj as { customer: string };
        const user = await findUser(inv.customer);
        if (user) {
          console.warn("[stripe webhook] payment failed for user:", user.id);
          // Keep plan active until subscription.deleted fires; just log
        }
        break;
      }
    }
  } catch (err) {
    console.error("[stripe webhook] handler error:", err);
    return new Response("Internal error", { status: 500 });
  }

  return new Response("OK", { status: 200 });
}
