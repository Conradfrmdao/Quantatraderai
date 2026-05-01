/**
 * POST /api/auth/signout
 * Called by client just before Clerk's sign-out completes.
 * Clears in-process server-side state (auth cache, rate limit windows) for the user.
 * Stripe subId / DB rows are untouched.
 */
import { auth } from "@clerk/nextjs/server";
import { invalidateAuthCache } from "@/lib/auth";
import { clearForUser as clearRateLimits } from "@/lib/rate-limit";

export async function POST() {
  const { userId } = await auth();
  if (!userId) return Response.json({ ok: true }); // already signed out

  invalidateAuthCache(userId);
  // Resolve Prisma id to also clear rate limit windows
  try {
    const { prisma } = await import("@/lib/prisma");
    const u = await prisma.user.findUnique({ where: { clerkId: userId }, select: { id: true } });
    if (u) clearRateLimits(u.id);
    clearRateLimits(userId); // clear by clerkId too (proxy uses clerkId as key)
  } catch {
    /* swallow — best effort */
  }
  return Response.json({ ok: true });
}
