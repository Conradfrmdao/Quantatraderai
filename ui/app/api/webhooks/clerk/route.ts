import { Webhook } from "svix";
import { headers } from "next/headers";
import { prisma } from "@/lib/prisma";
import { invalidateAuthCache } from "@/lib/auth";

const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;

export async function POST(req: Request) {
  if (!WEBHOOK_SECRET) {
    return new Response("Webhook secret not configured", { status: 500 });
  }

  const body = await req.text();
  const headerPayload = await headers();
  const svixId        = headerPayload.get("svix-id");
  const svixTimestamp = headerPayload.get("svix-timestamp");
  const svixSignature = headerPayload.get("svix-signature");

  if (!svixId || !svixTimestamp || !svixSignature) {
    return new Response("Missing svix headers", { status: 400 });
  }

  let payload: { type: string; data: Record<string, unknown> };
  try {
    const wh = new Webhook(WEBHOOK_SECRET);
    payload = wh.verify(body, {
      "svix-id": svixId,
      "svix-timestamp": svixTimestamp,
      "svix-signature": svixSignature,
    }) as typeof payload;
  } catch {
    return new Response("Invalid webhook signature", { status: 401 });
  }

  if (payload.type === "user.created") {
    const data = payload.data as {
      id: string;
      email_addresses: { email_address: string }[];
      first_name?: string;
      last_name?: string;
    };
    await prisma.user.upsert({
      where: { clerkId: data.id },
      create: {
        clerkId: data.id,
        email: data.email_addresses[0]?.email_address ?? `unknown-${data.id}@clerk.dev`,
        name: `${data.first_name ?? ""} ${data.last_name ?? ""}`.trim() || null,
      },
      update: {},
    });
  }

  if (payload.type === "user.updated") {
    const data = payload.data as {
      id: string;
      email_addresses: { email_address: string }[];
      first_name?: string;
      last_name?: string;
    };
    invalidateAuthCache(data.id);
    await prisma.user.update({
      where: { clerkId: data.id },
      data: {
        email: data.email_addresses[0]?.email_address,
        name: `${data.first_name ?? ""} ${data.last_name ?? ""}`.trim() || null,
      },
    }).catch(() => {});
  }

  if (payload.type === "user.deleted") {
    const data = payload.data as { id: string };
    invalidateAuthCache(data.id);
    await prisma.user.delete({ where: { clerkId: data.id } }).catch(() => {});
  }

  return new Response("OK", { status: 200 });
}
