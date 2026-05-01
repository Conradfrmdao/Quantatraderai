import { auth } from "@clerk/nextjs/server";
import { getAuthenticatedUser } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // M-I: Allow access if listing is public OR caller owns it. Never expose private
  // listings of other users via direct ID lookup.
  const { userId: clerkId } = await auth();
  let me: { id: string } | null = null;
  if (clerkId) {
    me = await prisma.user.findUnique({ where: { clerkId }, select: { id: true } });
  }

  const listing = await prisma.strategyListing.findFirst({
    where: {
      id,
      OR: [
        { isPublic: true },
        ...(me ? [{ userId: me.id }] : []),
      ],
    },
    select: {
      id: true, name: true, description: true,
      sharpe: true, totalReturn: true, maxDrawdown: true,
      price: true, isPublic: true, createdAt: true,
      // SECURITY: do not expose `config` JSON to non-owners — could contain
      // sensitive parameters. Only include for owner.
      config: me ? true : false,
      user: { select: { id: true, name: true } },
    },
  });
  if (!listing) return Response.json({ error: "Not found" }, { status: 404 });

  // Strip config if caller is not the owner
  if (listing.user.id !== me?.id) {
    return Response.json({ ...listing, config: undefined });
  }
  return Response.json(listing);
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { user } = await getAuthenticatedUser();
  const { id } = await params;
  await prisma.strategyListing.deleteMany({ where: { id, userId: user.id } });
  return Response.json({ ok: true });
}
