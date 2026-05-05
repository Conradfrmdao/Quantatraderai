import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/terms",
  "/docs",
  "/leaderboard(.*)",
  "/api/webhooks(.*)",
  "/api/health",
  "/api/chart(.*)",       // public: market data proxy (Yahoo Finance)
  "/api/price(.*)",       // public: live price quotes
  "/api/marketplace(.*)", // public: strategy listings
]);

const isApiRoute      = createRouteMatcher(["/api/(.*)"]);
const isWebhookRoute  = createRouteMatcher(["/api/webhooks/(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  // ── CSRF / Origin validation on state-changing requests ──────────────────
  // Webhooks are exempt — they verify their own signatures.
  const method = req.method.toUpperCase();
  const isMutation = method === "POST" || method === "PATCH" || method === "DELETE" || method === "PUT";

  if (isMutation && isApiRoute(req) && !isWebhookRoute(req)) {
    const origin = req.headers.get("origin");
    const host   = req.headers.get("host");
    if (origin) {
      try {
        const originHost = new URL(origin).host;
        if (originHost !== host) {
          // Cross-origin mutation — reject
          return NextResponse.json(
            { error: "Cross-origin requests are not allowed." },
            { status: 403 },
          );
        }
      } catch {
        return NextResponse.json({ error: "Invalid origin" }, { status: 400 });
      }
    }
    // Same-origin browser fetches do not always send Origin (e.g. on Safari);
    // in that case Clerk's SameSite=Lax cookies still protect us.
  }

  if (isPublicRoute(req)) return;

  const { userId } = await auth();

  if (!userId) {
    if (isApiRoute(req)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return (await auth()).redirectToSignIn({ returnBackUrl: req.url });
  }

  // ── Add hardening headers to authenticated responses ────────────────────
  const res = NextResponse.next();
  res.headers.set("X-Frame-Options",        "DENY");
  res.headers.set("X-Content-Type-Options", "nosniff");
  res.headers.set("Referrer-Policy",        "strict-origin-when-cross-origin");
  res.headers.set("Permissions-Policy",     "camera=(), microphone=(), geolocation=()");
  return res;
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
