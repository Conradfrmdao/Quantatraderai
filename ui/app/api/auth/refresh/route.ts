/**
 * POST /api/auth/refresh
 * Invalidates the in-process auth cache for the current Clerk user.
 *
 * Call this whenever the user mutates their profile / venues / plan
 * so the next request reads fresh data instead of stale cache.
 */
import { auth } from "@clerk/nextjs/server";
import { invalidateAuthCache } from "@/lib/auth";

export async function POST() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  invalidateAuthCache(userId);
  return Response.json({ ok: true });
}
