/**
 * Production environment validation.
 * Import this at the top of any server-side file that handles payments or auth.
 * It logs clearly when critical vars are missing so ops can catch them fast.
 */

const IS_PROD = process.env.NODE_ENV === "production";

const REQUIRED_PROD: { key: string; hint: string }[] = [
  { key: "NEXT_PUBLIC_APP_URL",   hint: "Set to your public domain, e.g. https://quantatraderai.com" },
  { key: "STRIPE_SECRET_KEY",     hint: "Get from stripe.com → Developers → API keys" },
  { key: "STRIPE_WEBHOOK_SECRET", hint: "Get from stripe.com → Webhooks → your endpoint → Signing secret" },
  { key: "STRIPE_PRICE_STARTER",  hint: "Get from stripe.com → Products → Starter price ID" },
  { key: "STRIPE_PRICE_PRO",      hint: "Get from stripe.com → Products → Pro price ID" },
  { key: "ADMIN_CLERK_IDS",       hint: "Comma-separated Clerk user IDs who can access /admin" },
  { key: "ADMIN_SECRET_KEY",      hint: "Random 32+ char secret shared between Next.js and Python" },
];

if (IS_PROD) {
  for (const { key, hint } of REQUIRED_PROD) {
    if (!process.env[key]) {
      console.error(`[env-check] MISSING required env var: ${key}\n  → ${hint}`);
    }
  }
}

// Export the app URL with a safe fallback that warns loudly
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL
  ?? (IS_PROD
      ? (() => { console.error("[env-check] NEXT_PUBLIC_APP_URL is unset — Stripe redirects will be broken"); return ""; })()
      : "http://localhost:3000");
