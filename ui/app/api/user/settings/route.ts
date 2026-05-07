import { NextResponse } from "next/server";
import { getUserId } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const settings = await prisma.userSettings.findUnique({ where: { userId } });
  return NextResponse.json(settings ?? {});
}

export async function PATCH(req: Request) {
  const userId = await getUserId();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const allowed = {
    telegramToken:        body.telegramToken,
    telegramChatId:       body.telegramChatId,
    emailNotifications:   body.emailNotifications,
    timezone:             body.timezone,
  };
  // Remove undefined keys
  const update = Object.fromEntries(Object.entries(allowed).filter(([,v]) => v !== undefined));
  const settings = await prisma.userSettings.upsert({
    where: { userId },
    create: { userId, ...update },
    update,
  });
  return NextResponse.json(settings);
}
