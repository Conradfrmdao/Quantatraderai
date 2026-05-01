import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { sendAgentStoppedEmail } from "@/lib/email";

export async function POST(req: NextRequest) {
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
