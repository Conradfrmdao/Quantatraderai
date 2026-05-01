import { auth, currentUser } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";

export type AuthUser = {
  id: string;
  clerkId: string;
  email: string;
  name: string | null;
  plan: string;
  stripeCustomerId: string | null;
  stripeSubId: string | null;
  planExpiresAt: Date | null;
  venues: {
    id: string;
    displayName: string;
    type: string;
    isPaper: boolean;
    isActive: boolean;
    riskProfile: {
      id: string;
      maxPositionPct: number;
      maxLeverage: number;
      mandatorySlPct: number;
      maxLossPerPositionPct: number;
      dailyLossCircuitBreaker: number;
      maxTotalExposurePct: number;
      maxConcurrentPositions: number;
    } | null;
  }[];
  settings: {
    id: string;
    telegramToken: string | null;
    telegramChatId: string | null;
    emailNotifications: boolean;
    timezone: string;
  } | null;
};

type AuthResult = { user: AuthUser };

type CacheEntry = { data: AuthResult; expiresAt: number };
const _authCache = new Map<string, CacheEntry>();
// SECURITY: short TTL means stale cache cannot leak between users for long.
// Key = clerkId, so different users have isolated entries.
const CACHE_TTL_MS = 10_000;

async function _lookupUser(userId: string): Promise<AuthResult> {
  let user = await prisma.user.findUnique({
    where: { clerkId: userId },
    include: {
      venues: { include: { riskProfile: true } },
      settings: true,
    },
  });

  if (!user) {
    const clerkUser = await currentUser();
    if (!clerkUser) throw new Error("Unauthorized");

    const email =
      clerkUser.emailAddresses[0]?.emailAddress ?? `unknown-${userId}@clerk.dev`;
    const name =
      `${clerkUser.firstName ?? ""} ${clerkUser.lastName ?? ""}`.trim() || null;

    const existing = await prisma.user.findUnique({ where: { email } });

    if (existing) {
      user = await prisma.user.update({
        where: { email },
        data: { clerkId: userId },
        include: { venues: { include: { riskProfile: true } }, settings: true },
      });
    } else {
      user = await prisma.user.create({
        data: { clerkId: userId, email, name },
        include: { venues: { include: { riskProfile: true } }, settings: true },
      });
    }
  }

  return { user };
}

/** Throws if user is unauthenticated or not found. Safe to destructure directly. */
export async function getAuthenticatedUser(): Promise<AuthResult> {
  const { userId } = await auth();
  if (!userId) throw new Error("Unauthorized");

  const cached = _authCache.get(userId);
  if (cached && cached.expiresAt > Date.now()) return cached.data;

  const result = await _lookupUser(userId);
  _authCache.set(userId, { data: result, expiresAt: Date.now() + CACHE_TTL_MS });
  return result;
}

export function invalidateAuthCache(userId: string) {
  _authCache.delete(userId);
}

export async function getUserId(): Promise<string | null> {
  try {
    const data = await getAuthenticatedUser();
    return data.user.id;
  } catch {
    return null;
  }
}
