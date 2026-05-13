import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { getVenueCatalog, listVenueCapabilities } from "@/lib/server/venue-capabilities";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  return NextResponse.json({
    catalog: getVenueCatalog(),
    venues: listVenueCapabilities(),
  });
}
