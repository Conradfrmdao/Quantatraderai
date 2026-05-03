/**
 * Admin Users API — GET /api/admin/users
 *
 * Search and list all users with their plan, payment status, and trade activity.
 * Admin-only. Returns full user records for the customer support dashboard.
 */
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

const ADMIN_CLERK_IDS = (process.env.ADMIN_CLERK_IDS ?? "").split(",").map(s => s.trim()).filter(Boolean);

async function isAdmin(clerkId: string) {
  if (ADMIN_CLERK_IDS.includes(clerkId)) return true;
  const first = await prisma.user.findFirst({ orderBy: { createdAt: "asc" }, select: { clerkId: true } });
  return first?.clerkId === clerkId;
}

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId || !(await isAdmin(userId))) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { searchParams } = new URL(req.url);
  const query  = searchParams.get("q")?.trim() ?? "";
  const plan   = searchParams.get("plan") ?? "";
  const page   = parseInt(searchParams.get("page") ?? "1");
  const limit  = 25;
  const skip   = (page - 1) * limit;

  const where: Record<string, unknown> = {};
  if (query) {
    where.OR = [
      { email: { contains: query, mode: "insensitive" } },
      { name:  { contains: query, mode: "insensitive" } },
      { clerkId: { contains: query } },
    ];
  }
  if (plan && plan !== "ALL") where.plan = plan;

  const [users, total] = await Promise.all([
    prisma.user.findMany({
      where,
      orderBy: { createdAt: "desc" },
      skip, take: limit,
      select: {
        id: true, clerkId: true, email: true, name: true,
        plan: true, stripeCustomerId: true, stripeSubId: true,
        planExpiresAt: true, createdAt: true,
        _count: { select: { tradeLogs: true } },
      },
    }),
    prisma.user.count({ where }),
  ]);

  return NextResponse.json({ users, total, page, pages: Math.ceil(total / limit) });
}
