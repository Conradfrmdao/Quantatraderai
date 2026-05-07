import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/prisma";
import { sendAgentStoppedEmail } from "@/lib/email";

export async function POST(req: NextRequest) {
  const { userId: authUserId } = await auth();
  if (!authUserId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const { userId, venue, reason } = await req.json() as {
      userId: string; venue: string; reason: string;
    };
    const user = await prisma.user.findFirst({
      where: { clerkId: userId },
      select: { email: true, name: true },
    });
    if (user?.email) {
      sendAgentStoppedEmail(user.email, reason, venue).catch(() => {});
    }
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}
